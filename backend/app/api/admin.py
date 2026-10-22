"""HTTP 入口：声明路径、输入校验和权限依赖，业务流程及事务见 services。"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.auth.dependencies import require_superadmin
from app.database.models import User
from app.database.session import get_db
from app.schemas.admin import HomepageUpdate
from app.services import homepage_admin as homepage_admin_service

router = APIRouter(
    prefix="/api/admin", tags=["admin"], dependencies=[Depends(require_superadmin)]
)


@router.get("/homepage")
def get_homepage(db: Session = Depends(get_db)):
    return homepage_admin_service.get_homepage(db)


@router.put("/homepage")
def save_homepage(
    body: HomepageUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(require_superadmin),
):
    return homepage_admin_service.save_homepage(body, db, user)
