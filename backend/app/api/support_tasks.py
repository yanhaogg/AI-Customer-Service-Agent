from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from app.auth.dependencies import require_superadmin
from app.database.session import get_db
from app.database.models import User
from app.database.activity_models import ChatSession
from app.database.support_task_models import SupportTask
from app.services import support_tasks as service
from app.services.aftersales import order_session
from app.schemas.support_tasks import TaskAction, PreviewRequest, CreateRequest

router = APIRouter(
    prefix="/api/admin/support-tasks",
    tags=["support-tasks"],
    dependencies=[Depends(require_superadmin)],
)


@router.get("/summary")
def summary(db: Session = Depends(get_db), user: User = Depends(require_superadmin)):
    counts = dict(
        db.execute(
            select(SupportTask.status, func.count()).group_by(SupportTask.status)
        ).all()
    )
    mine = db.scalar(
        select(func.count())
        .select_from(SupportTask)
        .where(
            SupportTask.status.in_(service.ACTIVE), SupportTask.assignee_id == user.id
        )
    )
    return {
        "counts": counts,
        "active": sum(counts.get(s, 0) for s in service.ACTIVE),
        "mine": mine,
        "rules": service.RULES,
        "mode": "manual",
    }


@router.post("/preview")
def preview(
    body: PreviewRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_superadmin),
):
    return service.preview_order(db, body.order_id, user.id)


@router.post("", status_code=201)
def create(
    body: CreateRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_superadmin),
):
    task, created = service.create_from_preview(db, body.preview_id, user.id)
    result = {**service.task_data(db, task, details=True), "created": created}
    db.commit()
    return result


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
    query = select(SupportTask)
    if status == "active":
        query = query.where(SupportTask.status.in_(service.ACTIVE))
    elif status != "all":
        query = query.where(SupportTask.status == status)
    if kind:
        query = query.where(SupportTask.kind == kind)
    if mine:
        query = query.where(SupportTask.assignee_id == user.id)
    if order_id:
        query = query.where(SupportTask.order_id == order_id)
    total = db.scalar(select(func.count()).select_from(query.subquery()))
    entries = db.scalars(
        query.order_by(
            (SupportTask.priority == "high").desc(), SupportTask.due_at, SupportTask.id
        )
        .offset((page - 1) * 20)
        .limit(20)
    ).all()
    return {
        "items": [service.task_data(db, t) for t in entries],
        "total": total,
        "total_pages": (total + 19) // 20,
    }


@router.get("/{task_id}")
def detail(task_id: int, db: Session = Depends(get_db)):
    task, order = service.locked_task(db, task_id)
    result = service.task_data(db, task, details=True)
    db.commit()
    return result


@router.post("/{task_id}/analyze")
def analyze(
    task_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_superadmin),
):
    return service.analyze_task(db, task_id, user.id)


@router.post("/{task_id}/actions")
def action(
    task_id: int,
    body: TaskAction,
    db: Session = Depends(get_db),
    user: User = Depends(require_superadmin),
):
    task, order = service.locked_task(db, task_id)
    if body.action == "note":
        if not body.note:
            raise HTTPException(422, "请填写跟进备注。")
        service.event(db, task, user.id, "note", body.note)
    else:
        if task.status not in service.ACTIVE:
            db.commit()
            raise HTTPException(409, "该待办已关闭或异常已消失。")
        if task.assignee_id and task.assignee_id != user.id:
            raise HTTPException(409, "待办已由其他客服认领，请由当前负责人处理。")
        if body.action == "claim":
            if task.assignee_id != user.id:
                task.assignee_id = user.id
                task.status = "in_progress"
                service.event(db, task, user.id, "claimed", "已认领待办。")
        elif body.action == "release":
            if task.assignee_id != user.id:
                raise HTTPException(409, "只能释放自己认领的待办。")
            task.assignee_id = None
            task.status = "pending"
            service.event(
                db, task, user.id, "released", "已释放待办，等待其他客服接手。"
            )
        else:
            if not body.note:
                raise HTTPException(422, "完成或忽略待办时必须填写处理说明。")
            task.assignee_id = user.id
            task.status = "resolved" if body.action == "resolve" else "dismissed"
            task.resolved_at = service.now()
            task.resolution_note = body.note
            task.analysis_key = None
            if task.analysis_status == "generating":
                task.analysis_status = "pending"
            service.event(db, task, user.id, body.action, body.note)
    task.updated_at = service.now()
    db.flush()
    result = service.task_data(db, task, details=True)
    db.commit()
    return result


@router.post("/{task_id}/conversation")
def conversation(task_id: int, db: Session = Depends(get_db)):
    task, order = service.locked_task(db, task_id)
    session = order_session(db, order)
    result = {"session_id": session.id, "url": f"/admin/support?session={session.id}"}
    db.commit()
    return result
