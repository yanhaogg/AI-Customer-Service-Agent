from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from sqlalchemy.orm import Session
from app.auth.jwt import ALGORITHM, SECRET_KEY
from app.database.models import User
from app.database.session import get_db

bearer = HTTPBearer(auto_error=False)


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
    db: Session = Depends(get_db),
):
    unauthorized = HTTPException(
        401, "请先登录或重新登录", headers={"WWW-Authenticate": "Bearer"}
    )
    if not credentials or credentials.scheme.lower() != "bearer":
        raise unauthorized
    if not SECRET_KEY:
        raise HTTPException(503, "认证服务未配置")
    try:
        payload = jwt.decode(
            credentials.credentials,
            SECRET_KEY,
            algorithms=[ALGORITHM],
            options={"require_exp": True},
        )
        user_id = payload.get("user_id")
        if type(user_id) is not int or user_id <= 0:
            raise unauthorized
    except JWTError:
        raise unauthorized from None
    user = db.get(User, user_id)
    if user is None:
        raise unauthorized
    return user


def require_superadmin(user: User = Depends(get_current_user)):
    if user.role != "super_admin":
        raise HTTPException(403, "仅超级管理员可以执行此管理操作")
    return user
