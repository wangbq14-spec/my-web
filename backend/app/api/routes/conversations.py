from fastapi import APIRouter, Depends, HTTPException, Response, status
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
from app.schemas.chat import ChatRequest, ChatResponse
from app.schemas.conversation import ConversationCreate, ConversationOut
from app.schemas.message import MessageCreate, MessageOut
from app.services import chat as chat_service
from app.services import conversation as conversation_service
from app.services import message as message_service

router = APIRouter()


@router.post("", response_model=ConversationOut, status_code=status.HTTP_201_CREATED)
def create_conversation(
    data: ConversationCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ConversationOut:
    conversation = conversation_service.create_conversation(
        session=db,
        user_id=current_user.id,
        data=data,
    )
    db.commit()
    return conversation


@router.get("", response_model=list[ConversationOut])
def list_conversations(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[ConversationOut]:
    return conversation_service.list_conversations(
        session=db,
        user_id=current_user.id,
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
        )
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

    return ChatResponse(user_message=user_message, assistant_message=assistant_message)
