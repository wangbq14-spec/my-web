"""Beta admin analytics aggregation.

Every metric is computed with SQLAlchemy 2.0 ``select`` / ``func`` aggregation
so that no prompt, message, document-chunk, step I/O, artifact, or feedback
content is ever loaded or serialized. Only counts, sums, and tier groupings
are returned.
"""

from datetime import datetime, timedelta, timezone

from fastapi import HTTPException
from sqlalchemy import case, func, select, union
from sqlalchemy.orm import Session

from app.models.beta import Feedback, RechargeRequest
from app.models.billing import CreditLedger, UsageRecord
from app.models.conversation import Conversation
from app.models.document import Document, DocumentChunk
from app.models.message import Message
from app.models.project import Project
from app.models.rag_query import RagQuery
from app.models.user import User
from app.models.workflow import StepRun, TaskRun

_RANGE_DAYS = {"7d": 7, "30d": 30, "all": None}


def _since_for(range: str) -> datetime | None:
    days = _RANGE_DAYS[range]
    if days is None:
        return None
    return datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=days)


def overview(db: Session, range: str) -> dict:
    """Aggregate platform-wide metrics for the given time range.

    ``range`` must be one of ``"7d"``, ``"30d"``, or ``"all"``; anything else
    raises ``HTTPException(422, "Invalid range")``. ``"all"`` applies no time
    filter at all. Timestamps are compared against a naive-UTC ``since`` value
    so they line up with the naive-UTC ``created_at`` columns.
    """
    if range not in _RANGE_DAYS:
        raise HTTPException(422, "Invalid range")

    since = _since_for(range)

    def since_filter(column):
        """Range predicate for ``column``; empty (no filter) for ``"all"``."""
        return [] if since is None else [column >= since]

    # Registered is intentionally all-time, not range-filtered.
    registered = db.scalar(select(func.count(User.id))) or 0

    # Active users: distinct user ids seen across message, usage, task-run,
    # and project-activity timestamps in the range. ``Message`` has no
    # ``user_id`` of its own, so it is resolved through its ``Conversation``.
    message_users = (
        select(Conversation.user_id.label("user_id"))
        .join(Message, Message.conversation_id == Conversation.id)
        .where(*since_filter(Message.created_at))
    )
    usage_users = select(UsageRecord.user_id.label("user_id")).where(
        *since_filter(UsageRecord.created_at)
    )
    task_users = select(TaskRun.user_id.label("user_id")).where(
        *since_filter(TaskRun.created_at)
    )
    project_users = select(Project.user_id.label("user_id")).where(
        *since_filter(Project.last_activity_at)
    )
    active_subq = union(message_users, usage_users, task_users, project_users).subquery()
    active_users = db.scalar(
        select(func.count(func.distinct(active_subq.c.user_id)))
    ) or 0

    new_users = db.scalar(
        select(func.count(User.id)).where(*since_filter(User.created_at))
    ) or 0
    chat_messages = db.scalar(
        select(func.count(Message.id)).where(*since_filter(Message.created_at))
    ) or 0
    rag_chunks = db.scalar(
        select(func.count(DocumentChunk.id)).where(*since_filter(DocumentChunk.created_at))
    ) or 0
    # ``StepRun`` has no ``created_at``; its ``started_at`` is the closest
    # "when this step ran" timestamp and is used for range filtering.
    agent_steps = db.scalar(
        select(func.count(StepRun.id)).where(*since_filter(StepRun.started_at))
    ) or 0
    workflows = db.scalar(
        select(func.count(TaskRun.id)).where(*since_filter(TaskRun.created_at))
    ) or 0
    documents = db.scalar(
        select(func.count(Document.id)).where(
            Document.deleted_at.is_(None), *since_filter(Document.created_at)
        )
    ) or 0
    projects = db.scalar(
        select(func.count(Project.id)).where(*since_filter(Project.created_at))
    ) or 0

    granted = db.scalar(
        select(func.coalesce(func.sum(CreditLedger.amount), 0)).where(
            CreditLedger.operation == "grant", *since_filter(CreditLedger.created_at)
        )
    ) or 0
    consumed = db.scalar(
        select(func.coalesce(func.sum(CreditLedger.amount), 0)).where(
            CreditLedger.operation == "consume", *since_filter(CreditLedger.created_at)
        )
    ) or 0

    tier_rows = db.execute(
        select(UsageRecord.model_tier, func.count(UsageRecord.id))
        .where(
            UsageRecord.model_tier.is_not(None), *since_filter(UsageRecord.created_at)
        )
        .group_by(UsageRecord.model_tier)
    ).all()
    model_tier = {tier: count for tier, count in tier_rows}

    feedback = db.scalar(
        select(func.count(Feedback.id)).where(*since_filter(Feedback.created_at))
    ) or 0

    return {
        "range": range,
        "registered": registered,
        "active_users": active_users,
        "new_users": new_users,
        "chat_messages": chat_messages,
        "rag_chunks": rag_chunks,
        "agent_steps": agent_steps,
        "workflows": workflows,
        "documents": documents,
        "projects": projects,
        "credits": {"granted": int(granted), "consumed": int(consumed)},
        "model_tier": model_tier,
        "feedback": feedback,
    }


def _active_user_count(db: Session, since: datetime) -> int:
    """Distinct users active (message / usage / task-run / project) since ``since``."""
    message_users = (
        select(Conversation.user_id.label("user_id"))
        .join(Message, Message.conversation_id == Conversation.id)
        .where(Message.created_at >= since)
    )
    usage_users = select(UsageRecord.user_id.label("user_id")).where(
        UsageRecord.created_at >= since
    )
    task_users = select(TaskRun.user_id.label("user_id")).where(
        TaskRun.created_at >= since
    )
    project_users = select(Project.user_id.label("user_id")).where(
        Project.last_activity_at >= since
    )
    active_subq = union(message_users, usage_users, task_users, project_users).subquery()
    return db.scalar(select(func.count(func.distinct(active_subq.c.user_id)))) or 0


