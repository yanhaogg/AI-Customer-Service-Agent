"""HTTP 入口：声明路径、输入校验和权限依赖，业务流程及事务见 services。"""

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.orm import Session
from app.auth.dependencies import get_current_user
from app.database.session import get_db
from app.database.models import User
from app.schemas.activity import ReadThrough
from app.schemas.activity import SessionCreate, MessageCreate, BrowseCreate
from app.services import chat as chat_service
from app.services import browsing as browsing_service

router = APIRouter(
    prefix="/api/activity",
    tags=["customer-history"],
    dependencies=[Depends(get_current_user)],
)


@router.get("/agent-status")
def agent_status():
    return chat_service.agent_status()


@router.post("/sessions", status_code=201)
def create_session(
    body: SessionCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return chat_service.create_session(body, db, user)


@router.get("/sessions")
def sessions(
    page: int = Query(1, ge=1),
    q: str = Query("", max_length=100),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return chat_service.sessions(page, q, db, user)


@router.get("/unread")
def unread(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return chat_service.unread(db, user)


@router.post("/sessions/{session_id}/read")
def read_session(
    session_id: int,
    body: ReadThrough,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return chat_service.read_session(session_id, body, db, user)


@router.get("/sessions/{session_id}")
def messages(
    session_id: int,
    before_id: int | None = Query(None, gt=0),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return chat_service.messages(session_id, before_id, db, user)


@router.delete("/sessions/{session_id}", status_code=204)
def delete_session(
    session_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return chat_service.delete_session(session_id, db, user)


@router.post("/sessions/{session_id}/messages")
def send_message(
    session_id: int,
    body: MessageCreate,
    response: Response,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    result, status_code = chat_service.send_message(session_id, body, db, user)
    response.status_code = status_code
    return result


@router.post("/browsing")
def record_browse(
    body: BrowseCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return browsing_service.record_browse(body, db, user)


@router.get("/browsing")
def browsing(
    page: int = Query(1, ge=1),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return browsing_service.browsing(page, db, user)


@router.delete("/browsing", status_code=204)
def clear_browsing(
    db: Session = Depends(get_db), user: User = Depends(get_current_user)
):
    return browsing_service.clear_browsing(db, user)


@router.delete("/browsing/{entry_id}", status_code=204)
def delete_browse(
    entry_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)
):
    return browsing_service.delete_browse(entry_id, db, user)
