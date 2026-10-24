"""购物公共查询、计价、订单快照与过期库存回收。

公共查询和数据组装供业务用例复用，本模块不提交事务。
"""

from app.services.clock import now

from decimal import Decimal
from fastapi import HTTPException
from sqlalchemy import select
from app.database.catalog_models import Product, ProductImage
from app.database.shop_models import (
    SaleOffer,
    ShippingAddress,
    ShopOrder,
    ShopOrderItem,
)
from app.storage import VISIBLE_STATUSES
from app.services.aftersales_queries import latest_summary
from app.services.inventory import release_stock


def address_data(address):
    """将收货地址对象转换为响应或订单快照可用的数据。

    输入：
        address: ShippingAddress ORM 对象。

    输出：
        dict：id、recipient、phone、region、detail、postal_code、is_default。

    流程：
        1. 提取指定地址属性
        2. 组装字典；不提交。
    """
    return {
        key: getattr(address, key)
        for key in (
            "id",
            "recipient",
            "phone",
            "region",
            "detail",
            "postal_code",
            "is_default",
        )
    }


def owned_address(db, user, address_id):
    """校验收货地址属于当前用户。

    输入：
        db: SQLAlchemy Session，当前数据库会话。
        user: 已认证的 User ORM 对象；后台权限由路由依赖检查。
        address_id: int，收货地址主键。

    输出：
        ShippingAddress ORM 对象；不存在或不属于本人时抛 404。

    流程：
        1. 同时按地址主键与 user.id 查询
        2. 返回对象；不加行锁、不提交。
    """
    address = db.scalar(
        select(ShippingAddress).where(
            ShippingAddress.id == address_id, ShippingAddress.user_id == user.id
        )
    )
    if address is None:
        raise HTTPException(404, "收货地址不存在")
    return address


def expire_orders(db):
    """按需取消超期待支付订单并回收库存。

    输入：
        db: SQLAlchemy Session，当前数据库会话。

    输出：
        None；最多处理本批 500 个订单，更新取消状态和库存。

    流程：
        1. 按主键查询超时 pending_payment 订单
        2. 加行锁并跳过已锁行
        3. release_stock 回补
        4. 写 cancelled、取消时间与原因
        5. flush；不 commit，由调用方提交。
    """
    # Lazy reclamation on shop access; row locks make repeated/parallel reclamation safe.
    # 访问商城时回收过期待付款订单；这是按需回收，不是后台定时扫描。
    expired = db.scalars(
        select(ShopOrder)
        .where(ShopOrder.status == "pending_payment", ShopOrder.expires_at <= now())
        .order_by(ShopOrder.id)
        .limit(500)
        .with_for_update(skip_locked=True)
    ).all()
    if expired:
        release_stock(db, expired)
        for order in expired:
            order.status = "cancelled"
            order.cancelled_at = now()
            order.cancel_reason = "超时未支付"
        db.flush()


