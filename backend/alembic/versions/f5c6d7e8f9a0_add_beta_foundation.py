"""Add Classroom Beta foundation tables and user roles/referrals."""

from alembic import op
import sqlalchemy as sa

revision = "f5c6d7e8f9a0"
down_revision = "f4b5c6d7e8f9"
branch_labels = None
depends_on = None

_OPTIONS = {
    "mysql_engine": "InnoDB",
    "mysql_charset": "utf8mb4",
    "mysql_collate": "utf8mb4_unicode_ci",
}


def upgrade():
    with op.batch_alter_table("users") as batch:
        batch.add_column(sa.Column("role", sa.String(20), nullable=False, server_default="user"))
        batch.add_column(sa.Column("referral_code", sa.String(64), nullable=True))
        batch.add_column(sa.Column("referred_by_user_id", sa.Integer(), nullable=True))
        batch.create_unique_constraint("uq_users_referral_code", ["referral_code"])
        batch.create_foreign_key("fk_users_referred_by_user_id", "users", ["referred_by_user_id"], ["id"], ondelete="SET NULL")
        batch.create_index("ix_users_referred_by_user_id", ["referred_by_user_id"])

    op.create_table(
        "invite_codes",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("code", sa.String(64), nullable=False),
        sa.Column("channel", sa.String(40), nullable=False),
        sa.Column("max_uses", sa.Integer(), nullable=False),
        sa.Column("used_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="1"),
        sa.Column("expires_at", sa.DateTime(), nullable=True),
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
        sa.UniqueConstraint("code"),
        **_OPTIONS,
    )
    op.create_table(
        "recharge_requests",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("package_code", sa.String(40), nullable=False),
        sa.Column("amount_display", sa.String(40), nullable=False),
        sa.Column("credits_requested", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("reviewed_at", sa.DateTime(), nullable=True),
        sa.Column("reviewed_by", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["reviewed_by"], ["users.id"], ondelete="SET NULL"),
        **_OPTIONS,
    )
    op.create_table(
        "feedback",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("type", sa.String(20), nullable=False),
        sa.Column("path", sa.String(200), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="new"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        **_OPTIONS,
    )
    op.create_table(
        "message_attachments",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("conversation_id", sa.Integer(), nullable=True),
        sa.Column("message_id", sa.Integer(), nullable=True),
        sa.Column("type", sa.String(20), nullable=False, server_default="image"),
        sa.Column("mime_type", sa.String(80), nullable=False),
        sa.Column("original_name", sa.String(255), nullable=False),
        sa.Column("storage_path", sa.String(500), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["conversation_id"], ["conversations.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["message_id"], ["messages.id"], ondelete="SET NULL"),
        **_OPTIONS,
    )
    for table, columns in (
        ("invite_codes", ("created_by",)),
        ("recharge_requests", ("user_id", "status", "reviewed_by")),
        ("feedback", ("user_id", "status")),
        ("message_attachments", ("user_id", "conversation_id", "message_id")),
    ):
        for column in columns:
            op.create_index(f"ix_{table}_{column}", table, [column])


def downgrade():
    op.drop_table("message_attachments")
    op.drop_table("feedback")
    op.drop_table("recharge_requests")
    op.drop_table("invite_codes")
    with op.batch_alter_table("users") as batch:
        batch.drop_index("ix_users_referred_by_user_id")
        batch.drop_constraint("fk_users_referred_by_user_id", type_="foreignkey")
        batch.drop_constraint("uq_users_referral_code", type_="unique")
        batch.drop_column("referred_by_user_id")
        batch.drop_column("referral_code")
        batch.drop_column("role")
