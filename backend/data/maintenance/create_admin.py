"""Securely create or promote the first (or an additional) admin account.

Role is written explicitly (``role="admin"``) and is NEVER inferred from the
username string, so an account named ``admin`` with role ``user`` stays a
normal user. Reuses the same password hashing as the auth flow.

Run (interactive, no shell history):
    uv run python data/maintenance/create_admin.py --email admin@example.com --username admin

Non-interactive (automation; password read from the environment, never echoed):
    OMNIXA_ADMIN_PASSWORD=... uv run python data/maintenance/create_admin.py \
        --email admin@example.com --username admin --password-env OMNIXA_ADMIN_PASSWORD

Never prints the password.
"""
import argparse
import getpass
import os
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[2]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from sqlalchemy import select  # noqa: E402

from app.core.security import hash_password  # noqa: E402
from app.db.session import SessionLocal  # noqa: E402
from app.models.user import User  # noqa: E402

MIN_PASSWORD_LENGTH = 12


def read_password(args) -> str:
    if args.password:
        password = args.password
    elif args.password_env:
        password = os.environ.get(args.password_env, "")
        if not password:
            raise SystemExit(f"环境变量 {args.password_env} 为空")
    else:
        password = getpass.getpass("管理员密码（不回显）：")
        confirm = getpass.getpass("再次输入确认：")
        if password != confirm:
            raise SystemExit("两次输入不一致")
    if len(password) < MIN_PASSWORD_LENGTH:
        raise SystemExit(f"密码长度至少 {MIN_PASSWORD_LENGTH} 位")
    return password


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Create or promote an admin account")
    parser.add_argument("--email", required=True, help="管理员邮箱（唯一键）")
    parser.add_argument("--username", required=True, help="管理员登录名（唯一键）")
    parser.add_argument(
        "--password",
        help="明文密码（仅供自动化；交互式请勿使用，避免写入 shell 历史）",
    )
    parser.add_argument("--password-env", help="从该环境变量读取密码（不回显）")
    args = parser.parse_args(argv)

    email = args.email.strip().lower()
    username = args.username.strip()
    if not email or not username:
        raise SystemExit("email 与 username 不能为空")
    password = read_password(args)

    with SessionLocal() as db:
        user = db.scalars(select(User).where(User.email == email)).first()
        clash = db.scalars(select(User).where(User.username == username)).first()
        if clash is not None and (user is None or clash.id != user.id):
            raise SystemExit(f"用户名 {username} 已被占用")

        if user is None:
            user = User(
                email=email,
                username=username,
                hashed_password=hash_password(password),
                role="admin",
            )
            db.add(user)
            action = "created"
        else:
            user.username = username
            user.hashed_password = hash_password(password)
            user.role = "admin"
            user.is_active = True
            action = "promoted"
        db.commit()
        print(
            f"ADMIN_{action.upper()} id={user.id} email={email} "
            f"username={username} role={user.role}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
