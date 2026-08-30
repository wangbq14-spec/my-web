"""add projects

Revision ID: c9d0e1f2a3b4
Revises: b7c8d9e0f1a2
Create Date: 2026-08-30 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c9d0e1f2a3b4"
down_revision: Union[str, None] = "b7c8d9e0f1a2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "projects",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("instructions", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_unicode_ci",
        mysql_engine="InnoDB",
    )
    op.create_index("ix_projects_user_id", "projects", ["user_id"], unique=False)

    op.add_column(
        "conversations", sa.Column("project_id", sa.Integer(), nullable=True)
    )
    op.create_foreign_key(
        "fk_conversations_project_id_projects",
        "conversations",
        "projects",
        ["project_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_conversations_project_id",
        "conversations",
        ["project_id"],
        unique=False,
    )

    op.add_column("documents", sa.Column("project_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_documents_project_id_projects",
        "documents",
        "projects",
        ["project_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_documents_project_id",
        "documents",
        ["project_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_documents_project_id", table_name="documents")
    op.drop_constraint("fk_documents_project_id_projects", "documents", type_="foreignkey")
    op.drop_column("documents", "project_id")

    op.drop_index("ix_conversations_project_id", table_name="conversations")
    op.drop_constraint(
        "fk_conversations_project_id_projects", "conversations", type_="foreignkey"
    )
    op.drop_column("conversations", "project_id")

    op.drop_index("ix_projects_user_id", table_name="projects")
    op.drop_table("projects")
