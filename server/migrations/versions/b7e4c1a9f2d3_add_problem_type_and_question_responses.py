"""add problem_type / content_json to questions and question_responses table

Revision ID: b7e4c1a9f2d3
Revises: ef96c230de9a
Create Date: 2026-08-31 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'b7e4c1a9f2d3'
down_revision = 'ef96c230de9a'
branch_labels = None
depends_on = None


def upgrade():
    # server_default backfills existing rows (NOT NULL with no default
    # otherwise fails against a table that already has data).
    with op.batch_alter_table('questions', schema=None) as batch_op:
        batch_op.add_column(
            sa.Column('problem_type', sa.String(length=30), nullable=False, server_default='coding')
        )
        batch_op.add_column(sa.Column('content_json', sa.Text(), nullable=True))

    op.create_table(
        'question_responses',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('group_id', sa.Integer(), nullable=False),
        sa.Column('question_id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('response_json', sa.Text(), nullable=True),
        sa.Column('is_correct', sa.Boolean(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['group_id'], ['groups.id'], ),
        sa.ForeignKeyConstraint(['question_id'], ['questions.id'], ),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('group_id', 'question_id'),
    )
    with op.batch_alter_table('question_responses', schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f('ix_question_responses_created_at'), ['created_at'], unique=False
        )


def downgrade():
    with op.batch_alter_table('question_responses', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_question_responses_created_at'))
    op.drop_table('question_responses')

    with op.batch_alter_table('questions', schema=None) as batch_op:
        batch_op.drop_column('content_json')
        batch_op.drop_column('problem_type')
