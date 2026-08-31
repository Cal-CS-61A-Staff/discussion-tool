"""class-level roster: class_enrollments replaces section_enrollments

Revision ID: c3f1a5d90b21
Revises: b7e4c1a9f2d3
Create Date: 2026-08-31 02:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'c3f1a5d90b21'
down_revision = 'b7e4c1a9f2d3'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'class_enrollments',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('class_id', sa.Integer(), nullable=False),
        sa.Column('student_email', sa.String(length=120), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['class_id'], ['classes.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('class_id', 'student_email'),
    )
    with op.batch_alter_table('class_enrollments', schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f('ix_class_enrollments_student_email'), ['student_email'], unique=False
        )

    # Roll every existing per-section enrollment up to its class.
    op.execute(
        """
        INSERT INTO class_enrollments (class_id, student_email, created_at)
        SELECT s.class_id, se.student_email, MIN(se.created_at)
        FROM section_enrollments se
        JOIN sections s ON s.id = se.section_id
        GROUP BY s.class_id, se.student_email
        """
    )

    op.drop_table('section_enrollments')


def downgrade():
    op.create_table(
        'section_enrollments',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('section_id', sa.Integer(), nullable=False),
        sa.Column('student_email', sa.String(length=120), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['section_id'], ['sections.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('section_id', 'student_email'),
    )
    with op.batch_alter_table('section_enrollments', schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f('ix_section_enrollments_student_email'), ['student_email'], unique=False
        )

    # Best effort: attach each class enrollment to that class's lowest-id section.
    op.execute(
        """
        INSERT INTO section_enrollments (section_id, student_email, created_at)
        SELECT (SELECT MIN(s.id) FROM sections s WHERE s.class_id = ce.class_id),
               ce.student_email, ce.created_at
        FROM class_enrollments ce
        WHERE EXISTS (SELECT 1 FROM sections s WHERE s.class_id = ce.class_id)
        """
    )

    with op.batch_alter_table('class_enrollments', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_class_enrollments_student_email'))
    op.drop_table('class_enrollments')
