from itertools import chain

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.agent.loop import run_agent
from app.agent.registry import build_agent_registry
from app.api.routes.auth import get_current_user
from app.api.routes.conversations import (
    _map_llm_error,
    _sse,
    _stream_error_code,
    _stream_error_message,
)
from app.core.config import settings
from app.db.session import get_db
from app.llm.base import LLMError
from app.llm.factory import get_llm_provider
from app.models.user import User
from app.schemas.agent import AgentRequest
from app.services import conversation as conversation_service

router = APIRouter()


@router.post("/{conversation_id}/agent/stream")
def agent_stream(
    conversation_id: int,
    data: AgentRequest,
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

    stream = run_agent(
        db,
        user_id,
        conversation_id,
        data.content,
        build_agent_registry(),
        get_llm_provider(),
        model=conversation.model,
        max_steps=settings.AGENT_MAX_STEPS,
    )
    try:
        first_event = next(stream)
    except LLMError as exc:
        db.rollback()
        raise _map_llm_error(exc) from exc

    def event_generator():
        yield _sse("start", {"conversation_id": conversation_id, "agent": True})

        committed = False
        try:
            for event in chain((first_event,), stream):
                if event.type == "agent_step":
                    yield _sse("agent_step", {"step": event.step})
                elif event.type == "tool_start":
                    yield _sse(
                        "tool_start",
                        {"tool_call_id": event.tool_call_id, "name": event.name},
                    )
                elif event.type == "tool_result":
                    yield _sse(
                        "tool_result",
                        {
                            "tool_call_id": event.tool_call_id,
                            "name": event.name,
                            "success": event.success,
                            "summary": event.summary,
                        },
                    )
                elif event.type == "delta":
                    yield _sse("delta", {"content": event.content})
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
                elif event.type == "error":
                    yield _sse(
                        "error", {"code": event.code, "message": event.message}
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
