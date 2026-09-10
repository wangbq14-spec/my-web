"""Shared authorization dependencies for Beta routes."""

from fastapi import Depends, HTTPException, status

from app.api.routes.auth import get_current_user
from app.models.user import User


def require_admin(current_user: User = Depends(get_current_user)) -> User:
    if current_user.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin role required")
    return current_user
