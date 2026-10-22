"""用户注册、登录与身份信息用例，密码和 JWT 算法仍由 auth 包提供。

业务用例管理事务；HTTP 参数解析与路由声明见对应 api 模块。
"""

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from app.auth.jwt import create_access_token
from app.auth.password import hash_password, verify_password
from app.database.models import User


def user_info(user):
    return {"id": user.id, "username": user.username, "role": user.role}


def register(user, db):
    if db.scalar(select(User).where(User.username == user.username).limit(1)):
        raise HTTPException(400, "用户名已存在")
    # Never accept role/permissions from the public registration body.
    created = User(
        username=user.username, password_hash=hash_password(user.password), role="user"
    )
    db.add(created)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            400, "用户名已存在"
        ) from None  # from None 抑制异常链，让最终对外暴露的错误就是干净的 HTTPException(400)，避免把数据库细节（表名、约束名、SQL）泄露给客户端，也避免 FastAPI 日志里出现一长串内部异常。
    return {"message": "注册成功", "user_id": created.id}


def login(user, db):
    stored = db.scalar(
        select(User).where(User.username == user.username.strip()).limit(1)
    )
    if stored is None or not verify_password(user.password, stored.password_hash):
        raise HTTPException(401, "用户名或密码错误")
    return {
        "access_token": create_access_token({"user_id": stored.id}),
        "token_type": "bearer",
        "user": user_info(stored),
    }


def me(user):
    return user_info(user)
