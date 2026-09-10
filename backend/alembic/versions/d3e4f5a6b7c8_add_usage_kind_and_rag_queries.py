"""Add usage kind column and lightweight rag_queries analytics table."""

from alembic import op
import sqlalchemy as sa

revision = "d3e4f5a6b7c8"
down_revision = "c1d2e3f4a5b6"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("usage_records") as batch:
        batch.add_column(sa.Column("kind", sa.String(20), nullable=True))

    op.create_table(
        "rag_queries",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        mysql_engine="InnoDB",
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_unicode_ci",
    )
    op.create_index("ix_rag_queries_user_id", "rag_queries", ["user_id"])
    op.create_index("ix_rag_queries_created_at", "rag_queries", ["created_at"])


def downgrade():
    op.drop_index("ix_rag_queries_created_at", table_name="rag_queries")
    op.drop_index("ix_rag_queries_user_id", table_name="rag_queries")
    op.drop_table("rag_queries")
    with op.batch_alter_table("usage_records") as batch:
        batch.drop_column("kind")
