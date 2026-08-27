from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.security import hash_password, verify_password
from app.models.user import User
from app.schemas.auth import RegisterIn


def get_user_by_email(db: Session, email: str) -> User | None:
    return db.scalar(select(User).where(User.email == email))


def get_user_by_username(db: Session, username: str) -> User | None:
    return db.scalar(select(User).where(User.username == username))


def get_user_by_credential(db: Session, credential: str) -> User | None:
    return db.scalar(
        select(User).where(or_(User.username == credential, User.email == credential))
    )


def create_user(db: Session, payload: RegisterIn) -> User:
    user = User(
        email=payload.email,
        username=payload.username,
        hashed_password=hash_password(payload.password),
    )
    db.add(user)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise exc
    db.refresh(user)
    return user


def authenticate_user(db: Session, credential: str, password: str) -> User | None:
    user = get_user_by_credential(db, credential)
    if user is None:
        return None
    if not verify_password(password, user.hashed_password):
        return None
    return user
