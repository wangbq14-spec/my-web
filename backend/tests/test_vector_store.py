from sqlalchemy.orm import sessionmaker

from app.models.document import Document
from app.models.project import Project
from app.models.user import User
from app.rag.vector_store.base import ChunkVector
from app.rag.vector_store.local import LocalVectorStore


def _create_ready_document(db, username: str = "alice") -> Document:
    user = User(
        email=f"{username}@example.com", username=username, hashed_password="x"
    )
    db.add(user)
    db.flush()
    document = Document(
        user_id=user.id,
        filename=f"{username}.txt",
        original_filename=f"{username}.txt",
        content_type="text/plain",
        file_size=1,
        status="ready",
    )
    db.add(document)
    db.commit()
    return document


def _create_store(db) -> LocalVectorStore:
    sessions = sessionmaker(bind=db.get_bind(), autocommit=False, autoflush=False)
    return LocalVectorStore(sessions)


def test_search_returns_chunks_in_cosine_similarity_order(db):
    document = _create_ready_document(db)
    store = _create_store(db)
    store.upsert_chunks(
        user_id=document.user_id,
        document_id=document.id,
        generation=1,
        chunks=[
            ChunkVector(chunk_index=0, content="east", embedding=[1.0, 0.0]),
            ChunkVector(chunk_index=1, content="north", embedding=[0.0, 1.0]),
        ],
    )

    matches = store.search(
        user_id=document.user_id, query_embedding=[0.9, 0.1], top_k=10
    )

    assert [match.content for match in matches] == ["east", "north"]


def test_search_respects_top_k(db):
    document = _create_ready_document(db)
    store = _create_store(db)
    store.upsert_chunks(
        user_id=document.user_id,
        document_id=document.id,
        generation=1,
        chunks=[
            ChunkVector(chunk_index=0, content="best", embedding=[1.0, 0.0]),
            ChunkVector(chunk_index=1, content="second", embedding=[0.8, 0.2]),
        ],
    )

    matches = store.search(
        user_id=document.user_id, query_embedding=[1.0, 0.0], top_k=1
    )

    assert [match.content for match in matches] == ["best"]
    assert (
        store.search(
            user_id=document.user_id, query_embedding=[1.0, 0.0], top_k=0
        )
        == []
    )


def test_delete_document_removes_its_chunks(db):
    document = _create_ready_document(db)
    store = _create_store(db)
    store.upsert_chunks(
        user_id=document.user_id,
        document_id=document.id,
        generation=1,
        chunks=[ChunkVector(chunk_index=0, content="remove", embedding=[1.0, 0.0])],
    )

    store.delete_document(user_id=document.user_id, document_id=document.id)

    assert (
        store.search(
            user_id=document.user_id, query_embedding=[1.0, 0.0], top_k=10
        )
        == []
    )


def test_search_isolates_users(db):
    alice_document = _create_ready_document(db, "alice")
    bob = User(email="bob@example.com", username="bob", hashed_password="x")
    db.add(bob)
    db.commit()
    store = _create_store(db)
    store.upsert_chunks(
        user_id=alice_document.user_id,
        document_id=alice_document.id,
        generation=1,
        chunks=[ChunkVector(chunk_index=0, content="private", embedding=[1.0, 0.0])],
    )

    assert store.search(user_id=bob.id, query_embedding=[1.0, 0.0], top_k=10) == []


def test_search_filters_by_document_project_before_applying_top_k(db):
    user = User(email="alice@example.com", username="alice", hashed_password="x")
    db.add(user)
    db.flush()
    project_a = Project(user_id=user.id, name="project-a")
    project_b = Project(user_id=user.id, name="project-b")
    db.add_all([project_a, project_b])
    db.flush()
    document_a = Document(
        user_id=user.id,
        project_id=project_a.id,
        filename="a.txt",
        original_filename="a.txt",
        content_type="text/plain",
        file_size=1,
        status="ready",
    )
    document_b = Document(
        user_id=user.id,
        project_id=project_b.id,
        filename="b.txt",
        original_filename="b.txt",
        content_type="text/plain",
        file_size=1,
        status="ready",
    )
    db.add_all([document_a, document_b])
    db.commit()
    store = _create_store(db)
    store.upsert_chunks(
        user.id,
        document_a.id,
        1,
        [ChunkVector(chunk_index=0, content="project-a", embedding=[0.8, 0.2])],
    )
    store.upsert_chunks(
        user.id,
        document_b.id,
        1,
        [ChunkVector(chunk_index=0, content="project-b", embedding=[1.0, 0.0])],
    )

    matches = store.search(
        user.id, query_embedding=[1.0, 0.0], top_k=1, project_id=project_a.id
    )

    assert [match.document_id for match in matches] == [document_a.id]