def _count(db: Session, model, column, since: datetime) -> int:
    return db.scalar(select(func.count(model.id)).where(column >= since)) or 0


def _sum_consumed(db: Session, since: datetime) -> int:
    value = db.scalar(
        select(func.coalesce(func.sum(func.abs(CreditLedger.amount)), 0)).where(
            CreditLedger.operation == "consume", CreditLedger.created_at >= since
        )
    )
    return int(value) if value is not None else 0


def admin_overview(db: Session) -> dict:
    """Operations overview for the Beta admin home: today + 7-day + health.

    Aggregations only — no prompt / message / chunk / feedback content is ever
    selected. Metrics that the current data model cannot compute accurately
    (AI error rate, vision error rate) are returned as ``None`` so the UI can
    show them as "not trackable" instead of guessing.
    """
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    since_7d = now - timedelta(days=7)

    def kind_count(since: datetime, *kinds: str) -> int:
        return db.scalar(
            select(func.count(UsageRecord.id)).where(
                UsageRecord.kind.in_(kinds), UsageRecord.created_at >= since
            )
        ) or 0

    # ---- today ----
    documents_today = db.scalar(
        select(func.count(Document.id)).where(
            Document.deleted_at.is_(None), Document.created_at >= today_start
        )
    ) or 0
    pending_recharges = db.scalar(
        select(func.count(RechargeRequest.id)).where(
            RechargeRequest.status == "pending"
        )
    ) or 0
    unreviewed_feedback = db.scalar(
        select(func.count(Feedback.id)).where(Feedback.status == "new")
    ) or 0

    today = {
        "new_users": _count(db, User, User.created_at, today_start),
        "active_users": _active_user_count(db, today_start),
        "chat_requests": kind_count(today_start, "chat"),
        "rag_requests": _count(db, RagQuery, RagQuery.created_at, today_start),
        "agent_requests": kind_count(today_start, "agent", "workflow"),
        "vision_requests": kind_count(today_start, "vision"),
        "documents_uploaded": documents_today,
        "credits_consumed": _sum_consumed(db, today_start),
        "pending_recharge_requests": pending_recharges,
        "new_feedback": _count(db, Feedback, Feedback.created_at, today_start),
        "unreviewed_feedback": unreviewed_feedback,
    }

    # ---- last 7 days ----
    tier_rows = db.execute(
        select(UsageRecord.model_tier, func.count(UsageRecord.id))
        .where(
            UsageRecord.model_tier.is_not(None), UsageRecord.created_at >= since_7d
        )
        .group_by(UsageRecord.model_tier)
    ).all()
    most_used_model_tier = max(tier_rows, key=lambda row: row[1])[0] if tier_rows else None
    vision_rows = db.execute(
        select(func.count(UsageRecord.id), func.coalesce(func.sum(UsageRecord.credits_charged), 0))
        .where(UsageRecord.kind == "vision", UsageRecord.created_at >= since_7d)
    ).one()
    rag_usage = _count(db, RagQuery, RagQuery.created_at, since_7d)

    last_7d = {
        "active_users": _active_user_count(db, since_7d),
        "total_ai_requests": db.scalar(
            select(func.count(UsageRecord.id)).where(UsageRecord.created_at >= since_7d)
        ) or 0,
        "credits_consumed": _sum_consumed(db, since_7d),
        "most_used_model_tier": most_used_model_tier,
        "vision_usage": {
            "requests": int(vision_rows[0] or 0),
            "credits": int(vision_rows[1] or 0),
        },
        "rag_usage": rag_usage,
    }

    # ---- beta health ----
    recent_usage = select(UsageRecord.user_id).where(UsageRecord.created_at >= since_7d)
    recent_tasks = select(TaskRun.user_id).where(TaskRun.created_at >= since_7d)
    recent_projects = select(Project.user_id).where(Project.last_activity_at >= since_7d)
    recent_messages = (
        select(Conversation.user_id)
        .join(Message, Message.conversation_id == Conversation.id)
        .where(Message.created_at >= since_7d)
    )
    returning_users = db.scalar(
        select(func.count(func.distinct(User.id))).where(
            User.created_at < since_7d,
            User.id.in_(
                union(recent_usage, recent_tasks, recent_projects, recent_messages)
            ),
        )
    ) or 0
    terminal_docs = db.execute(
        select(
            func.count(Document.id),
            func.coalesce(
                func.sum(case((Document.status == "ready", 1), else_=0)), 0
            ),
        ).where(
            Document.status.in_(("ready", "failed")),
            Document.created_at >= since_7d,
        )
    ).one()
    doc_total, doc_ready = terminal_docs[0] or 0, terminal_docs[1] or 0

    health = {
        "active_users": last_7d["active_users"],
        "returning_users": returning_users,
        "ai_success_rate": None,  # no failure log in the data model -> deferred
        "ai_error_rate": None,  # no failure log in the data model -> deferred
        "document_success_rate": (
            round(doc_ready / doc_total, 4) if doc_total else None
        ),
        "vision_success_rate": None,  # no failure log in the data model -> deferred
        "credits_consumed": last_7d["credits_consumed"],
    }

    return {
        "generated_at": now.isoformat(),
        "today": today,
        "last_7d": last_7d,
        "health": health,
    }
