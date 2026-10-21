"""Deterministic detection and task lifecycle. AI only proposes, never changes orders."""

import hashlib
import json
from datetime import datetime, timedelta, timezone
from uuid import uuid4
from fastapi import HTTPException
from sqlalchemy import select, delete
from sqlalchemy.orm import Session
from app.database.models import User
from app.database.shop_models import ShopOrder
from app.database.aftersales_models import RefundRequest
from app.database.support_task_models import (
    SupportTask,
    SupportTaskEvent,
    SupportTaskPreview,
)
from app.agent.order_followup import order_followup_agent, FollowupAdvice
from app.agent.config import AgentConfigurationError

ACTIVE = ("pending", "in_progress")
RULES = {
    "shipping_overdue": {
        "label": "支付后超过48小时未发货",
        "hours": 48,
        "priority": "high",
        "actions": [
            "核对当前售后状态及是否可安排发货",
            "联系相关人员核实预计发货安排，不推测超时原因",
            "确认信息后在订单会话向客户说明，实际发货仍在订单页操作",
        ],
    },
    "receipt_overdue": {
        "label": "发货超过7天未确认收货，需核实",
        "hours": 168,
        "priority": "normal",
        "actions": [
            "核对快递公司和单号，人工查询承运商信息",
            "确认客户是否已经收货；未确认不等于配送异常",
            "根据核实结果沟通或转售后处理，不自动确认收货",
        ],
    },
    "refund_overdue": {
        "label": "退款申请超过24小时未审核",
        "hours": 24,
        "priority": "high",
        "actions": [
            "查看退款申请、凭证和当前订单状态",
            "核实是否需要补充材料，避免重复退款或继续发货",
            "在订单售后页人工审核并记录处理依据",
        ],
    },
}


def now():
    return datetime.now(timezone.utc)


