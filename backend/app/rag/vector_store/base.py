from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class ChunkVector:
    chunk_index: int
    content: str
    embedding: list[float]


@dataclass
class ScoredChunk:
    document_id: int
    chunk_index: int
    content: str
    score: float


class VectorStore(ABC):
    @abstractmethod
    def upsert_chunks(
        self,
        user_id: int,
        document_id: int,
        generation: int,
        chunks: list[ChunkVector],
    ) -> None:
        raise NotImplementedError

    @abstractmethod
    def search(
        self, user_id: int, query_embedding: list[float], top_k: int
    ) -> list[ScoredChunk]:
        raise NotImplementedError

    @abstractmethod
    def delete_document(self, user_id: int, document_id: int) -> None:
        raise NotImplementedError
