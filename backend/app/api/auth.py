from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from app.auth.dependencies import get_current_user
from app.auth.jwt import create_access_token
from app.auth.password import hash_password, verify_password
from app.database.models import User
from app.database.session import get_db
from app.schemas.user import UserCreate, UserLogin

router = APIRouter()


def user_info(user):
    return {"id": user.id, "username": user.username, "role": user.role}


@router.post("/register", status_code=201)
def register(user: UserCreate, db: Session = Depends(get_db)):
    if db.query(User).filter(User.username == user.username).first():
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
        raise HTTPException(400, "用户名已存在") from None
    return {"message": "注册成功", "user_id": created.id}


@router.post("/login")
def login(user: UserLogin, db: Session = Depends(get_db)):
    stored = db.query(User).filter(User.username == user.username.strip()).first()
    if stored is None or not verify_password(user.password, stored.password_hash):
        raise HTTPException(401, "用户名或密码错误")
    return {
        "access_token": create_access_token({"user_id": stored.id}),
        "token_type": "bearer",
        "user": user_info(stored),
    }


@router.get("/me")
def me(user: User = Depends(get_current_user)):
    return user_info(user)
