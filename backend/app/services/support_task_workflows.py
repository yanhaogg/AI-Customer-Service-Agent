"""客服待办的列表、统计、操作与会话入口；分析能力委托 support_tasks。

业务用例管理事务；HTTP 参数解析与路由声明见对应 api 模块。
"""

from fastapi import HTTPException
from sqlalchemy import func, select
from app.database.support_task_models import SupportTask
from app.services import support_tasks as service
from app.services.conversations import order_session


def summary(db, user):
    """统计后台待办状态、活动数量和当前客服认领量。

    输入：
        db: SQLAlchemy Session，当前数据库会话。
        user: 已认证的 User ORM 对象；后台权限由路由依赖检查。

    输出：
        dict：counts、active、mine、rules、mode=manual。

    流程：
        1. 按状态分组计数
        2. 统计本人活动待办
        3. 合并确定性规则配置；只读取，不扫描订单、不创建待办、不提交。
    """
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


def preview(body, db, user):
    """为管理员选中的订单生成待办分析预览。

    输入：
        body: PreviewRequest：order_id，待分析订单主键。
        db: SQLAlchemy Session，当前数据库会话。
        user: 已认证的 User ORM 对象；后台权限由路由依赖检查。

    输出：
        dict：订单信息、candidates 分析候选及 message，尚未创建正式待办。

    流程：
        1. 将 body.order_id、user.id 交给 preview_order；由其检测规则、调用模型、校验快照并提交短期预览。
    """
    return service.preview_order(db, body.order_id, user.id)


def create(body, db, user):
    """将管理员确认的分析预览转换成正式待办。

    输入：
        body: CreateRequest：preview_id，人工确认的分析预览标识。
        db: SQLAlchemy Session，当前数据库会话。
        user: 已认证的 User ORM 对象；后台权限由路由依赖检查。

    输出：
        dict：待办详情加 created（是否本次新建）。

    流程：
        1. create_from_preview 校验预览并创建或复用
        2. task_data 组装详情
        3. 本层提交事务。
    """
    task, created = service.create_from_preview(db, body.preview_id, user.id)
    result = {**service.task_data(db, task, details=True), "created": created}
    db.commit()
    return result


def tasks(status, kind, mine, order_id, page, db, user):
    """按多种条件分页列出后台待办。

    输入：
        status: str，状态筛选条件，具体允许值由路由约束。
        kind: str，跟进事项类型；列表入口允许空值表示不限。
        mine: bool，是否只查看当前客服认领的待办。
        order_id: int，订单主键。
        page: int，从 1 开始的页码（由路由校验）。
        db: SQLAlchemy Session，当前数据库会话。
        user: 已认证的 User ORM 对象；后台权限由路由依赖检查。

    输出：
        dict：items、total、total_pages。

    流程：
        1. 按状态、类型、本人认领和订单筛选
        2. 统计总数
        3. 高优先级优先，再按到期时间及主键每页取 20 条
        4. 组装待办；不提交。
    """
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


def detail(task_id, db):
    """读取单个待办详情并释放读取时获取的锁。

    输入：
        task_id: int，客服待办主键。
        db: SQLAlchemy Session，当前数据库会话。

    输出：
        dict：待办字段、事实变化标记、建议及最近事件。

    流程：
        1. locked_task 先锁订单后锁待办
        2. task_data(details=True)
        3. 提交释放锁；不自动关闭待办。
    """
    task, order = service.locked_task(db, task_id)
    result = service.task_data(db, task, details=True)
    db.commit()
    return result


def analyze(task_id, db, user):
    """由当前客服显式触发待办重新分析。

    输入：
        task_id: int，客服待办主键。
        db: SQLAlchemy Session，当前数据库会话。
        user: 已认证的 User ORM 对象；后台权限由路由依赖检查。

    输出：
        dict：重新分析后的待办详情；过期事实、并发分析等情况抛对应 HTTPException。

    流程：
        1. 将 task_id 和 user.id 交给 analyze_task，由其记录生成状态、调用模型、校验版本并提交。
    """
    return service.analyze_task(db, task_id, user.id)


def action(task_id, body, db, user):
    """处理待办备注、认领、释放、完成或忽略。

    输入：
        task_id: int，客服待办主键。
        body: TaskAction：action（note/claim/release/resolve/dismiss）、note。
        db: SQLAlchemy Session，当前数据库会话。
        user: 已认证的 User ORM 对象；后台权限由路由依赖检查。

    输出：
        dict：操作后的待办详情。

    流程：
        1. 先锁订单及待办
        2. 备注要求非空，其余操作校验活动状态和负责人
        3. 按 action 更新认领/状态/解决说明及分析标记
        4. 记录事件
        5. 更新时间、flush、组装并提交。
    """
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


def conversation(task_id, db):
    """为待办对应订单提供后台会话入口。

    输入：
        task_id: int，客服待办主键。
        db: SQLAlchemy Session，当前数据库会话。

    输出：
        dict：session_id、后台客服 url。

    流程：
        1. 锁待办及订单
        2. 复用或创建订单会话
        3. 组装链接
        4. 提交；不发送消息。
    """
    task, order = service.locked_task(db, task_id)
    session = order_session(db, order)
    result = {"session_id": session.id, "url": f"/admin/support?session={session.id}"}
    db.commit()
    return result
