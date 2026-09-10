from fastapi import APIRouter

from app.api.routes import (
    admin,
    analytics,
    me_recharge,
    attachments,
    feedback,
    invite,
    agent,
    auth,
    billing,
    conversations,
    documents,
    models,
    projects,
    retrieval,
    workflows,
)

api_router = APIRouter()
api_router.include_router(invite.router, prefix="/invite", tags=["invite"])
api_router.include_router(admin.router, prefix="/admin", tags=["admin"])
api_router.include_router(feedback.router, prefix="/feedback", tags=["feedback"])
api_router.include_router(attachments.router, prefix="/chat/attachments", tags=["attachments"])
api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(billing.router, prefix="/me", tags=["billing"])
api_router.include_router(
    conversations.router, prefix="/conversations", tags=["conversations"]
)
api_router.include_router(agent.router, prefix="/conversations", tags=["agent"])
api_router.include_router(documents.router, prefix="/documents", tags=["documents"])
api_router.include_router(projects.router, prefix="/projects", tags=["projects"])
api_router.include_router(retrieval.router, prefix="/retrieval", tags=["retrieval"])
api_router.include_router(models.router, prefix="/models", tags=["models"])
api_router.include_router(workflows.router, prefix="/tasks", tags=["tasks"])
api_router.include_router(analytics.router, prefix="/admin/analytics", tags=["admin"])

api_router.include_router(me_recharge.router, prefix="/me", tags=["recharge"])
