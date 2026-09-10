"""add billing tables"""
from alembic import op
import sqlalchemy as sa
revision = "f4b5c6d7e8f9"
down_revision = "f3a4b5c6d7e8"
branch_labels = None
depends_on = None
def upgrade():
    opts={"mysql_engine":"InnoDB","mysql_charset":"utf8mb4","mysql_collate":"utf8mb4_unicode_ci"}
    op.create_table("user_wallets", sa.Column("id",sa.Integer,primary_key=True), sa.Column("user_id",sa.Integer,nullable=False), sa.Column("balance",sa.Integer,nullable=False,server_default="0"), sa.Column("created_at",sa.DateTime,nullable=False), sa.Column("updated_at",sa.DateTime,nullable=False), sa.ForeignKeyConstraint(["user_id"],["users.id"],ondelete="CASCADE"), sa.UniqueConstraint("user_id"), **opts)
    op.create_table("credit_ledger", sa.Column("id",sa.Integer,primary_key=True), sa.Column("user_id",sa.Integer,nullable=False), sa.Column("amount",sa.Integer,nullable=False), sa.Column("operation",sa.String(20),nullable=False), sa.Column("description",sa.Text), sa.Column("request_id",sa.String(64)), sa.Column("created_at",sa.DateTime,nullable=False), sa.ForeignKeyConstraint(["user_id"],["users.id"],ondelete="CASCADE"), sa.UniqueConstraint("request_id","operation",name="uq_credit_ledger_request_operation"), **opts)
    op.create_table("usage_records", sa.Column("id",sa.Integer,primary_key=True), sa.Column("user_id",sa.Integer,nullable=False), sa.Column("provider",sa.String(50),nullable=False), sa.Column("model",sa.String(100),nullable=False), sa.Column("model_tier",sa.String(20)), sa.Column("prompt_tokens",sa.Integer,nullable=False), sa.Column("completion_tokens",sa.Integer,nullable=False), sa.Column("total_tokens",sa.Integer,nullable=False), sa.Column("estimated_cost",sa.Float,nullable=False), sa.Column("credits_charged",sa.Integer,nullable=False), sa.Column("request_id",sa.String(64),nullable=False), sa.Column("status",sa.String(20),nullable=False,server_default="charged"), sa.Column("created_at",sa.DateTime,nullable=False), sa.ForeignKeyConstraint(["user_id"],["users.id"],ondelete="CASCADE"), sa.UniqueConstraint("request_id"), **opts)
    for table,col in (("user_wallets","user_id"),("credit_ledger","user_id"),("credit_ledger","request_id"),("usage_records","user_id"),("usage_records","created_at")): op.create_index(f"ix_{table}_{col}",table,[col])
def downgrade():
    op.drop_table("usage_records"); op.drop_table("credit_ledger"); op.drop_table("user_wallets")
