"""add document async processing fields

Revision ID: b7c8d9e0f1a2
Revises: a1b2c3d4e5f6
Create Date: 2026-08-29 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "b7c8d9e0f1a2"
down_revision: Union[str, None] = "a1b2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        "documents",
        "status",
        existing_type=sa.String(length=20),
        existing_nullable=False,
        server_default=sa.text("'queued'"),
    )
    op.add_column("documents", sa.Column("processing_token", sa.String(length=36), nullable=True))
    op.add_column(
        "documents",
        sa.Column(
            "processing_generation",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
    )
    op.add_column(
        "documents",
        sa.Column(
            "active_generation", sa.Integer(), nullable=False, server_default=sa.text("0")
        ),
    )
    op.add_column(
        "documents",
        sa.Column("retry_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
    )
    op.add_column("documents", sa.Column("next_retry_at", sa.DateTime(), nullable=True))
    op.add_column(
        "documents", sa.Column("processing_started_at", sa.DateTime(), nullable=True)
    )
    op.add_column(
        "documents", sa.Column("processing_lease_expires_at", sa.DateTime(), nullable=True)
    )
    op.add_column("documents", sa.Column("processed_at", sa.DateTime(), nullable=True))
    op.add_column("documents", sa.Column("deleted_at", sa.DateTime(), nullable=True))
    op.add_column("documents", sa.Column("error_code", sa.String(length=64), nullable=True))

    op.add_column(
        "document_chunks",
        sa.Column("generation", sa.Integer(), nullable=False, server_default=sa.text("0")),
    )
    # Existing ready documents need backfill/reprocessing to generate durable embeddings.
    op.add_column("document_chunks", sa.Column("embedding", sa.Text(), nullable=True))
    op.drop_index("ix_document_chunks_document_chunk_index", table_name="document_chunks")
    op.create_index(
        "uq_document_chunks_document_generation_index",
        "document_chunks",
        ["document_id", "generation", "chunk_index"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index(
        "uq_document_chunks_document_generation_index", table_name="document_chunks"
    )
    op.create_index(
        "ix_document_chunks_document_chunk_index",
        "document_chunks",
        ["document_id", "chunk_index"],
        unique=False,
    )
    op.drop_column("document_chunks", "embedding")
    op.drop_column("document_chunks", "generation")

    op.drop_column("documents", "error_code")
    op.drop_column("documents", "deleted_at")
    op.drop_column("documents", "processed_at")
    op.drop_column("documents", "processing_lease_expires_at")
    op.drop_column("documents", "processing_started_at")
    op.drop_column("documents", "next_retry_at")
    op.drop_column("documents", "retry_count")
    op.drop_column("documents", "active_generation")
    op.drop_column("documents", "processing_generation")
    op.drop_column("documents", "processing_token")
    op.alter_column(
        "documents",
        "status",
        existing_type=sa.String(length=20),
        existing_nullable=False,
        server_default=None,
    )
