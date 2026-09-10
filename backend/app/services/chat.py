from dataclasses import dataclass, field
from typing import Iterator, Literal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.llm.base import ImagePart, LLMError, LLMMessage, LLMResponse, LLMUsage
from app.llm.factory import get_llm_provider, get_vision_provider
from app.llm.registry import ModelTier, resolve_model, get_model_registry
from app.models.message import Message
from app.models.user import utcnow_naive
from app.rag.context import Citation, build_citations, build_rag_system_prompt
from app.rag.embeddings.base import EmbeddingError
from app.rag.retrieval import retrieve
from app.services.conversation import get_conversation
from app.services.project import (
    _PROJECT_SYSTEM_SAFETY_PROMPT,
    append_project_instructions,
    build_project_system_prompt,
    touch_project_activity,
)
from app.services.title import maybe_auto_title
from app.services.billing import charge_response, consume_credit, credits_from_cost, estimate_cost, require_balance
from app.services.attachments import validate_attachments, bind_attachments, build_messages


def _estimate_required_credits(messages, tier) -> int:
    """Worst-case credits for the upcoming turn (P1-2 TOCTOU guard).

    Pre-authorize before calling the provider so a low balance fails fast with
    402 instead of burning provider tokens and only then discovering the charge
    exceeds the balance. Prompt tokens are estimated from character count;
    completion uses a configured worst-case budget. Always at least 1.
    """
    prompt_chars = sum(len(m.content or "") for m in messages)
    prompt_tokens = max(1, prompt_chars // 4)
    cost = estimate_cost(prompt_tokens, settings.CHAT_COMPLETION_BUDGET_TOKENS, tier)
    return max(1, credits_from_cost(cost))


def _select_provider(session, user_id, messages, tier, explicit_model):
    image_count = sum(isinstance(part, ImagePart)
                      for message in messages for part in (message.content_parts or []))
    require_balance(session, user_id, _estimate_required_credits(messages, tier))
    if not image_count:
        return get_llm_provider(), resolve_model(tier, explicit_model), None
    registry = get_model_registry()
    # Server-authoritative vision tier: if the requested tier has no vision
    # capability, upgrade to the configured vision tier instead of failing.
    effective_tier = tier
    if not registry.capabilities(effective_tier).get("vision", False):
        effective_tier = settings.VISION_MODEL_TIER
    provider_label, model = registry.resolve_for(capability="vision", tier=effective_tier)
    require_balance(session, user_id, max(1, settings.VISION_BASE_CREDIT_COST))
    provider = get_vision_provider(provider_label)
    return provider, model, provider_label


def _charge_chat(session, user_id, response, tier, description, vision_provider=None):
    kind = "vision" if vision_provider else "chat"
    if vision_provider is None:
        # Text: mirror the vision floor so a provider that omits streaming usage
        # (OpenAI-compatible fallback without include_usage) still charges the
        # per-request minimum — text is never free.
        floor = max(1, settings.CHAT_BASE_CREDIT_COST)
        billed = response
        if response.usage is None:
            billed = response.model_copy(update={
                "usage": LLMUsage(prompt_tokens=0, completion_tokens=0, total_tokens=0),
            })
        record = charge_response(session, user_id, billed, tier, description, kind=kind)
        if record is not None and record.credits_charged < floor:
            extra = floor - record.credits_charged
            consume_credit(session, user_id, extra, record.request_id + ":chat-floor",
                           "Chat minimum charge")
            record.credits_charged = floor
            session.flush()
        return record
    # OpenAI-compatible usage has no portable, reliable image-token breakdown.
    # Bill real tokens unchanged, then apply a per-request (not per-image) floor.
    # Missing usage is recorded as zero measured tokens, never fabricated tokens.
    billed = response.model_copy(update={
        "provider": vision_provider,
        "usage": response.usage or LLMUsage(prompt_tokens=0, completion_tokens=0, total_tokens=0),
    })
    record = charge_response(session, user_id, billed, tier, description, kind=kind)
    floor = max(1, settings.VISION_BASE_CREDIT_COST)
    if record is not None and record.credits_charged < floor:
        extra = floor - record.credits_charged
        consume_credit(session, user_id, extra, record.request_id + ":vision-floor",
                       "Vision minimum charge")
        record.credits_charged = floor
        session.flush()
    return record


@dataclass
class ChatResult:
    user_message: Message
    assistant_message: Message
    sources: list[Citation] = field(default_factory=list)


def _retrieve_for_conversation(
    session: Session,
    user_id: int,
    content: str,
    top_k: int,
    project_id: int | None,
):
    if project_id is None:
        return retrieve(session, user_id, content, top_k)
    return retrieve(session, user_id, content, top_k, project_id=project_id)


def _build_rag_prompt(content: str, retrieved, project_instructions: str | None) -> str:
    """Keep global safety ahead of RAG evidence and supplementary project rules."""
    rag_prompt = f"{_PROJECT_SYSTEM_SAFETY_PROMPT}\n\n{build_rag_system_prompt(content, retrieved)}"
    return append_project_instructions(rag_prompt, project_instructions)


def send_chat_message(
    session: Session,
    user_id: int,
    conversation_id: int,
    content: str,
    use_rag: bool = False,
    top_k: int = 5,
    model_tier: ModelTier = "auto",
    attachment_ids: list[int] | None = None,
) -> ChatResult | None:
    conversation = get_conversation(session, user_id, conversation_id)
    if conversation is None:
        return None

    # Image-only messages have no query to retrieve against; never embed "".
    use_rag = use_rag and bool(content.strip())

    attachments = validate_attachments(session, user_id, conversation_id, attachment_ids)
    user_message = Message(
        conversation_id=conversation_id,
        role="user",
        content=content,
        model=None,
    )
    session.add(user_message)
    session.flush()
    # NB: no session.refresh(user_message) here — refresh before the bulk
    # bind UPDATE marks the selectin attachments relationship as loaded-empty.
    bind_attachments(session, user_id, conversation_id, user_message.id, attachments)

    history = (
        session.execute(
            select(Message)
            .where(Message.conversation_id == conversation_id)
            .order_by(Message.created_at.asc(), Message.id.asc())
        )
        .scalars()
        .all()
    )

    llm_messages = build_messages(session, user_id, history)
    sources: list[Citation] = []
    if use_rag:
        retrieved = _retrieve_for_conversation(
            session, user_id, content, top_k, conversation.project_id
        )
        llm_messages = [
            LLMMessage(
                role="system",
                content=_build_rag_prompt(
                    content,
                    retrieved,
                    conversation.project.instructions if conversation.project else None,
                ),
            )
        ] + llm_messages
        sources = build_citations(retrieved)
    elif (system_prompt := build_project_system_prompt(
        conversation.project.instructions if conversation.project else None
    )) is not None:
        llm_messages = [LLMMessage(role="system", content=system_prompt)] + llm_messages

    provider, resolved_model, vision_provider = _select_provider(
        session, user_id, llm_messages, model_tier, conversation.model)
    response = provider.complete(llm_messages, model=resolved_model)

    assistant_message = Message(
        conversation_id=conversation_id,
        role="assistant",
        content=response.content,
        model=response.model or resolved_model,
    )
    session.add(assistant_message)
    session.flush()
    session.refresh(assistant_message)
    if vision_provider:
        response = response.model_copy(update={"model": response.model or resolved_model})
    _charge_chat(session, user_id, response, model_tier, "chat", vision_provider)

    conversation.updated_at = utcnow_naive()
    session.flush()
    maybe_auto_title(conversation, content)
    if conversation.project_id is not None:
        touch_project_activity(session, conversation.project_id)

    return ChatResult(
        user_message=user_message,
        assistant_message=assistant_message,
        sources=sources,
    )


@dataclass
class StreamEvent:
    type: Literal[
        "delta", "done", "not_found", "no_user_message", "sources", "retrieval_error"
    ]
    content: str | None = None
    user_message_id: int | None = None
    assistant_message_id: int | None = None
    model: str | None = None
    sources: list[Citation] | None = None


def stream_chat_message(
    session: Session,
    user_id: int,
    conversation_id: int,
    content: str,
    use_rag: bool = False,
    top_k: int = 5,
    model_tier: ModelTier = "auto",
    attachment_ids: list[int] | None = None,
) -> Iterator[StreamEvent]:
    conversation = get_conversation(session, user_id, conversation_id)
    if conversation is None:
        yield StreamEvent(type="not_found")
        return

    # Image-only messages have no query to retrieve against; never embed "".
    use_rag = use_rag and bool(content.strip())

    retrieved = []
    citations: list[Citation] = []
    if use_rag:
        try:
            retrieved = _retrieve_for_conversation(
                session, user_id, content, top_k, conversation.project_id
            )
        except EmbeddingError:
            yield StreamEvent(type="retrieval_error")
            return
        citations = build_citations(retrieved)

    attachments = validate_attachments(session, user_id, conversation_id, attachment_ids)
    user_message = Message(
        conversation_id=conversation_id,
        role="user",
        content=content,
        model=None,
    )
    session.add(user_message)
    session.flush()
    # NB: no session.refresh(user_message) here — refresh before the bulk
    # bind UPDATE marks the selectin attachments relationship as loaded-empty.
    bind_attachments(session, user_id, conversation_id, user_message.id, attachments)

    history = (
        session.execute(
            select(Message)
            .where(Message.conversation_id == conversation_id)
            .order_by(Message.created_at.asc(), Message.id.asc())
        )
        .scalars()
        .all()
    )

    llm_messages = build_messages(session, user_id, history)
    if use_rag:
        llm_messages = [
            LLMMessage(
                role="system",
                content=_build_rag_prompt(
                    content,
                    retrieved,
                    conversation.project.instructions if conversation.project else None,
                ),
            )
        ] + llm_messages
    elif (system_prompt := build_project_system_prompt(
        conversation.project.instructions if conversation.project else None
    )) is not None:
        llm_messages = [LLMMessage(role="system", content=system_prompt)] + llm_messages

    provider, resolved_model, vision_provider = _select_provider(
        session, user_id, llm_messages, model_tier, conversation.model)

    if use_rag:
        yield StreamEvent(type="sources", sources=citations)

    chunks: list[str] = []
    actual_model: str | None = None
    usage = None
    for chunk in provider.stream(llm_messages, model=resolved_model):
        if chunk.model:
            actual_model = chunk.model
        if chunk.usage is not None:
            usage = chunk.usage
        if chunk.content:
            chunks.append(chunk.content)
            if chunk.model:
                actual_model = chunk.model
            yield StreamEvent(type="delta", content=chunk.content)

    full_content = "".join(chunks)
    if not full_content.strip():
        raise LLMError("上游返回空内容")

    assistant_message = Message(
        conversation_id=conversation_id,
        role="assistant",
        content=full_content,
        model=actual_model or resolved_model,
    )
    session.add(assistant_message)
    session.flush()
    session.refresh(assistant_message)
    _charge_chat(session, user_id, LLMResponse(
        model=assistant_message.model, provider=getattr(provider, "name", None),
        usage=usage), model_tier, "chat stream", vision_provider)

    conversation.updated_at = utcnow_naive()
    session.flush()
    maybe_auto_title(conversation, content)
    if conversation.project_id is not None:
        touch_project_activity(session, conversation.project_id)

    yield StreamEvent(
        type="done",
        user_message_id=user_message.id,
        assistant_message_id=assistant_message.id,
        model=assistant_message.model,
    )


def regenerate_chat_message(
    session: Session,
    user_id: int,
    conversation_id: int,
    use_rag: bool = False,
    top_k: int = 5,
    model_tier: ModelTier = "auto",
) -> Iterator[StreamEvent]:
    conversation = get_conversation(session, user_id, conversation_id)
    if conversation is None:
        yield StreamEvent(type="not_found")
        return

    messages = (
        session.execute(
            select(Message)
            .where(Message.conversation_id == conversation_id)
            .order_by(Message.created_at.asc(), Message.id.asc())
        )
        .scalars()
        .all()
    )
    last_user_index = next(
        (index for index in range(len(messages) - 1, -1, -1) if messages[index].role == "user"),
        None,
    )
    if last_user_index is None:
        yield StreamEvent(type="no_user_message")
        return

    context = messages[: last_user_index + 1]
    llm_messages = build_messages(session, user_id, context)
    last_user_content = context[-1].content
    # Image-only messages have no query to retrieve against; never embed "".
    use_rag = use_rag and bool(last_user_content.strip())
    if use_rag:
        try:
            retrieved = _retrieve_for_conversation(
                session,
                user_id,
                last_user_content,
                top_k,
                conversation.project_id,
            )
        except EmbeddingError:
            yield StreamEvent(type="retrieval_error")
            return
        llm_messages = [
            LLMMessage(
                role="system",
                content=_build_rag_prompt(
                    last_user_content,
                    retrieved,
                    conversation.project.instructions if conversation.project else None,
                ),
            )
        ] + llm_messages
        yield StreamEvent(type="sources", sources=build_citations(retrieved))
    elif (system_prompt := build_project_system_prompt(
        conversation.project.instructions if conversation.project else None
    )) is not None:
        llm_messages = [LLMMessage(role="system", content=system_prompt)] + llm_messages
    provider, resolved_model, vision_provider = _select_provider(
        session, user_id, llm_messages, model_tier, conversation.model)

    chunks: list[str] = []
    actual_model: str | None = None
    usage = None
    for chunk in provider.stream(llm_messages, model=resolved_model):
        if chunk.model:
            actual_model = chunk.model
        if chunk.usage is not None:
            usage = chunk.usage
        if chunk.content:
            chunks.append(chunk.content)
            if chunk.model:
                actual_model = chunk.model
            yield StreamEvent(type="delta", content=chunk.content)

    full_content = "".join(chunks)
    if not full_content.strip():
        raise LLMError("上游返回空内容")

    assistant_message = Message(
        conversation_id=conversation_id,
        role="assistant",
        content=full_content,
        model=actual_model or resolved_model,
    )
    session.add(assistant_message)
    session.flush()
    session.refresh(assistant_message)
    _charge_chat(session, user_id, LLMResponse(
        model=assistant_message.model, provider=getattr(provider, "name", None),
        usage=usage), model_tier, "chat regenerate", vision_provider)

    conversation.updated_at = utcnow_naive()
    session.flush()
    if conversation.project_id is not None:
        touch_project_activity(session, conversation.project_id)

    yield StreamEvent(
        type="done",
        assistant_message_id=assistant_message.id,
        model=assistant_message.model,
    )
