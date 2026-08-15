"""Associate experiment runs with their variant."""

import sqlalchemy as sa
from alembic import op

revision = "0002_add_run_variant_id"
down_revision = "0001_initial_schema"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("runs", sa.Column("variant_id", sa.String(length=200), nullable=True))
    op.create_index(op.f("ix_runs_variant_id"), "runs", ["variant_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_runs_variant_id"), table_name="runs")
    op.drop_column("runs", "variant_id")
