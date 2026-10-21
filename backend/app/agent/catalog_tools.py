"""Scoped, bounded, read-only database tools. Identity is captured, never a model argument."""

from contextlib import contextmanager
from datetime import datetime, timezone
from decimal import Decimal
from typing import Literal
from langchain_core.tools import StructuredTool
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import func, or_, select, text
from app.database.database import SessionLocal
from app.database.catalog_models import CatalogCategory, Product
from app.database.shop_models import SaleOffer, ShopOrder, ShopOrderItem
from app.database.activity_models import BrowsingHistory, ChatSession, ChatMessage
from app.api.catalog import product_query, serialize_products
from app.services.aftersales import latest_summary, refund_policy

Currency = Literal["CNY", "USD", "EUR", "GBP", "JPY", "HKD"]
OrderStatus = Literal[
    "pending_payment", "paid", "shipped", "completed", "cancelled", "refunded"
]


class Arguments(BaseModel):
    model_config = ConfigDict(extra="forbid")


class NoArguments(Arguments):
    pass


class SearchProducts(Arguments):
    query: str = Field(
        default="",
        max_length=150,
        description="名称、品牌或型号关键词。没有结果时尝试更短或原文关键词。",
    )
    category_code: str | None = Field(default=None, max_length=100)
    currency: Currency | None = None
    min_price: float | None = Field(default=None, ge=0, le=9999999999)
    max_price: float | None = Field(default=None, ge=0, le=9999999999)
    in_stock_only: bool = False
    page: int = Field(default=1, ge=1, le=50)
    limit: int = Field(default=6, ge=1, le=8)

    @model_validator(mode="after")
    def price_currency(self):
        if (
            self.min_price is not None or self.max_price is not None
        ) and not self.currency:
            raise ValueError("按价格筛选必须明确币种，禁止把 USD 当作 CNY")
        if (
            self.min_price is not None
            and self.max_price is not None
            and self.min_price > self.max_price
        ):
            raise ValueError("最低价格不能大于最高价格")
        return self


class ProductDetails(Arguments):
    product_id: int = Field(gt=0)


class MyOrders(Arguments):
    status: OrderStatus | None = None
    page: int = Field(default=1, ge=1, le=100)
    limit: int = Field(default=5, ge=1, le=8)


class MyOrderDetails(Arguments):
    order_number: str | None = Field(default=None, max_length=40)
    order_id: int | None = Field(default=None, gt=0)

    @model_validator(mode="after")
    def identifier(self):
        if bool(self.order_number) == bool(self.order_id):
            raise ValueError("请提供一个订单编号或订单 ID")
        return self


class MyBrowsing(Arguments):
    limit: int = Field(default=6, ge=1, le=10)


class MyChatHistory(Arguments):
    query: str = Field(min_length=1, max_length=100)
    limit: int = Field(default=5, ge=1, le=8)


def short(value, length=500):
    return str(value or "")[:length]


def product_brief(product):
    return {
        "product_id": product["id"],
        "name": short(product["name"], 300),
        "brand": product["brand"],
        "model": product["model"],
        "category": product["category"],
        "category_code": product["category_code"],
        "introduction": short(product["introduction"], 600),
        "url": f"/products/{product['id']}",
        "demo_sale": product["offer"],
        "reference_price": product["price"],
    }


def order_brief(db, order):
    expired = order.status == "pending_payment" and order.expires_at <= datetime.now(
        timezone.utc
    )
    items = db.scalars(
        select(ShopOrderItem)
        .where(ShopOrderItem.order_id == order.id)
        .order_by(ShopOrderItem.id)
        .limit(50)
    ).all()
    return {
        "order_id": order.id,
        "number": order.number,
        "status": order.status,
        "is_expired": expired,
        "total": str(order.total),
        "currency": order.currency,
        "demo": True,
        "url": f"/orders/{order.id}",
        "created_at": order.created_at.isoformat(),
        "expires_at": order.expires_at.isoformat(),
        "carrier": order.carrier,
        "tracking_number": order.tracking_number,
        "cancel_reason": order.cancel_reason,
        "items": [
            {
                "product_id": i.product_id,
                "name": short(i.name, 250),
                "quantity": i.quantity,
                "unit_price": str(i.unit_price),
            }
            for i in items
        ],
        "aftersales": latest_summary(db, order.id),
        "shipping_region": short((order.shipping_address or {}).get("region"), 200),
        "privacy_note": "完整收货人、电话和详细地址请在订单详情查看。",
    }


