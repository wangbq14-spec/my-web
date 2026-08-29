from app.rag.vector_store.base import ChunkVector
from app.rag.vector_store.local import LocalVectorStore


def test_search_returns_chunks_in_cosine_similarity_order():
    store = LocalVectorStore()
    store.upsert_chunks(
        user_id=1,
        document_id=10,
        chunks=[
            ChunkVector(chunk_index=0, content="east", embedding=[1.0, 0.0]),
            ChunkVector(chunk_index=1, content="north", embedding=[0.0, 1.0]),
        ],
    )

    matches = store.search(user_id=1, query_embedding=[0.9, 0.1], top_k=10)

    assert [match.content for match in matches] == ["east", "north"]


def test_search_respects_top_k():
    store = LocalVectorStore()
    store.upsert_chunks(
        user_id=1,
        document_id=10,
        chunks=[
            ChunkVector(chunk_index=0, content="best", embedding=[1.0, 0.0]),
            ChunkVector(chunk_index=1, content="second", embedding=[0.8, 0.2]),
        ],
    )

    matches = store.search(user_id=1, query_embedding=[1.0, 0.0], top_k=1)

    assert [match.content for match in matches] == ["best"]
    assert store.search(user_id=1, query_embedding=[1.0, 0.0], top_k=0) == []


def test_delete_document_removes_its_chunks():
    store = LocalVectorStore()
    store.upsert_chunks(
        user_id=1,
        document_id=10,
        chunks=[ChunkVector(chunk_index=0, content="remove", embedding=[1.0, 0.0])],
    )

    store.delete_document(user_id=1, document_id=10)

    assert store.search(user_id=1, query_embedding=[1.0, 0.0], top_k=10) == []


def test_search_isolates_users():
    store = LocalVectorStore()
    store.upsert_chunks(
        user_id=1,
        document_id=10,
        chunks=[ChunkVector(chunk_index=0, content="private", embedding=[1.0, 0.0])],
    )

    assert store.search(user_id=2, query_embedding=[1.0, 0.0], top_k=10) == []
