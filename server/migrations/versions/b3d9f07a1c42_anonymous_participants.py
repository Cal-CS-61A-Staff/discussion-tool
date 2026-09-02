"""anonymous participants + per-assignment share links

Students no longer have accounts or class enrollment. Group-scoped tables
key on an opaque per-session ``participant_key`` (server/participant.py)
instead of ``users.id``; ``groups`` gets ``last_activity_at`` for the
retention TTL; ``worksheets`` gets ``share_code`` for the student entry
link. Existing transient session data is intentionally discarded.

Revision ID: b3d9f07a1c42
Revises: a9c2e1f4b7d0
Create Date: 2026-09-02 12:00:00.000000
"""
import sqlalchemy as sa
from alembic import op

revision = "b3d9f07a1c42"
down_revision = "a9c2e1f4b7d0"
branch_labels = None
depends_on = None

# All disposable — wiped so NOT NULL columns can be added cleanly.
_TRANSIENT_TABLES = (
    "test_runs",
    "ratings",
    "scratch_codes",
    "question_responses",
    "group_predictions",
    "group_question_states",
    "group_assignment_progress",
    "group_memberships",
    "groups",
)


def _wipe():
    bind = op.get_bind()
    for table in _TRANSIENT_TABLES:
        bind.execute(sa.text(f"DELETE FROM {table}"))
    # Student class enrollment is gone; keep only staff rows.
    bind.execute(sa.text("DELETE FROM class_memberships WHERE role <> 'staff'"))


def upgrade():
    _wipe()

    op.drop_table("attempts")

    with op.batch_alter_table("groups", schema=None) as b:
        b.add_column(
            sa.Column(
                "last_activity_at",
                sa.DateTime(),
                nullable=False,
                server_default=sa.func.now(),
            )
        )
        b.create_index("ix_groups_last_activity_at", ["last_activity_at"], unique=False)

    with op.batch_alter_table("worksheets", schema=None) as b:
        b.add_column(sa.Column("share_code", sa.String(length=12), nullable=True))
        b.create_unique_constraint("uq_worksheets_share_code", ["share_code"])

    with op.batch_alter_table("group_memberships", schema=None) as b:
        b.drop_column("user_id")
        b.add_column(sa.Column("participant_key", sa.String(length=40), nullable=False))
        b.add_column(
            sa.Column("participant_name", sa.String(length=80), nullable=False, server_default="")
        )
        b.create_index("ix_group_memberships_participant_key", ["participant_key"], unique=False)
        b.create_unique_constraint(
            "uq_group_memberships_group_participant", ["group_id", "participant_key"]
        )

    with op.batch_alter_table("group_assignment_progress", schema=None) as b:
        b.drop_column("typist_user_id")
        b.add_column(sa.Column("typist_key", sa.String(length=40), nullable=True))

    with op.batch_alter_table("ratings", schema=None) as b:
        b.drop_column("user_id")
        b.add_column(sa.Column("participant_key", sa.String(length=40), nullable=False))
        b.create_index("ix_ratings_participant_key", ["participant_key"], unique=False)
        b.create_unique_constraint(
            "uq_ratings_group_question_participant", ["group_id", "question_id", "participant_key"]
        )

    for table in ("scratch_codes", "question_responses", "group_predictions", "test_runs"):
        with op.batch_alter_table(table, schema=None) as b:
            b.drop_column("user_id")
            b.add_column(sa.Column("participant_key", sa.String(length=40), nullable=False))

    with op.batch_alter_table("scratch_codes", schema=None) as b:
        b.create_index("ix_scratch_codes_participant_key", ["participant_key"], unique=False)
        b.create_unique_constraint(
            "uq_scratch_codes_group_question_participant",
            ["group_id", "question_id", "participant_key"],
        )


def downgrade():
    _wipe()

    with op.batch_alter_table("scratch_codes", schema=None) as b:
        b.drop_constraint("uq_scratch_codes_group_question_participant", type_="unique")
        b.drop_index("ix_scratch_codes_participant_key")

    for table in ("scratch_codes", "question_responses", "group_predictions", "test_runs"):
        with op.batch_alter_table(table, schema=None) as b:
            b.drop_column("participant_key")
            b.add_column(sa.Column("user_id", sa.Integer(), nullable=False))

    with op.batch_alter_table("ratings", schema=None) as b:
        b.drop_constraint("uq_ratings_group_question_participant", type_="unique")
        b.drop_index("ix_ratings_participant_key")
        b.drop_column("participant_key")
        b.add_column(sa.Column("user_id", sa.Integer(), nullable=False))

    with op.batch_alter_table("group_assignment_progress", schema=None) as b:
        b.drop_column("typist_key")
        b.add_column(sa.Column("typist_user_id", sa.Integer(), nullable=True))

    with op.batch_alter_table("group_memberships", schema=None) as b:
        b.drop_constraint("uq_group_memberships_group_participant", type_="unique")
        b.drop_index("ix_group_memberships_participant_key")
        b.drop_column("participant_name")
        b.drop_column("participant_key")
        b.add_column(sa.Column("user_id", sa.Integer(), nullable=False))

    with op.batch_alter_table("worksheets", schema=None) as b:
        b.drop_constraint("uq_worksheets_share_code", type_="unique")
        b.drop_column("share_code")

    with op.batch_alter_table("groups", schema=None) as b:
        b.drop_index("ix_groups_last_activity_at")
        b.drop_column("last_activity_at")

    op.create_table(
        "attempts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("group_id", sa.Integer(), nullable=False),
        sa.Column("question_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("prediction_text", sa.Text(), nullable=False),
        sa.Column("is_match", sa.Boolean(), nullable=False),
        sa.Column("code_snapshot", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["group_id"], ["groups.id"]),
        sa.ForeignKeyConstraint(["question_id"], ["questions.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("attempts", schema=None) as b:
        b.create_index(b.f("ix_attempts_created_at"), ["created_at"], unique=False)
