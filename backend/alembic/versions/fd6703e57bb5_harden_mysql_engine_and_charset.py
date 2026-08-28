"""harden mysql engine and charset

Revision ID: fd6703e57bb5
Revises: f39835698041
Create Date: 2026-08-27 23:38:48.788210

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'fd6703e57bb5'
down_revision: Union[str, None] = 'f39835698041'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        sa.text(
            """
            ALTER TABLE users
            ENGINE=InnoDB,
            CONVERT TO CHARACTER SET utf8mb4
            COLLATE utf8mb4_unicode_ci
            """
        )
    )


def downgrade() -> None:
    # Intentionally irreversible:
    # reverting to MyISAM would remove transaction and foreign-key support.
    pass
