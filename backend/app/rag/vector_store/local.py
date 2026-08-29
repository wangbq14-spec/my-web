import math

from app.rag.vector_store.base import ChunkVector, ScoredChunk, VectorStore


class LocalVectorStore(VectorStore):
    """In-memory vector store; vectors are lost on restart and must be rebuilt.

    Durable vector persistence is deferred beyond Phase 1.
    """

    def __init__(self) -> None:
        self._documents: dict[tuple[int, int], list[ChunkVector]] = {}

    def upsert_chunks(
        self,
        user_id: int,
        document_id: int,
        generation: int,
        chunks: list[ChunkVector],
    ) -> None:
        del generation
        self._documents[(user_id, document_id)] = list(chunks)

    def search(
        self, user_id: int, query_embedding: list[float], top_k: int
    ) -> list[ScoredChunk]:
        if top_k <= 0:
            return []

        matches: list[ScoredChunk] = []
        for (stored_user_id, document_id), chunks in self._documents.items():
            if stored_user_id != user_id:
                continue
            for chunk in chunks:
                matches.append(
                    ScoredChunk(
                        document_id=document_id,
                        chunk_index=chunk.chunk_index,
                        content=chunk.content,
                        score=self._cosine_similarity(query_embedding, chunk.embedding),
                    )
                )
        matches.sort(key=lambda match: match.score, reverse=True)
        return matches[:top_k]

    def delete_document(self, user_id: int, document_id: int) -> None:
        self._documents.pop((user_id, document_id), None)

    @staticmethod
    def _cosine_similarity(vector_a: list[float], vector_b: list[float]) -> float:
        dot = sum(a * b for a, b in zip(vector_a, vector_b, strict=False))
        norm_a = math.sqrt(sum(value * value for value in vector_a))
        norm_b = math.sqrt(sum(value * value for value in vector_b))
        if norm_a == 0.0 or norm_b == 0.0:
            return 0.0
        return dot / (norm_a * norm_b)
