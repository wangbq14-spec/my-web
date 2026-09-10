"""Add custom recharge amount and pricing snapshot columns."""

from alembic import op
import sqlalchemy as sa

revision = "c1d2e3f4a5b6"
down_revision = "f5c6d7e8f9a0"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("recharge_requests") as batch:
        batch.add_column(sa.Column("amount_cny", sa.Numeric(10, 2), nullable=True))
        batch.add_column(sa.Column("pricing_snapshot", sa.Text(), nullable=True))


def downgrade():
    with op.batch_alter_table("recharge_requests") as batch:
        batch.drop_column("pricing_snapshot")
        batch.drop_column("amount_cny")