def quote(db, items, lock=False):
    """按服务端当前销售配置校验选品并计算报价。

    输入：
        db: SQLAlchemy Session，当前数据库会话。
        items: Selection/其子类对象列表，每项包含 product_id、quantity。
        lock: bool，是否对查询结果加行锁，默认 False。

    输出：
        tuple：(报价 dict, {product_id: SaleOffer})；报价含 items、total、currency、shipping_fee、demo。

    流程：
        1. 固定顺序查可见商品及销售配置
        2. lock=True 时加锁
        3. 校验上架/库存
        4. 查主图并用 Decimal 算小计总额
        5. 校验单币种及金额上限
        6. 返回；不扣库存、不提交。
    """
    # 价格与库存以数据库为准，服务端重新计算总额；结算时加锁，预览时不预留库存。
    ids = sorted(item.product_id for item in items)
    products_query = (
        select(Product)
        .where(Product.id.in_(ids), Product.status.in_(VISIBLE_STATUSES))
        .order_by(Product.id)
    )
    if lock:
        products_query = products_query.with_for_update(read=True)
    products = {p.id: p for p in db.scalars(products_query)}
    offers_query = (
        select(SaleOffer)
        .where(SaleOffer.product_id.in_(ids))
        .order_by(SaleOffer.product_id)
    )
    if lock:
        offers_query = offers_query.with_for_update()
    offers = {o.product_id: o for o in db.scalars(offers_query)}
    result = []
    currencies = set()
    total = Decimal("0")
    for item in items:
        product, offer = products.get(item.product_id), offers.get(item.product_id)
        if not product or not offer or not offer.is_active:
            raise HTTPException(
                409, f"商品 #{item.product_id} 已下架或尚未设置销售价格"
            )
        if offer.stock < item.quantity:
            raise HTTPException(
                409,
                f"{product.name_zh or product.name_original} 库存不足（剩余 {offer.stock}）",
            )
        image = db.scalar(
            select(ProductImage.asset_id)
            .where(ProductImage.product_id == product.id)
            .order_by(
                ProductImage.is_primary.desc(), ProductImage.sort_order, ProductImage.id
            )
            .limit(1)
        )
        currencies.add(offer.currency)
        subtotal = offer.price * item.quantity
        total += subtotal
        result.append(
            {
                "product_id": product.id,
                "name": product.name_zh or product.name_original,
                "quantity": item.quantity,
                "unit_price": str(offer.price),
                "subtotal": str(subtotal),
                "image_asset_id": image,
                "image": {"url": f"/api/catalog/media/{image}"} if image else None,
            }
        )
    if len(currencies) != 1:
        raise HTTPException(422, "不同币种的商品需要分别下单，请选择相同币种商品")
    if total > Decimal("999999999999.99"):
        raise HTTPException(422, "订单金额过大，请减少商品数量或拆分订单")
    return {
        "items": result,
        "total": str(total),
        "currency": next(iter(currencies)),
        "shipping_fee": "0.00",
        "demo": True,
    }, offers


def order_data(db, order):
    """组装订单快照、商品明细与最新售后摘要。

    输入：
        db: SQLAlchemy Session，当前数据库会话。
        order: ShopOrder ORM 对象。

    输出：
        dict：订单字段、字符串 total、items、aftersales、demo。

    流程：
        1. 按订单查询保存的明细快照
        2. 提取订单属性
        3. latest_summary 补充售后
        4. 金额转字符串、组装图片链接；不提交。
    """
    items = db.scalars(
        select(ShopOrderItem)
        .where(ShopOrderItem.order_id == order.id)
        .order_by(ShopOrderItem.id)
    ).all()
    result = {
        key: getattr(order, key)
        for key in (
            "id",
            "number",
            "status",
            "currency",
            "shipping_address",
            "note",
            "created_at",
            "expires_at",
            "paid_at",
            "shipped_at",
            "completed_at",
            "cancelled_at",
            "cancel_reason",
            "carrier",
            "tracking_number",
            "refunded_at",
        )
    }
    result["aftersales"] = latest_summary(db, order.id)
    result.update(
        total=str(order.total),
        demo=True,
        items=[
            {
                "product_id": item.product_id,
                "name": item.name,
                "quantity": item.quantity,
                "unit_price": str(item.unit_price),
                "subtotal": str(item.unit_price * item.quantity),
                "image": (
                    {"url": f"/api/catalog/media/{item.image_asset_id}"}
                    if item.image_asset_id
                    else None
                ),
            }
            for item in items
        ],
    )
    return result


def owned_order(db, user, order_id):
    """查找本人订单并加行锁供状态转换使用。

    输入：
        db: SQLAlchemy Session，当前数据库会话。
        user: 已认证的 User ORM 对象；后台权限由路由依赖检查。
        order_id: int，订单主键。

    输出：
        ShopOrder ORM 对象；不存在或越权时抛 404。

    流程：
        1. 按 order_id 和 user.id 查询
        2. FOR UPDATE 锁订单
        3. 返回对象；不提交。
    """
    order = db.scalar(
        select(ShopOrder)
        .where(ShopOrder.id == order_id, ShopOrder.user_id == user.id)
        .with_for_update()
    )
    if order is None:
        raise HTTPException(404, "订单不存在")
    return order
