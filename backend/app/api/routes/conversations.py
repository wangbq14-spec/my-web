import json
from itertools import chain

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from fastapi.responses import StreamingResponse
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.api.routes.auth import get_current_user
from app.db.session import get_db
from app.llm.base import (
    LLMConfigurationError,
    LLMError,
    LLMTimeoutError,
    LLMUpstreamError,
)
from app.models.user import User
from app.rag.embeddings.base import EmbeddingError
from app.schemas.chat import ChatRequest, ChatResponse, CitationOut
from app.schemas.conversation import ConversationCreate, ConversationOut, ConversationUpdate
from app.schemas.message import MessageCreate, MessageOut
from app.services import chat as chat_service
from app.services import conversation as conversation_service
from app.services import message as message_service

router = APIRouter()


def _project_not_found() -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="项目不存在")


@router.post("", response_model=ConversationOut, status_code=status.HTTP_201_CREATED)
def create_conversation(
    data: ConversationCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ConversationOut:
    try:
        conversation = conversation_service.create_conversation(
            session=db,
            user_id=current_user.id,
            data=data,
        )
        db.commit()
        db.refresh(conversation)
    except conversation_service.ProjectNotFoundError as exc:
        db.rollback()
        raise _project_not_found() from exc
    except SQLAlchemyError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="会话创建失败"
        ) from exc
    return conversation


@router.get("", response_model=list[ConversationOut])
def list_conversations(
    project_id: int | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[ConversationOut]:
    if project_id is not None:
        from app.services import project as project_service

        if project_service.get_project(db, current_user, project_id) is None:
            raise _project_not_found()
    return conversation_service.list_conversations(
        session=db,
        user_id=current_user.id,
        project_id=project_id,
    )


@router.get("/{conversation_id}", response_model=ConversationOut)
def get_conversation(
    conversation_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ConversationOut:
    conversation = conversation_service.get_conversation(
        session=db,
        user_id=current_user.id,
        conversation_id=conversation_id,
    )
    if conversation is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="会话不存在",
        )
    return conversation


@router.patch("/{conversation_id}", response_model=ConversationOut)
def update_conversation(
    conversation_id: int,
    data: ConversationUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ConversationOut:
    if not data.model_fields_set:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="至少提供一个要更新的字段",
        )
    try:
        conversation = conversation_service.update_conversation(
            session=db,
            user_id=current_user.id,
            conversation_id=conversation_id,
            data=data,
        )
        if conversation is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="会话不存在",
            )
        if "pinned" in data.model_fields_set:
            conversation.pinned = data.pinned
            db.flush()
        db.commit()
        db.refresh(conversation)
    except conversation_service.ProjectNotFoundError as exc:
        db.rollback()
        raise _project_not_found() from exc
    except SQLAlchemyError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="会话更新失败"
        ) from exc
    return conversation


@router.delete("/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_conversation(
    conversation_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Response:
    deleted = conversation_service.delete_conversation(
        session=db,
        user_id=current_user.id,
        conversation_id=conversation_id,
    )
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="会话不存在",
        )
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/{conversation_id}/messages",
    response_model=MessageOut,
    status_code=status.HTTP_201_CREATED,
)
def create_message(
    conversation_id: int,
    data: MessageCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> MessageOut:
    message = message_service.create_user_message(
        session=db,
        user_id=current_user.id,
        conversation_id=conversation_id,
        data=data,
    )
    if message is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="会话不存在",
        )
    db.commit()
    return message


@router.get("/{conversation_id}/messages", response_model=list[MessageOut])
def list_messages(
    conversation_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[MessageOut]:
    messages = message_service.list_messages(
        session=db,
        user_id=current_user.id,
        conversation_id=conversation_id,
    )
    if messages is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="会话不存在",
        )
    return messages


def _map_llm_error(exc: LLMError) -> HTTPException:
    if isinstance(exc, LLMConfigurationError):
        return HTTPException(status_code=503, detail="LLM 服务未配置")
    if isinstance(exc, LLMTimeoutError):
        return HTTPException(status_code=504, detail="LLM 请求超时")
    if isinstance(exc, LLMUpstreamError):
        return HTTPException(status_code=502, detail="LLM 上游服务错误")
    return HTTPException(status_code=502, detail="LLM 服务错误")


@router.post(
    "/{conversation_id}/chat",
    response_model=ChatResponse,
    status_code=status.HTTP_201_CREATED,
)
def chat(
    conversation_id: int,
    data: ChatRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ChatResponse:
    try:
        result = chat_service.send_chat_message(
            session=db,
            user_id=current_user.id,
            conversation_id=conversation_id,
            content=data.content,
            use_rag=data.use_rag,
            top_k=data.top_k,
        )
    except EmbeddingError as exc:
        db.rollback()
        raise HTTPException(status_code=502, detail="知识库检索失败，请稍后重试") from exc
    except LLMError as exc:
        db.rollback()
        raise _map_llm_error(exc) from exc

    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="会话不存在",
        )

    user_message = MessageOut.model_validate(result.user_message)
    assistant_message = MessageOut.model_validate(result.assistant_message)

    db.commit()

    return ChatResponse(
        user_message=user_message,
        assistant_message=assistant_message,
        sources=[CitationOut.model_validate(citation) for citation in result.sources],
    )


