"""订单联系与催发货流程；复用订单会话，不自动发货或调用大模型。"""

from datetime import timedelta
from fastapi import HTTPException
from sqlalchemy import select
from app.database.shop_models import ShopOrder
from app.database.aftersales_models import ShipmentReminder
from .clock import now
from .order_access import owned
from .aftersales_queries import active_refund
from .conversations import order_session


def contact(order_id, body, db, user):
    """为本人订单提供客服会话入口。

    输入：
        order_id: int，订单主键。
        body: Contact：intent 咨询意图，human 表示请求人工。
        db: SQLAlchemy Session，当前数据库会话。
        user: 已认证的 User ORM 对象；后台权限由路由依赖检查。

    输出：
        dict：session_id、order_id、url。

    流程：
        1. 校验归属并锁订单
        2. 复用或新建订单会话
        3. intent=human 时转人工
        4. 组装聊天链接并提交。
    """
    order = owned(db, user, order_id)
    session = order_session(db, order, body.intent, human=body.intent == "human")
    result = {
        "session_id": session.id,
        "order_id": order.id,
        "url": f"/chat?session={session.id}",
    }
    db.commit()
    return result


def remind(order_id, body, db, user):
    """记录订单催发货请求，并防止 24 小时内重复催促。

    输入：
        order_id: int，订单主键。
        body: Reminder：note 催促备注。
        db: SQLAlchemy Session，当前数据库会话。
        user: 已认证的 User ORM 对象；后台权限由路由依赖检查。

    输出：
        dict：id、repeated、message、session_id、url。

    流程：
        1. 锁本人订单
        2. 要求 paid 且无活动退款
        3. 查询最新催促
        4. 24 小时内复用，否则新增
        5. 关联订单会话
        6. 提交；不会直接发货或调用模型。
    """
    # 阅读主线：锁本人订单 → 校验状态 → 检查24小时重复催促 → 保存记录 → 关联会话。
    order = owned(db, user, order_id)
    if order.status != "paid":
        raise HTTPException(409, "仅已支付且未发货的订单可以催发货")
    if active_refund(db, order.id):
        raise HTTPException(409, "售后处理中，暂不能催发货")
    previous = db.scalar(
        select(ShipmentReminder)
        .where(ShipmentReminder.order_id == order.id)
        .order_by(ShipmentReminder.id.desc())
        .limit(1)
    )
    repeated = bool(previous and now() - previous.created_at < timedelta(hours=24))
    if not repeated:
        previous = ShipmentReminder(
            order_id=order.id, user_id=user.id, note=body.note, status="pending"
        )
        db.add(previous)
        db.flush()
    session = order_session(db, order, "shipping_reminder")
    result = {
        "id": previous.id,
        "repeated": repeated,
        "message": (
            "24小时内已催促过，请耐心等待客服跟进。"
            if repeated
            else "催发货已记录，客服可在订单后台跟进。"
        ),
        "session_id": session.id,
        "url": f"/chat?session={session.id}",
    }
    db.commit()
    return result


def handle_reminder(reminder_id, body, db):
    """将催发货记录标记为已处理。

    输入：
        reminder_id: int，催发货记录主键。
        body: HandleReminder：note 处理说明。
        db: SQLAlchemy Session，当前数据库会话。

    输出：
        dict：status=handled。

    流程：
        1. 读取催促（不存在 404）→ 锁所属订单
        2. 写处理状态、备注和时间
        3. 提交；管理员权限由路由验证。
    """
    reminder = db.get(ShipmentReminder, reminder_id)
    if reminder is None:
        raise HTTPException(404, "催发货记录不存在")
    db.execute(
        select(ShopOrder.id).where(ShopOrder.id == reminder.order_id).with_for_update()
    )
    reminder.status = "handled"
    reminder.handled_note = body.note
    reminder.handled_at = now()
    db.commit()
    return {"status": "handled"}
