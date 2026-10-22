"""HTTP 入口：声明路径、输入校验和权限依赖，业务流程及事务见 services。"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from app.auth.dependencies import require_superadmin, get_current_user
from app.database.session import get_db
from app.database.models import User
from app.schemas.activity import ReadThrough
from app.schemas.human_support import Reply, AssistantRequest
from app.services import human_support as human_support_service

router = APIRouter(
    prefix="/api/admin/support-sessions",
    tags=["human-support"],
    dependencies=[Depends(require_superadmin)],
)

user_router = APIRouter(
    prefix="/api/activity",
    tags=["human-handoff"],
    dependencies=[Depends(get_current_user)],
)


@user_router.post("/sessions/{session_id}/handoff")
def handoff(
    session_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return human_support_service.handoff(session_id, db, user)


@router.get("")
def inbox(
    status: str = Query("all", pattern="^(all|none|waiting|active|closed)$"),
    page: int = Query(1, ge=1),
    unread_only: bool = False,
    db: Session = Depends(get_db),
    user: User = Depends(require_superadmin),
):
    return human_support_service.inbox(status, page, unread_only, db, user)


@router.get("/unread")
def unread(db: Session = Depends(get_db), user: User = Depends(require_superadmin)):
    return human_support_service.unread(db, user)


@router.post("/{session_id}/read")
def read_session(
    session_id: int,
    body: ReadThrough,
    db: Session = Depends(get_db),
    user: User = Depends(require_superadmin),
):
    return human_support_service.read_session(session_id, body, db, user)


@router.get("/{session_id}")
def detail(
    session_id: int,
    before_id: int | None = Query(None, gt=0),
    db: Session = Depends(get_db),
    user: User = Depends(require_superadmin),
):
    return human_support_service.detail(session_id, before_id, db, user)


@router.post("/{session_id}/assistant")
def assistant(
    session_id: int,
    body: AssistantRequest | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(require_superadmin),
):
    return human_support_service.assistant(session_id, body, db, user)


@router.post("/{session_id}/messages")
def reply(
    session_id: int,
    body: Reply,
    db: Session = Depends(get_db),
    user: User = Depends(require_superadmin),
):
    return human_support_service.reply(session_id, body, db, user)


@router.post("/{session_id}/close")
def close(
    session_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_superadmin),
):
    return human_support_service.close(session_id, db, user)
