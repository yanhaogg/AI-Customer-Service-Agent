"""HTTP 入口：声明路径、输入校验和权限依赖，业务流程及事务见 services。"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.auth.dependencies import get_current_user
from app.database.models import User
from app.database.session import get_db
from app.schemas.user import UserCreate, UserLogin
from app.services import accounts as accounts_service

router = APIRouter()


@router.post("/register", status_code=201)
def register(user: UserCreate, db: Session = Depends(get_db)):
    return accounts_service.register(user, db)


@router.post("/login")
def login(user: UserLogin, db: Session = Depends(get_db)):
    return accounts_service.login(user, db)


@router.get("/me")
def me(user: User = Depends(get_current_user)):
    return accounts_service.me(user)
