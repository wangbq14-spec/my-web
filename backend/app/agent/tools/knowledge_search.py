import json

from pydantic import BaseModel, ConfigDict, Field

from app.agent.base import Tool, ToolContext, ToolResult
from app.core.config import settings
from app.rag.embeddings.base import EmbeddingError
from app.rag.retrieval import retrieve


class KnowledgeSearchInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: str = Field(min_length=1, max_length=5000)
    top_k: int = Field(default=5, ge=1, le=20)


class KnowledgeSearchTool(Tool):
    name = "knowledge_search"
    description = "在当前用户已上传的知识库中检索相关内容。"
    input_schema = KnowledgeSearchInput

    def execute(self, args: KnowledgeSearchInput, context: ToolContext) -> ToolResult:
        try:
            chunks = retrieve(context.session, context.user_id, args.query, args.top_k)
        except EmbeddingError:
            return ToolResult(
                success=False,
                error_code="retrieval_error",
                content="知识库检索失败",
            )

        serialized_chunks: list[dict] = []
        remaining = max(0, settings.RAG_MAX_CONTEXT_CHARS)
        for chunk in chunks:
            if remaining <= 0:
                break
            content = chunk.content[:remaining]
            serialized_chunks.append(
                {
                    "document_id": chunk.document_id,
                    "filename": chunk.filename,
                    "chunk_index": chunk.chunk_index,
                    "content": content,
                    "score": chunk.score,
                }
            )
            remaining -= len(content)
            if len(content) < len(chunk.content):
                break

        return ToolResult(
            success=True,
            content=json.dumps(serialized_chunks, ensure_ascii=False),
            data={"chunks": serialized_chunks},
        )
