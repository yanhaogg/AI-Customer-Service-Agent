"""收货地址的归属、默认地址与增删改查用例。

业务用例管理事务；HTTP 参数解析与路由声明见对应 api 模块。
"""

from fastapi import HTTPException
from sqlalchemy import select
from app.database.shop_models import ShippingAddress
from app.services.shopping_queries import address_data, owned_address
from app.services.user_access import lock_user


def addresses(db, user):
    """查询当前用户的收货地址。

    输入：
        db: SQLAlchemy Session，当前数据库会话。
        user: 已认证的 User ORM 对象；后台权限由路由依赖检查。

    输出：
        dict：items 为地址字典列表。

    流程：
        1. 按 user.id 筛选地址
        2. 默认地址优先、再按主键排序
        3. 调用 address_data 组装；不提交事务。
    """
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
    """统一处理地址新增和编辑，并维护默认地址。

    输入：
        db: SQLAlchemy Session，当前数据库会话。
        user: 已认证的 User ORM 对象；后台权限由路由依赖检查。
        body: AddressBody：收件人、电话、地区、详细地址、邮编和默认标记。
        address: ShippingAddress 或 None；None 表示新增，否则更新此地址（调用方须保证归属）。

    输出：
        dict：保存后的地址信息。

    流程：
        1. 锁用户
        2. 读取已有地址并校验新增上限 20 条
        3. 决定默认地址并清除其他默认标记
        4. 写字段
        5. flush 生成主键
        6. 组装结果并提交。
    """
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
    """新增当前用户的收货地址。

    输入：
        body: AddressBody：新增地址字段。
        db: SQLAlchemy Session，当前数据库会话。
        user: 已认证的 User ORM 对象；后台权限由路由依赖检查。

    输出：
        dict：新地址信息。

    流程：
        1. 调用 save_address，不传已有地址；地址数量限制、默认地址维护和提交均由它完成。
    """
    return save_address(db, user, body)


def edit_address(address_id, body, db, user):
    """修改属于当前用户的地址。

    输入：
        address_id: int，收货地址主键。
        body: AddressBody：修改后的完整地址字段。
        db: SQLAlchemy Session，当前数据库会话。
        user: 已认证的 User ORM 对象；后台权限由路由依赖检查。

    输出：
        dict：修改后的地址信息。

    流程：
        1. 锁用户
        2. owned_address 校验归属（失败 404）→ 将已有地址交给 save_address 更新并提交。
    """
    lock_user(db, user)
    return save_address(db, user, body, owned_address(db, user, address_id))


def delete_address(address_id, db, user):
    """删除用户地址并在必要时补选默认地址。

    输入：
        address_id: int，收货地址主键。
        db: SQLAlchemy Session，当前数据库会话。
        user: 已认证的 User ORM 对象；后台权限由路由依赖检查。

    输出：
        None；成功时只产生数据库删除和默认标记更新。

    流程：
        1. 锁用户
        2. 校验地址归属
        3. 删除并 flush
        4. 若删的是默认地址，将剩余主键最小的地址设为默认
        5. 提交。
    """
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