def build_tools(user_id, session_factory=None, current_message_id=None):
    if type(user_id) is not int or user_id <= 0:
        raise ValueError("Verified user required")
    factory = session_factory or SessionLocal

    @contextmanager
    def database():
        with factory() as db:
            db.execute(text("SET TRANSACTION READ ONLY"))
            db.execute(text("SET LOCAL statement_timeout = '3000ms'"))
            yield db

    def categories():
        with database() as db:
            rows = db.execute(
                select(
                    CatalogCategory.code, CatalogCategory.name, func.count(Product.id)
                )
                .join(Product, Product.category_id == CatalogCategory.id)
                .where(Product.status.in_(["draft", "reviewed", "published"]))
                .group_by(CatalogCategory.id)
                .order_by(CatalogCategory.code)
                .limit(50)
            ).all()
            return {
                "items": [{"code": r[0], "name": r[1], "count": r[2]} for r in rows]
            }

    def search_products(
        query="",
        category_code=None,
        currency=None,
        min_price=None,
        max_price=None,
        in_stock_only=False,
        page=1,
        limit=6,
    ):
        with database() as db:
            statement = product_query().outerjoin(
                SaleOffer, SaleOffer.product_id == Product.id
            )
            if query.strip():
                statement = statement.where(
                    or_(
                        *[
                            column.icontains(query.strip(), autoescape=True)
                            for column in (
                                Product.name_original,
                                Product.name_zh,
                                Product.brand,
                                Product.model,
                                Product.introduction_zh,
                            )
                        ]
                    )
                )
            if category_code:
                statement = statement.where(CatalogCategory.code == category_code)
            if currency:
                statement = statement.where(SaleOffer.currency == currency)
            if in_stock_only:
                statement = statement.where(
                    SaleOffer.is_active.is_(True), SaleOffer.stock > 0
                )
            if min_price is not None:
                statement = statement.where(
                    SaleOffer.price >= Decimal(str(min_price)),
                    SaleOffer.is_active.is_(True),
                )
            if max_price is not None:
                statement = statement.where(
                    SaleOffer.price <= Decimal(str(max_price)),
                    SaleOffer.is_active.is_(True),
                )
            total = db.scalar(select(func.count()).select_from(statement.subquery()))
            rows = db.execute(
                statement.order_by(Product.id).offset((page - 1) * limit).limit(limit)
            ).all()
            return {
                "items": [product_brief(p) for p in serialize_products(db, rows)],
                "total": total,
                "page": page,
                "has_more": page * limit < total,
                "note": "销售设置为演示价格与库存；reference_price 是独立参考价，币种不自动换算。",
            }

    def product_details(product_id):
        with database() as db:
            row = db.execute(product_query().where(Product.id == product_id)).first()
            if not row:
                return {"error": "商品不存在或已删除"}
            result = product_brief(serialize_products(db, [row])[0])
            product = row[0]
            result.update(
                description_original=short(product.description_original, 3000),
                verified_specs={
                    short(k, 100): short(v, 500)
                    for k, v in list((product.specs or {}).get("verified", {}).items())[
                        :40
                    ]
                },
                source_original={
                    short(k, 100): short(v, 500)
                    for k, v in list(
                        (product.specs or {}).get("source_original", {}).items()
                    )[:20]
                },
            )
            return result

    def my_orders(status=None, page=1, limit=5):
        with database() as db:
            query = select(ShopOrder).where(ShopOrder.user_id == user_id)
            if status:
                query = query.where(ShopOrder.status == status)
            total = db.scalar(select(func.count()).select_from(query.subquery()))
            rows = db.scalars(
                query.order_by(ShopOrder.id.desc())
                .offset((page - 1) * limit)
                .limit(limit)
            ).all()
            return {
                "items": [order_brief(db, o) for o in rows],
                "total": total,
                "has_more": page * limit < total,
            }

    def order_details(order_number=None, order_id=None):
        with database() as db:
            query = select(ShopOrder).where(ShopOrder.user_id == user_id)
            query = (
                query.where(ShopOrder.id == order_id)
                if order_id
                else query.where(ShopOrder.number == order_number)
            )
            order = db.scalar(query)
            return (
                order_brief(db, order)
                if order
                else {"error": "未找到属于当前登录账号的订单"}
            )

    def browsing(limit=6):
        with database() as db:
            rows = db.scalars(
                select(BrowsingHistory)
                .where(BrowsingHistory.user_id == user_id)
                .order_by(
                    BrowsingHistory.last_viewed_at.desc(), BrowsingHistory.id.desc()
                )
                .limit(limit)
            ).all()
            ids = [r.product_id for r in rows]
            products = {
                p["id"]: p
                for p in serialize_products(
                    db, db.execute(product_query().where(Product.id.in_(ids))).all()
                )
            }
            return {
                "items": [
                    {
                        "product_id": r.product_id,
                        "name": short(r.product_name, 300),
                        "view_count": r.view_count,
                        "last_viewed_at": r.last_viewed_at.isoformat(),
                        "available": r.product_id in products,
                        "product": (
                            product_brief(products[r.product_id])
                            if r.product_id in products
                            else None
                        ),
                    }
                    for r in rows
                ],
                "note": "仅当前账号主动打开的商品详情，登录前浏览不会保存。",
            }

    def chat_history(query, limit=5):
        with database() as db:
            statement = select(ChatMessage, ChatSession.title).join(
                ChatSession, ChatSession.id == ChatMessage.session_id
            )
            statement = statement.where(
                ChatSession.user_id == user_id,
                ChatMessage.status == "completed",
                ChatMessage.content.icontains(query.strip(), autoescape=True),
            )
            if current_message_id:
                statement = statement.where(ChatMessage.id < current_message_id)
            rows = db.execute(
                statement.order_by(ChatMessage.id.desc()).limit(limit)
            ).all()
            return {
                "items": [
                    {
                        "session_title": short(title, 100),
                        "role": message.role,
                        "content": short(message.content, 1000),
                        "created_at": message.created_at.isoformat(),
                    }
                    for message, title in rows
                ],
                "note": "历史消息是上下文线索；订单状态、库存与价格仍需重新调用实时查询工具核实。",
            }

    definitions = [
        (
            "get_refund_policy",
            refund_policy,
            NoArguments,
            "查询商城现行模拟退款规则、自动/人工条件、所需凭证与退货流程。只读，不能执行退款。",
        ),
        (
            "list_product_categories",
            categories,
            NoArguments,
            "列出当前可展示的商品分类及其分类编码。",
        ),
        (
            "search_products",
            search_products,
            SearchProducts,
            "搜索真实商品资料。支持名称/品牌/型号、分类、售价币种和库存过滤。预算筛选必须指定币种，不会换算汇率。",
        ),
        (
            "get_product_details",
            product_details,
            ProductDetails,
            "按商品 ID 查询介绍、已核实参数、演示售价和库存。",
        ),
        (
            "list_my_orders",
            my_orders,
            MyOrders,
            "分页查询当前登录账号自己的订单，可筛选状态。",
        ),
        (
            "get_my_order_details",
            order_details,
            MyOrderDetails,
            "按订单编号或内部 ID 查询当前账号自己的订单、商品、金额、状态和物流。",
        ),
        (
            "get_my_browsing_history",
            browsing,
            MyBrowsing,
            "查询当前登录账号最近浏览过的商品，可用于继续咨询或推荐。",
        ),
        (
            "search_my_chat_history",
            chat_history,
            MyChatHistory,
            "在当前登录账号的历史聊天中按关键词查找上下文。只返回已完成的历史消息。",
        ),
    ]
    return [
        StructuredTool.from_function(
            func=func, name=name, args_schema=schema, description=description
        )
        for name, func, schema, description in definitions
    ]
