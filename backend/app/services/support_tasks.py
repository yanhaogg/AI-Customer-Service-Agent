"""Deterministic detection and task lifecycle. AI only proposes, never changes orders."""

import hashlib
import json
from datetime import datetime, timedelta, timezone
from uuid import uuid4
from fastapi import HTTPException
from sqlalchemy import select, delete
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
    """提供待办规则使用的当前 UTC 时间。

    输入：
        无。

    输出：
        带 UTC 时区的 datetime 对象。

    流程：
        1. 调用 datetime.now(timezone.utc)；不访问数据库。
    """
    return datetime.now(timezone.utc)


def fingerprint(snapshot):
    """为订单事实快照生成稳定的版本指纹。

    输入：
        snapshot: dict，包含订单事实的可 JSON 序列化快照。

    输出：
        str：SHA-256 十六进制摘要。

    流程：
        1. 快照按键排序并保留中文序列化为 JSON
        2. 编码为字节
        3. 计算 SHA-256；用于检测事实变化，不是密码哈希。
    """
    return hashlib.sha256(
        json.dumps(snapshot, sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()


def event(db, task, actor_id, action, note):
    """为待办添加操作事件。

    输入：
        db: SQLAlchemy Session，当前数据库会话。
        task: SupportTask ORM 对象。
        actor_id: int 或 None，事件操作者主键；None 表示无指定操作者。
        action: str，待办事件动作编码。
        note: str，操作说明或事件备注。

    输出：
        None；向当前 Session 添加 SupportTaskEvent。

    流程：
        1. 用待办主键、操作者、动作和备注创建事件
        2. db.add；不 flush、不 commit，由调用方统一保存。
    """
    db.add(
        SupportTaskEvent(task_id=task.id, actor_id=actor_id, action=action, note=note)
    )


def findings(order, refund, at):
    """按固定超时规则检测需要人工核实的订单事项。

    输入：
        order: ShopOrder ORM 对象。
        refund: 活动 RefundRequest 或 None。
        at: 带时区 datetime，本次规则判断的参考时间。

    输出：
        list[dict]：每项含 kind、source_key、due_at、title、priority、snapshot。

    流程：
        1. 按 paid 未发货、shipped 未确认收货、退款待审核三个条件选择规则
        2. 内部 add 比较时间阈值并保存事实快照；不访问数据库、不调用 AI、不创建待办。
    """
    # 确定性规则只判断三类时间条件；命中条件表示需要核实，不代表已经证实物流故障。
    result = []

    def add(kind, source, anchor):
        """向外层 findings 的结果列表追加一条达到超时阈值的发现。

        输入：
            kind: str，跟进事项类型；列表入口允许空值表示不限。
            source: str，规则来源标识，例如 paid、shipped 或 refund:<id>。
            anchor: datetime 或 None，规则计时起点。

        输出：
            None；符合条件时向闭包 result 追加候选字典。

        流程：
            1. 按 kind 读取规则
            2. 检查 anchor 是否早于阈值
            3. 捕获外层 order/refund 构造事实、建议动作和到期时间
            4. 追加；anchor=None 或未超时则不追加。
        """
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
    """读取订单活动退款并检测当前需要跟进的事项。

    输入：
        db: SQLAlchemy Session，当前数据库会话。
        order: ShopOrder ORM 对象。

    输出：
        list[dict]：findings 返回的当前规则候选。

    流程：
        1. 查该订单处于审核/待退货/退货中的申请
        2. 用 now() 调用 findings；不提交。
    """
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
    """查找当前事实中与指定类型及来源一致的发现。

    输入：
        db: SQLAlchemy Session，当前数据库会话。
        order: ShopOrder ORM 对象。
        kind: str，跟进事项类型；列表入口允许空值表示不限。
        source: str，规则来源标识，例如 paid、shipped 或 refund:<id>。

    输出：
        dict 或 None：首个匹配的发现；条件已消失时为 None。

    流程：
        1. 调用 current_findings
        2. 同时匹配 kind 和 source_key
        3. 取首个；不提交。
    """
    return next(
        (
            f
            for f in current_findings(db, order)
            if f["kind"] == kind and f["source_key"] == source
        ),
        None,
    )


def preview_order(db, order_id, actor_id):
    """分析指定订单并保存待人工确认的短期预览。

    输入：
        db: SQLAlchemy Session，当前数据库会话。
        order_id: int，订单主键。
        actor_id: int 或 None，事件操作者主键；None 表示无指定操作者。

    输出：
        dict：order_id、order_number、candidates、message；候选含 preview_id、snapshot、advice、existing_task_id。

    流程：
        1. 查询订单并检测规则
        2. rollback 释放读取事务
        3. 对候选调用模型并校验结构
        4. 重查事实和指纹防过期
        5. 保存属于操作者的 30 分钟预览
        6. 清理过期预览并提交；不创建正式待办，模型异常 503、事实变化 409。
    """
    # 管理员主动分析选定订单：读事实 → 释放事务 → 调模型 → 重查事实 → 保存短期预览。
    # 这里只生成预览，必须另行确认才创建正式待办。
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
    """将仍有效且属于操作者的预览转换为待办。

    输入：
        db: SQLAlchemy Session，当前数据库会话。
        preview_id: str，预览记录的随机标识。
        actor_id: int 或 None，事件操作者主键；None 表示无指定操作者。

    输出：
        tuple：(SupportTask ORM 对象, bool 是否新建)。

    流程：
        1. 校验预览归属与期限
        2. 锁订单并重验事实指纹
        3. 同类型同来源已有任务则复用
        4. 否则保存任务快照/建议并 flush、记创建事件；不 commit，由调用方提交。
    """
    # 确认时再次检查预览归属、有效期和事实版本；同一订单同类来源已有待办则直接复用。
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
    """按统一顺序锁定待办及其订单。

    输入：
        db: SQLAlchemy Session，当前数据库会话。
        task_id: int，客服待办主键。

    输出：
        tuple：(SupportTask, ShopOrder)，均为 ORM 对象。

    流程：
        1. 先读待办确认存在（否则 404）→ 锁订单
        2. 再锁待办并 populate_existing 刷新
        3. 返回；不提交，不自动关闭任务。
    """
    # 先锁订单、后锁待办，保持一致的加锁顺序；这里只读取和加锁，不自动关闭待办。
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
    """组装待办展示数据并判断建议是否已过期。

    输入：
        db: SQLAlchemy Session，当前数据库会话。
        task: SupportTask ORM 对象。
        details: bool，是否附加事件明细，默认 False。

    输出：
        dict：待办字段、facts_changed、当前订单信息、负责人、advice、order_url；details=True 加 events。

    流程：
        1. 查询订单和负责人
        2. 比较当前发现与快照指纹
        3. 按版本及状态决定是否展示建议
        4. 可选查询最近 100 条事件及操作者
        5. 返回；不修改待办、不提交。
    """
    # 展示时比较当前事实与分析快照；事实变化就隐藏过期建议，但不在读取接口修改待办状态。
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
    """显式重新生成待办建议并防止旧结果覆盖新状态。

    输入：
        db: SQLAlchemy Session，当前数据库会话。
        task_id: int，客服待办主键。
        actor_id: int 或 None，事件操作者主键；None 表示无指定操作者。

    输出：
        dict：分析后的待办详情；无效状态/事实变化抛 409，模型失败记录状态后抛 503。

    流程：
        1. 锁订单及待办
        2. 校验活动状态、并发生成和规则仍成立
        3. 保存新快照/请求标记并提交释放锁
        4. 调用模型
        5. 重锁并校验任务状态、事实版本和请求标记
        6. 失败记事件或保存建议
        7. 提交；不执行订单操作。
    """
    # 仅在人工触发时重新分析；生成前记录请求标记，生成后核对版本，避免旧结果覆盖新事实。
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
    """查询某订单仍在处理的待办摘要。

    输入：
        db: SQLAlchemy Session，当前数据库会话。
        order_id: int，订单主键。

    输出：
        list[dict]：id、title、status、assignee_id、snapshot_version；无 order_id 返回空列表。

    流程：
        1. 按订单及 ACTIVE 状态筛选
        2. 按 due_at 排序
        3. 提取摘要字段；不提交。
    """
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
