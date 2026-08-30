import subprocess
from pathlib import Path

from app.models.document import Document, DocumentChunk


def test_document_models_include_required_mysql_options_and_foreign_keys():
    assert Document.__table_args__["mysql_engine"] == "InnoDB"
    assert Document.__table_args__["mysql_charset"] == "utf8mb4"
    assert Document.__table_args__["mysql_collate"] == "utf8mb4_unicode_ci"
    chunk_options = DocumentChunk.__table_args__[-1]
    assert chunk_options["mysql_engine"] == "InnoDB"
    assert chunk_options["mysql_charset"] == "utf8mb4"
    assert chunk_options["mysql_collate"] == "utf8mb4_unicode_ci"
    document_foreign_keys = {
        foreign_key.column.table.name: foreign_key.ondelete
        for foreign_key in Document.__table__.foreign_keys
    }
    assert document_foreign_keys == {"users": "CASCADE", "projects": "SET NULL"}
    assert next(iter(DocumentChunk.__table__.foreign_keys)).ondelete == "CASCADE"
    assert Document.status.default.arg == "queued"
    assert Document.processing_generation.default.arg == 0
    assert Document.active_generation.default.arg == 0
    assert Document.retry_count.default.arg == 0
    assert DocumentChunk.generation.default.arg == 0
    assert "embedding" in DocumentChunk.__table__.c
    unique_indexes = [index for index in DocumentChunk.__table__.indexes if index.unique]
    assert any(
        tuple(column.name for column in index.columns)
        == ("document_id", "generation", "chunk_index")
        for index in unique_indexes
    )


def test_document_migration_defines_tables_cascades_indexes_and_mysql_options():
    migration_path = (
        Path(__file__).resolve().parents[1]
        / "alembic"
        / "versions"
        / "a1b2c3d4e5f6_add_documents_and_chunks.py"
    )
    source = migration_path.read_text(encoding="utf-8")

    assert "'documents'" in source
    assert "'document_chunks'" in source
    assert "ondelete='CASCADE'" in source
    assert "'ix_document_chunks_document_id'" in source
    assert "'ix_document_chunks_document_chunk_index'" in source
    assert "mysql_engine='InnoDB'" in source
    assert "mysql_charset='utf8mb4'" in source
    assert "mysql_collate='utf8mb4_unicode_ci'" in source
    assert "down_revision: Union[str, None] = 'fcac867b9964'" in source


def test_document_async_migration_defines_new_columns_and_unique_generation_index():
    migration_path = (
        Path(__file__).resolve().parents[1]
        / "alembic"
        / "versions"
        / "b7c8d9e0f1a2_add_document_async_fields.py"
    )
    source = migration_path.read_text(encoding="utf-8")

    for column_name in (
        "processing_token",
        "processing_generation",
        "active_generation",
        "retry_count",
        "next_retry_at",
        "processing_started_at",
        "processing_lease_expires_at",
        "processed_at",
        "deleted_at",
        "error_code",
        "generation",
        "embedding",
    ):
        assert f'"{column_name}"' in source
    assert "ix_document_chunks_document_chunk_index" in source
    assert "uq_document_chunks_document_generation_index" in source
    assert "unique=True" in source
    assert 'down_revision: Union[str, None] = "a1b2c3d4e5f6"' in source


def test_alembic_has_a_single_head():
    backend_dir = Path(__file__).resolve().parents[1]
    result = subprocess.run(
        ["uv", "run", "alembic", "heads"],
        cwd=backend_dir,
        check=True,
        capture_output=True,
        text=True,
    )
    lines = [line for line in result.stdout.splitlines() if line.strip()]
    assert lines == ["d1e2f3a4b5c6 (head)"]
