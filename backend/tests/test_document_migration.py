from pathlib import Path

from app.models.document import Document, DocumentChunk


def test_document_models_include_required_mysql_options_and_cascade_foreign_keys():
    assert Document.__table_args__["mysql_engine"] == "InnoDB"
    assert Document.__table_args__["mysql_charset"] == "utf8mb4"
    assert Document.__table_args__["mysql_collate"] == "utf8mb4_unicode_ci"
    chunk_options = DocumentChunk.__table_args__[-1]
    assert chunk_options["mysql_engine"] == "InnoDB"
    assert chunk_options["mysql_charset"] == "utf8mb4"
    assert chunk_options["mysql_collate"] == "utf8mb4_unicode_ci"
    assert next(iter(Document.__table__.foreign_keys)).ondelete == "CASCADE"
    assert next(iter(DocumentChunk.__table__.foreign_keys)).ondelete == "CASCADE"


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