def _sse(event: str, payload: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"


def _stream_error_code(exc: LLMError) -> str:
    if isinstance(exc, LLMConfigurationError):
        return "configuration_error"
    if isinstance(exc, LLMTimeoutError):
        return "timeout"
    if isinstance(exc, LLMUpstreamError):
        return "upstream_error"
    return "llm_error"


def _stream_error_message(exc: LLMError) -> str:
    if isinstance(exc, LLMConfigurationError):
        return "LLM 服务未配置"
    if isinstance(exc, LLMTimeoutError):
        return "LLM 请求超时"
    if isinstance(exc, LLMUpstreamError):
        return "LLM 上游服务错误"
    return "LLM 服务错误"


@router.post("/{conversation_id}/chat/stream")
def chat_stream(
    conversation_id: int,
    data: ChatRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> StreamingResponse:
    user_id = current_user.id
    content = data.content
    use_rag = data.use_rag
    top_k = data.top_k

    conversation = conversation_service.get_conversation(db, user_id, conversation_id)
    if conversation is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="会话不存在",
        )

    stream = chat_service.stream_chat_message(
        session=db,
        user_id=user_id,
        conversation_id=conversation_id,
        content=content,
        use_rag=use_rag,
        top_k=top_k,
    )
    try:
        first_event = next(stream)
    except LLMError as exc:
        db.rollback()
        raise _map_llm_error(exc) from exc

    def event_generator():
        yield _sse("start", {"conversation_id": conversation_id})

        committed = False
        try:
            for event in chain((first_event,), stream):
                if event.type == "delta":
                    yield _sse("delta", {"content": event.content})
                elif event.type == "sources":
                    yield _sse(
                        "sources",
                        {
                            "sources": [
                                CitationOut.model_validate(citation).model_dump()
                                for citation in (event.sources or [])
                            ]
                        },
                    )
                elif event.type == "retrieval_error":
                    yield _sse(
                        "error",
                        {
                            "code": "retrieval_error",
                            "message": "知识库检索失败，请稍后重试",
                        },
                    )
                elif event.type == "done":
                    db.commit()
                    committed = True
                    yield _sse(
                        "done",
                        {
                            "user_message_id": event.user_message_id,
                            "assistant_message_id": event.assistant_message_id,
                            "model": event.model,
                        },
                    )
                elif event.type == "not_found":
                    yield _sse(
                        "error", {"code": "not_found", "message": "会话不存在"}
                    )
        except LLMError as exc:
            yield _sse(
                "error",
                {
                    "code": _stream_error_code(exc),
                    "message": _stream_error_message(exc),
                },
            )
        finally:
            if not committed:
                db.rollback()

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache"},
    )


@router.post("/{conversation_id}/regenerate/stream")
def regenerate_stream(
    conversation_id: int,
    use_rag: bool = False,
    top_k: int = Query(default=5, ge=1, le=20),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> StreamingResponse:
    user_id = current_user.id
    conversation = conversation_service.get_conversation(db, user_id, conversation_id)
    if conversation is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="会话不存在",
        )

    stream = chat_service.regenerate_chat_message(
        db,
        user_id,
        conversation_id,
        use_rag=use_rag,
        top_k=top_k,
    )
    try:
        first_event = next(stream)
    except LLMError as exc:
        db.rollback()
        raise _map_llm_error(exc) from exc

    def event_generator():
        yield _sse("start", {"conversation_id": conversation_id})

        committed = False
        try:
            for event in chain((first_event,), stream):
                if event.type == "delta":
                    yield _sse("delta", {"content": event.content})
                elif event.type == "sources":
                    yield _sse(
                        "sources",
                        {
                            "sources": [
                                CitationOut.model_validate(citation).model_dump()
                                for citation in (event.sources or [])
                            ]
                        },
                    )
                elif event.type == "retrieval_error":
                    yield _sse(
                        "error",
                        {
                            "code": "retrieval_error",
                            "message": "知识库检索失败，请稍后重试",
                        },
                    )
                elif event.type == "done":
                    db.commit()
                    committed = True
                    yield _sse(
                        "done",
                        {
                            "assistant_message_id": event.assistant_message_id,
                            "model": event.model,
                        },
                    )
                elif event.type == "no_user_message":
                    yield _sse(
                        "error",
                        {"code": "no_user_message", "message": "没有可重新生成的用户消息"},
                    )
                elif event.type == "not_found":
                    yield _sse("error", {"code": "not_found", "message": "会话不存在"})
        except LLMError as exc:
            yield _sse(
                "error",
                {
                    "code": _stream_error_code(exc),
                    "message": _stream_error_message(exc),
                },
            )
        finally:
            if not committed:
                db.rollback()

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache"},
    )