def fingerprint(snapshot):
    return hashlib.sha256(
        json.dumps(snapshot, sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()


def event(db, task, actor_id, action, note):
    db.add(
        SupportTaskEvent(task_id=task.id, actor_id=actor_id, action=action, note=note)
    )


def findings(order, refund, at):
    result = []

    def add(kind, source, anchor):
        rule = RULES[kind]
        if anchor is not None and anchor <= at - timedelta(hours=rule["hours"]):
            facts = {
                "order_id": order.id,
                "order_number": order.number,
                "order_status": order.status,
                "paid_at": order.paid_at.isoformat() if order.paid_at else None,
                "shipped_at": (
                    order.shipped_at.isoformat() if order.shipped_at else None
                ),
                "carrier": order.carrier,
                "tracking_number": order.tracking_number,
                "refund": (
                    {
                        "id": refund.id,
                        "status": refund.status,
                        "created_at": refund.created_at.isoformat(),
                    }
                    if refund
                    else None
                ),
                "kind": kind,
                "rule": rule["label"],
                "rule_hours": rule["hours"],
                "recommended_actions": rule["actions"],
                "logistics_note": "未接入承运商轨迹；仅可核实发货和确认收货状态，不能推断丢件。",
            }
            result.append(
                {
                    "kind": kind,
                    "source_key": source,
                    "due_at": anchor + timedelta(hours=rule["hours"]),
                    "title": rule["label"],
                    "priority": rule["priority"],
                    "snapshot": facts,
                }
            )

    if order.status == "paid" and refund is None:
        add("shipping_overdue", "paid", order.paid_at)
    if order.status == "shipped" and refund is None:
        add("receipt_overdue", "shipped", order.shipped_at)
    if refund and refund.status == "review_pending":
        add("refund_overdue", f"refund:{refund.id}", refund.created_at)
    return result


def current_findings(db, order):
    refund = db.scalar(
        select(RefundRequest).where(
            RefundRequest.order_id == order.id,
            RefundRequest.status.in_(
                ["review_pending", "awaiting_return", "return_in_transit"]
            ),
        )
    )
    return findings(order, refund, now())


def matching_finding(db, order, kind, source):
    return next(
        (
            f
            for f in current_findings(db, order)
            if f["kind"] == kind and f["source_key"] == source
        ),
        None,
    )


def preview_order(db, order_id, actor_id):
    order = db.get(ShopOrder, order_id)
    if order is None:
        raise HTTPException(404, "订单不存在")
    candidates = current_findings(db, order)
    number = order.number
    db.rollback()
    results = []
    for candidate in candidates:
        snapshot = candidate["snapshot"]
        version = fingerprint(snapshot)
        try:
            advice = FollowupAdvice.model_validate(
                order_followup_agent.invoke(snapshot)
            ).model_dump()
        except AgentConfigurationError:
            raise HTTPException(503, "跟进模型尚未配置，请检查配置后重试。") from None
        except Exception:
            raise HTTPException(503, "异常分析暂时不可用，请稍后重试。") from None
        order = db.scalar(
            select(ShopOrder)
            .where(ShopOrder.id == order_id)
            .execution_options(populate_existing=True)
        )
        fresh = matching_finding(db, order, candidate["kind"], candidate["source_key"])
        if fresh is None or fingerprint(fresh["snapshot"]) != version:
            raise HTTPException(409, "分析期间订单已变化，请重新分析。")
        existing = db.scalar(
            select(SupportTask).where(
                SupportTask.order_id == order_id,
                SupportTask.kind == candidate["kind"],
                SupportTask.source_key == candidate["source_key"],
            )
        )
        token = uuid4().hex
        db.add(
            SupportTaskPreview(
                id=token,
                actor_id=actor_id,
                order_id=order_id,
                kind=candidate["kind"],
                source_key=candidate["source_key"],
                snapshot=snapshot,
                snapshot_version=version,
                advice=advice,
                expires_at=now() + timedelta(minutes=30),
            )
        )
        results.append(
            {
                "preview_id": token,
                "title": candidate["title"],
                "snapshot": snapshot,
                "advice": advice,
                "existing_task_id": existing.id if existing else None,
            }
        )
    db.execute(delete(SupportTaskPreview).where(SupportTaskPreview.expires_at < now()))
    db.commit()
    return {
        "order_id": order_id,
        "order_number": number,
        "candidates": results,
        "message": (
            "分析完成，尚未创建待办。"
            if results
            else "未发现符合当前三类跟进规则的异常，未创建待办。"
        ),
    }


def create_from_preview(db, preview_id, actor_id):
    preview = db.get(SupportTaskPreview, preview_id)
    if preview is None or preview.actor_id != actor_id:
        raise HTTPException(404, "分析结果不存在，请重新分析。")
    if preview.expires_at < now():
        raise HTTPException(409, "分析结果已过期，请重新分析。")
    order = db.scalar(
        select(ShopOrder).where(ShopOrder.id == preview.order_id).with_for_update()
    )
    fresh = matching_finding(db, order, preview.kind, preview.source_key)
    if fresh is None or fingerprint(fresh["snapshot"]) != preview.snapshot_version:
        raise HTTPException(409, "订单事实已变化，请重新分析后创建待办。")
    existing = db.scalar(
        select(SupportTask).where(
            SupportTask.order_id == order.id,
            SupportTask.kind == preview.kind,
            SupportTask.source_key == preview.source_key,
        )
    )
    if existing:
        return existing, False
    task = SupportTask(
        order_id=order.id,
        kind=preview.kind,
        source_key=preview.source_key,
        title=fresh["title"],
        priority=fresh["priority"],
        due_at=fresh["due_at"],
        status="pending",
        snapshot=preview.snapshot,
        snapshot_version=preview.snapshot_version,
        advice=preview.advice,
        advice_version=preview.snapshot_version,
        analysis_status="ready",
        last_seen_at=now(),
    )
    db.add(task)
    db.flush()
    event(db, task, actor_id, "created", "管理员查看分析结果后确认创建待办。")
    return task, True


def locked_task(db, task_id):
    task = db.get(SupportTask, task_id)
    if task is None:
        raise HTTPException(404, "待办不存在")
    order = db.scalar(
        select(ShopOrder).where(ShopOrder.id == task.order_id).with_for_update()
    )
    return (
        db.scalar(
            select(SupportTask)
            .where(SupportTask.id == task_id)
            .execution_options(populate_existing=True)
            .with_for_update()
        ),
        order,
    )


def task_data(db, task, details=False):
    order = db.get(ShopOrder, task.order_id)
    assignee = db.get(User, task.assignee_id) if task.assignee_id else None
    result = {
        key: getattr(task, key)
        for key in (
            "id",
            "order_id",
            "kind",
            "title",
            "status",
            "priority",
            "assignee_id",
            "due_at",
            "snapshot",
            "snapshot_version",
            "analysis_status",
            "created_at",
            "updated_at",
            "resolved_at",
            "resolution_note",
        )
    }
    fresh = matching_finding(db, order, task.kind, task.source_key)
    stale = fresh is None or fingerprint(fresh["snapshot"]) != task.snapshot_version
    result.update(
        facts_changed=stale,
        current_order_status=order.status,
        order_number=order.number,
        assignee_name=assignee.username if assignee else None,
        advice=(
            task.advice
            if task.advice_version == task.snapshot_version
            and (not stale or task.status not in ACTIVE)
            else {}
        ),
        order_url=f"/admin/orders?q={order.number}",
    )
    if details:
        rows = db.execute(
            select(SupportTaskEvent, User.username)
            .outerjoin(User, User.id == SupportTaskEvent.actor_id)
            .where(SupportTaskEvent.task_id == task.id)
            .order_by(SupportTaskEvent.id.desc())
            .limit(100)
        ).all()
        result["events"] = [
            {
                "id": e.id,
                "action": e.action,
                "note": e.note,
                "actor": name or "系统",
                "created_at": e.created_at,
            }
            for e, name in rows
        ]
    return result


def analyze_task(db, task_id, actor_id=None):
    task, order = locked_task(db, task_id)
    if task.status not in ACTIVE:
        db.commit()
        raise HTTPException(409, "待办已关闭或异常已消失，请刷新查看。")
    if (
        task.analysis_status == "generating"
        and task.analysis_started_at
        and task.analysis_started_at > now() - timedelta(minutes=2)
    ):
        raise HTTPException(409, "该待办正在分析，请稍候。")
    fresh = matching_finding(db, order, task.kind, task.source_key)
    if fresh is None:
        raise HTTPException(409, "原异常条件已不成立，请核实后手动完成或忽略待办。")
    version = fingerprint(fresh["snapshot"])
    request_key = uuid4().hex
    snapshot = fresh["snapshot"]
    task.snapshot = snapshot
    task.snapshot_version = version
    task.advice = {}
    task.advice_version = None
    task.analysis_status = "generating"
    task.analysis_key = request_key
    task.analysis_started_at = now()
    db.commit()
    failure = None
    try:
        advice = FollowupAdvice.model_validate(
            order_followup_agent.invoke(snapshot)
        ).model_dump()
    except AgentConfigurationError:
        failure = "跟进模型尚未配置，规则提示与人工待办仍可使用。"
    except Exception:
        failure = "异常跟进分析暂时不可用，请重试或按规则提示人工处理。"
    task, order = locked_task(db, task_id)
    fresh = matching_finding(db, order, task.kind, task.source_key)
    if (
        task.status not in ACTIVE
        or fresh is None
        or fingerprint(fresh["snapshot"]) != version
        or task.analysis_key != request_key
    ):
        if task.analysis_key == request_key:
            task.analysis_status = "pending"
            task.analysis_key = None
        db.commit()
        raise HTTPException(409, "分析期间订单或待办已更新，本次结果未采用。")
    task.updated_at = now()
    task.analysis_key = None
    if failure:
        task.analysis_status = "failed"
        event(db, task, actor_id, "analysis_failed", failure)
        db.commit()
        raise HTTPException(503, failure)
    task.advice = advice
    task.advice_version = version
    task.analysis_status = "ready"
    event(
        db,
        task,
        actor_id,
        "analyzed",
        "已生成内部跟进建议，尚未执行订单操作或发送客户消息。",
    )
    db.flush()
    result = task_data(db, task, details=True)
    db.commit()
    return result


def order_tasks(db, order_id):
    if not order_id:
        return []
    return [
        {
            key: getattr(t, key)
            for key in ("id", "title", "status", "assignee_id", "snapshot_version")
        }
        for t in db.scalars(
            select(SupportTask)
            .where(SupportTask.order_id == order_id, SupportTask.status.in_(ACTIVE))
            .order_by(SupportTask.due_at)
        )
    ]
