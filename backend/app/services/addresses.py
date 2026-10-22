"""收货地址的归属、默认地址与增删改查用例。

业务用例管理事务；HTTP 参数解析与路由声明见对应 api 模块。
"""

from fastapi import HTTPException
from sqlalchemy import select
from app.database.shop_models import ShippingAddress
from app.services.shopping_queries import address_data, owned_address
from app.services.user_access import lock_user


def addresses(db, user):
    return {
        "items": [
            address_data(a)
            for a in db.scalars(
                select(ShippingAddress)
                .where(ShippingAddress.user_id == user.id)
                .order_by(ShippingAddress.is_default.desc(), ShippingAddress.id)
            )
        ]
    }


def save_address(db, user, body, address=None):
    lock_user(db, user)
    existing = db.scalars(
        select(ShippingAddress)
        .where(ShippingAddress.user_id == user.id)
        .order_by(ShippingAddress.id)
    ).all()
    if address is None and len(existing) >= 20:
        raise HTTPException(422, "最多保存 20 个收货地址")
    make_default = body.is_default or not existing
    if address is not None and address.is_default:
        make_default = True
    if make_default:
        for entry in existing:
            entry.is_default = False
    if address is None:
        address = ShippingAddress(user_id=user.id)
        db.add(address)
    for key, value in body.model_dump().items():
        setattr(address, key, value)
    address.is_default = make_default
    db.flush()
    result = address_data(address)
    db.commit()
    return result


def add_address(body, db, user):
    return save_address(db, user, body)


def edit_address(address_id, body, db, user):
    lock_user(db, user)
    return save_address(db, user, body, owned_address(db, user, address_id))


def delete_address(address_id, db, user):
    lock_user(db, user)
    address = owned_address(db, user, address_id)
    was_default = address.is_default
    db.delete(address)
    db.flush()
    if was_default:
        other = db.scalar(
            select(ShippingAddress)
            .where(ShippingAddress.user_id == user.id)
            .order_by(ShippingAddress.id)
            .limit(1)
        )
        if other:
            other.is_default = True
    db.commit()
