import jwt
import logging
from uuid import uuid4
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.security import create_access_token, decode_access_token, hash_password
from app.db.session import get_db
from app.models.user import User
from app.core.config import settings
from app.schemas.auth import LoginIn, RegisterIn as BaseRegisterIn, TokenOut
from app.schemas.user import UserOut
from app.services import auth as auth_service
from app.services import billing as billing_service
from app.services.invite import validate_and_consume_invite_code
logger = logging.getLogger(__name__)

router = APIRouter()
bearer_scheme = HTTPBearer(auto_error=False)

UNAUTHORIZED_HEADERS = {"WWW-Authenticate": "Bearer"}


class RegisterIn(BaseRegisterIn):
    invite_code: str | None = Field(default=None, max_length=64)
    referral_code: str | None = Field(default=None, max_length=64)


def _new_referral_code(db: Session) -> str:
    while True:
        code = f"OMNIXA-{uuid4().hex.upper()}"
        if db.scalar(select(User.id).where(User.referral_code == code)) is None:
            return code


def _grant_registration_credits(db: Session, user: User) -> None:
    """Called only after a new registration commits; stable keys permit retries."""
    user_id = user.id
    inviter_id = user.referred_by_user_id
    try:
        billing_service.create_wallet_if_missing(db, user_id)
        billing_service.grant_credit(
            db, user_id, settings.BETA_REGISTER_CREDITS,
            description="Classroom Beta 注册赠送", request_id=f"beta-register-{user_id}",
        )
        if inviter_id is not None and inviter_id != user_id:
            if settings.REFERRAL_REWARD_CREDITS > 0:
                billing_service.grant_credit(
                    db, inviter_id, settings.REFERRAL_REWARD_CREDITS,
                    description="Referral 邀请奖励", request_id=f"referral-reward-{user_id}",
                )
            if settings.REFERRAL_NEW_USER_CREDITS > 0:
                billing_service.grant_credit(
                    db, user_id, settings.REFERRAL_NEW_USER_CREDITS,
                    description="Referral 新用户奖励", request_id=f"referral-new-user-{user_id}",
                )
        db.commit()
    except Exception:
        db.rollback()
        logger.exception("failed to grant beta/referral credits user_id=%s", user_id)


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    db: Session = Depends(get_db),
    request: Request = None,
) -> User:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="未提供有效的认证信息",
            headers=UNAUTHORIZED_HEADERS,
        )

    try:
        payload = decode_access_token(credentials.credentials)
    except jwt.InvalidTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="token 无效或已过期",
            headers=UNAUTHORIZED_HEADERS,
        )

    sub = payload.get("sub")
    if not sub:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="token 无效",
            headers=UNAUTHORIZED_HEADERS,
        )

    try:
        user_id = int(sub)
    except (TypeError, ValueError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="token 无效",
            headers=UNAUTHORIZED_HEADERS,
        )

    user = db.get(User, user_id)
    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户不存在或已禁用",
            headers=UNAUTHORIZED_HEADERS,
        )

    # Attribute the request to the authenticated user for structured access logs.
    if request is not None:
        request.state.user_id = user.id

    return user


@router.post("/register", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def register(payload: RegisterIn, db: Session = Depends(get_db)) -> User:
    existing_email = auth_service.get_user_by_email(db, payload.email)
    existing_username = auth_service.get_user_by_username(db, payload.username)
    inviter = None
    if payload.referral_code is not None:
        inviter = db.scalar(select(User).where(User.referral_code == payload.referral_code.strip()))
        if inviter is None:
            raise HTTPException(status_code=400, detail="推荐码无效")
    if existing_email:
        raise HTTPException(status_code=400, detail="邮箱已被注册")
    if existing_username:
        raise HTTPException(status_code=400, detail="用户名已被占用")

    try:
        # A provided invite code is always validated and consumed (invite
        # codes stay controllable even when registration is not gated).
        if payload.invite_code and payload.invite_code.strip():
            validate_and_consume_invite_code(db, payload.invite_code)
        elif settings.INVITE_REQUIRED:
            raise HTTPException(status_code=400, detail="请输入邀请码")
        user = User(
            email=payload.email, username=payload.username,
            hashed_password=hash_password(payload.password),
            referral_code=_new_referral_code(db),
            referred_by_user_id=inviter.id if inviter is not None else None,
        )
        db.add(user)
        db.flush()
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="邮箱或用户名已存在")
    except Exception:
        db.rollback()
        raise

    _grant_registration_credits(db, user)
    return user


@router.post("/login", response_model=TokenOut)
def login(payload: LoginIn, db: Session = Depends(get_db)) -> TokenOut:
    user = auth_service.authenticate_user(db, payload.username, payload.password)
    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户名或密码错误",
            headers=UNAUTHORIZED_HEADERS,
        )

    token = create_access_token(subject=str(user.id))
    return TokenOut(access_token=token, token_type="bearer")


@router.get("/me", response_model=UserOut)
def get_me(current_user: User = Depends(get_current_user)) -> User:
    return current_user
