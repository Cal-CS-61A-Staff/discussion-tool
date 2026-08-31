"""prediction suite as an optional per-question field; python tutor code;
group_predictions table

Revision ID: e4a7d21c8b9f
Revises: c3f1a5d90b21
Create Date: 2026-08-31 03:00:00.000000

"""
import json

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = 'e4a7d21c8b9f'
down_revision = 'c3f1a5d90b21'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('questions', schema=None) as batch_op:
        batch_op.add_column(sa.Column('prediction_json', sa.Text(), nullable=True))
        batch_op.add_column(sa.Column('python_tutor_code', sa.Text(), nullable=True))

    op.create_table(
        'group_predictions',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('group_id', sa.Integer(), nullable=False),
        sa.Column('question_id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('prediction_text', sa.Text(), nullable=True),
        sa.Column('is_correct', sa.Boolean(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['group_id'], ['groups.id'], ),
        sa.ForeignKeyConstraint(['question_id'], ['questions.id'], ),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('group_id', 'question_id'),
    )
    with op.batch_alter_table('group_predictions', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_group_predictions_created_at'), ['created_at'], unique=False)

    # Fold the retired standalone 'prediction' problem_type into the new field.
    conn = op.get_bind()
    rows = conn.execute(
        sa.text("SELECT id, content_json FROM questions WHERE problem_type = 'prediction'")
    ).fetchall()
    for row in rows:
        try:
            content = json.loads(row[1]) if row[1] else {}
        except (ValueError, TypeError):
            content = {}
        pred = json.dumps(
            {
                "mode": "output",
                "setup": content.get("setup", ""),
                "doctest": content.get("doctest", ""),
                "items": content.get("items", []),
            }
        )
        conn.execute(
            sa.text(
                "UPDATE questions SET prediction_json = :p, problem_type = 'discussion', "
                "content_json = NULL WHERE id = :i"
            ),
            {"p": pred, "i": row[0]},
        )


def downgrade():
    with op.batch_alter_table('group_predictions', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_group_predictions_created_at'))
    op.drop_table('group_predictions')

    with op.batch_alter_table('questions', schema=None) as batch_op:
        batch_op.drop_column('python_tutor_code')
        batch_op.drop_column('prediction_json')
