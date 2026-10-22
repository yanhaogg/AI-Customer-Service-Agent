"""串行处理同一用户的购物车、地址、会话创建等写入，不涉及登录令牌校验。"""

from sqlalchemy import select
from app.database.models import User


def lock_user(db, user):
    db.execute(select(User.id).where(User.id == user.id).with_for_update())
