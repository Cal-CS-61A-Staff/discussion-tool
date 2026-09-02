"""Pensive-style groups + per-class roles

Groups become class-scoped (join by number); Section becomes a "Room" with
an assigned-numbers spec; per-class roles move to class_memberships
(replacing the email-keyed class_enrollments); adds ta_watched_numbers for
the dashboard watch list; retires the global 'ta' role.

Revision ID: f1a2b3c4d5e6
Revises: e4a7d21c8b9f
Create Date: 2026-08-31 10:00:00.000000
"""
import secrets

import sqlalchemy as sa
from alembic import op

revision = "f1a2b3c4d5e6"
down_revision = "e4a7d21c8b9f"
branch_labels = None
depends_on = None

_ALPHABET = "23456789ABCDEFGHJKMNPQRSTVWXYZ"


def _code():
    return "".join(secrets.choice(_ALPHABET) for _ in range(6))


def upgrade():
    bind = op.get_bind()

    # --- classes.join_code -------------------------------------------------
    op.add_column("classes", sa.Column("join_code", sa.String(length=12), nullable=True))
    used = set()
    for (class_id,) in bind.execute(sa.text("SELECT id FROM classes")).fetchall():
        code = _code()
        while code in used:
            code = _code()
        used.add(code)
        bind.execute(sa.text("UPDATE classes SET join_code = :c WHERE id = :i"), {"c": code, "i": class_id})
    with op.batch_alter_table("classes", schema=None) as batch_op:
        batch_op.alter_column("join_code", existing_type=sa.String(length=12), nullable=False)
        batch_op.create_unique_constraint("uq_classes_join_code", ["join_code"])

    # --- sections.assigned_numbers --------------------------------------
    op.add_column(
        "sections",
        sa.Column("assigned_numbers", sa.String(length=200), nullable=False, server_default=""),
    )

    # --- groups.section_id -> groups.class_id --------------------------
    op.add_column("groups", sa.Column("class_id", sa.Integer(), nullable=True))
    bind.execute(
        sa.text(
            "UPDATE groups SET class_id = "
            "(SELECT s.class_id FROM sections s WHERE s.id = groups.section_id)"
        )
    )
    bind.execute(sa.text("DELETE FROM groups WHERE class_id IS NULL"))
    with op.batch_alter_table("groups", schema=None) as batch_op:
        batch_op.alter_column("class_id", existing_type=sa.Integer(), nullable=False)
        batch_op.drop_column("section_id")
        batch_op.create_unique_constraint("uq_groups_class_id_number", ["class_id", "number"])
        batch_op.create_foreign_key("fk_groups_class_id_classes", "classes", ["class_id"], ["id"])

    # --- class_memberships (replaces class_enrollments) -----------------
    op.create_table(
        "class_memberships",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("class_id", sa.Integer(), nullable=False),
        sa.Column("role", sa.String(length=10), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["class_id"], ["classes.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "class_id"),
    )
    # staff = whoever ran a room (primary TA or co-teacher)
    bind.execute(
        sa.text(
            "INSERT INTO class_memberships (user_id, class_id, role, created_at) "
            "SELECT DISTINCT s.ta_user_id, s.class_id, 'staff', CURRENT_TIMESTAMP "
            "FROM sections s WHERE s.ta_user_id IS NOT NULL"
        )
    )
    bind.execute(
        sa.text(
            "INSERT INTO class_memberships (user_id, class_id, role, created_at) "
            "SELECT sct.user_id, s.class_id, 'staff', CURRENT_TIMESTAMP "
            "FROM section_co_teachers sct JOIN sections s ON s.id = sct.section_id "
            "WHERE NOT EXISTS (SELECT 1 FROM class_memberships cm "
            "  WHERE cm.user_id = sct.user_id AND cm.class_id = s.class_id)"
        )
    )
    # student = existing enrollment whose email resolves to a real account
    bind.execute(
        sa.text(
            "INSERT INTO class_memberships (user_id, class_id, role, created_at) "
            "SELECT u.id, ce.class_id, 'student', ce.created_at "
            "FROM class_enrollments ce JOIN users u ON lower(u.email) = lower(ce.student_email) "
            "WHERE NOT EXISTS (SELECT 1 FROM class_memberships cm "
            "  WHERE cm.user_id = u.id AND cm.class_id = ce.class_id)"
        )
    )

    # --- ta_watched_numbers ------------------------------------------------
    op.create_table(
        "ta_watched_numbers",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("class_id", sa.Integer(), nullable=False),
        sa.Column("number", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["class_id"], ["classes.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "class_id", "number"),
    )

    # --- drop class_enrollments -----------------------------------------
    with op.batch_alter_table("class_enrollments", schema=None) as batch_op:
        batch_op.drop_index("ix_class_enrollments_student_email")
    op.drop_table("class_enrollments")

    # --- retire the global 'ta' role ----------------------------------
    bind.execute(sa.text("UPDATE users SET role = 'student' WHERE role = 'ta'"))


def downgrade():
    bind = op.get_bind()

    op.create_table(
        "class_enrollments",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("class_id", sa.Integer(), nullable=False),
        sa.Column("student_email", sa.String(length=120), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["class_id"], ["classes.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("class_id", "student_email"),
    )
    with op.batch_alter_table("class_enrollments", schema=None) as batch_op:
        batch_op.create_index("ix_class_enrollments_student_email", ["student_email"], unique=False)
    bind.execute(
        sa.text(
            "INSERT INTO class_enrollments (class_id, student_email, created_at) "
            "SELECT cm.class_id, u.email, cm.created_at FROM class_memberships cm "
            "JOIN users u ON u.id = cm.user_id WHERE cm.role = 'student' AND u.email IS NOT NULL"
        )
    )

    op.drop_table("ta_watched_numbers")
    op.drop_table("class_memberships")

    op.add_column("groups", sa.Column("section_id", sa.Integer(), nullable=True))
    bind.execute(
        sa.text(
            "UPDATE groups SET section_id = "
            "(SELECT MIN(s.id) FROM sections s WHERE s.class_id = groups.class_id)"
        )
    )
    bind.execute(sa.text("DELETE FROM groups WHERE section_id IS NULL"))
    with op.batch_alter_table("groups", schema=None) as batch_op:
        batch_op.alter_column("section_id", existing_type=sa.Integer(), nullable=False)
        batch_op.drop_column("class_id")
        batch_op.create_unique_constraint("uq_groups_section_id_number", ["section_id", "number"])
        batch_op.create_foreign_key("fk_groups_section_id_sections", "sections", ["section_id"], ["id"])

    op.drop_column("sections", "assigned_numbers")
    with op.batch_alter_table("classes", schema=None) as batch_op:
        batch_op.drop_constraint("uq_classes_join_code", type_="unique")
    op.drop_column("classes", "join_code")
