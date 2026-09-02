"""drop the per-user grader cooldown columns

Grading moved into the browser (Pyodide) — there's no server-side per-run
cost to rate-limit, so the escalating cooldown and its two `users` columns
are gone.

Revision ID: a9c2e1f4b7d0
Revises: f1a2b3c4d5e6
Create Date: 2026-09-02 08:30:00.000000
"""
import sqlalchemy as sa
from alembic import op

revision = "a9c2e1f4b7d0"
down_revision = "f1a2b3c4d5e6"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.drop_column("grader_run_streak")
        batch_op.drop_column("last_grader_run_at")


def downgrade():
    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.add_column(sa.Column("last_grader_run_at", sa.DateTime(), nullable=True))
        batch_op.add_column(
            sa.Column("grader_run_streak", sa.Integer(), nullable=False, server_default="0")
        )
