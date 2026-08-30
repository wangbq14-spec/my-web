"""add project activity timestamp

Revision ID: d1e2f3a4b5c6
Revises: c9d0e1f2a3b4
Create Date: 2026-08-30 00:10:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "d1e2f3a4b5c6"
down_revision: Union[str, None] = "c9d0e1f2a3b4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "projects", sa.Column("last_activity_at", sa.DateTime(), nullable=True)
    )
    op.execute("UPDATE projects SET last_activity_at = created_at")
    op.alter_column(
        "projects",
        "last_activity_at",
        existing_type=sa.DateTime(),
        nullable=False,
    )
    op.create_index(
        "ix_projects_user_id_last_activity",
        "projects",
        ["user_id", "last_activity_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_projects_user_id_last_activity", table_name="projects")
    op.drop_column("projects", "last_activity_at")
