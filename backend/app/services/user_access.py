"""串行处理同一用户的购物车、地址、会话创建等写入，不涉及登录令牌校验。"""

from sqlalchemy import select
from app.database.models import User


def lock_user(db, user):
    """以用户行锁串行化同一用户的业务写入。

    输入：
        db: SQLAlchemy Session，当前数据库会话。
        user: 已认证的 User ORM 对象；后台权限由路由依赖检查。

    输出：
        None；在当前事务内持有该用户行的排他锁。

    流程：
        1. 按 user.id 构造 User.id 查询
        2. 使用 FOR UPDATE 执行加锁；不校验 JWT、不提交，锁随调用方事务提交或回滚释放。
    """
    db.execute(select(User.id).where(User.id == user.id).with_for_update())
