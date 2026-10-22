"""HTTP 入口：声明路径、输入校验和权限依赖，业务流程及事务见 services。"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from app.auth.dependencies import require_superadmin
from app.database.session import get_db
from app.database.models import User
from app.schemas.support_tasks import TaskAction, PreviewRequest, CreateRequest
from app.services import support_task_workflows as support_task_workflows_service

router = APIRouter(
    prefix="/api/admin/support-tasks",
    tags=["support-tasks"],
    dependencies=[Depends(require_superadmin)],
)


@router.get("/summary")
def summary(db: Session = Depends(get_db), user: User = Depends(require_superadmin)):
    return support_task_workflows_service.summary(db, user)


@router.post("/preview")
def preview(
    body: PreviewRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_superadmin),
):
    return support_task_workflows_service.preview(body, db, user)


@router.post("", status_code=201)
def create(
    body: CreateRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_superadmin),
):
    return support_task_workflows_service.create(body, db, user)


@router.get("")
def tasks(
    status: str = Query(
        "active", pattern="^(active|all|pending|in_progress|resolved|dismissed)$"
    ),
    kind: str = Query(
        "", pattern="^(|shipping_overdue|receipt_overdue|refund_overdue)$"
    ),
    mine: bool = False,
    order_id: int | None = Query(None, gt=0),
    page: int = Query(1, ge=1),
    db: Session = Depends(get_db),
    user: User = Depends(require_superadmin),
):
    return support_task_workflows_service.tasks(
        status, kind, mine, order_id, page, db, user
    )


@router.get("/{task_id}")
def detail(task_id: int, db: Session = Depends(get_db)):
    return support_task_workflows_service.detail(task_id, db)


@router.post("/{task_id}/analyze")
def analyze(
    task_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_superadmin),
):
    return support_task_workflows_service.analyze(task_id, db, user)


@router.post("/{task_id}/actions")
def action(
    task_id: int,
    body: TaskAction,
    db: Session = Depends(get_db),
    user: User = Depends(require_superadmin),
):
    return support_task_workflows_service.action(task_id, body, db, user)


@router.post("/{task_id}/conversation")
def conversation(task_id: int, db: Session = Depends(get_db)):
    return support_task_workflows_service.conversation(task_id, db)
