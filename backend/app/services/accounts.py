"""用户注册、登录与身份信息用例，密码和 JWT 算法仍由 auth 包提供。

业务用例管理事务；HTTP 参数解析与路由声明见对应 api 模块。
"""

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from app.auth.jwt import create_access_token
from app.auth.password import hash_password, verify_password
from app.database.models import User


def user_info(user):
    """提取可以返回给客户端的用户公开信息。

    输入：
        user: 已认证的 User ORM 对象；后台权限由路由依赖检查。

    输出：
        dict：包含 id、username、role，不包含密码哈希。

    流程：
        1. 读取 User 的公开属性
        2. 组装字典；不查询数据库、不提交事务。
    """
    return {"id": user.id, "username": user.username, "role": user.role}


def register(user, db):
    """注册普通用户并保存密码哈希。

    输入：
        user: UserCreate 请求模型：username 用户名、password 明文密码；不是数据库 User。
        db: SQLAlchemy Session，当前数据库会话。

    输出：
        dict：message 注册成功提示、user_id 新用户主键。

    流程：
        1. 查询用户名是否占用
        2. 哈希密码
        3. 创建 role=user 的用户
        4. 提交事务；唯一约束冲突时回滚并返回 400。
    """
    if db.scalar(select(User).where(User.username == user.username).limit(1)):
        raise HTTPException(400, "用户名已存在")
    # Never accept role/permissions from the public registration body.
    created = User(
        username=user.username, password_hash=hash_password(user.password), role="user"
    )
    db.add(created)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            400, "用户名已存在"
        ) from None  # from None 抑制异常链，让最终对外暴露的错误就是干净的 HTTPException(400)，避免把数据库细节（表名、约束名、SQL）泄露给客户端，也避免 FastAPI 日志里出现一长串内部异常。
    return {"message": "注册成功", "user_id": created.id}


def login(user, db):
    """验证账号密码并签发登录令牌。

    输入：
        user: UserLogin 请求模型：username 用户名、password 明文密码。
        db: SQLAlchemy Session，当前数据库会话。

    输出：
        dict：access_token、token_type=bearer、user 公开信息。

    流程：
        1. 去掉用户名两端空白并查用户
        2. 用 bcrypt 验证密码
        3. 失败返回 401，成功生成包含 user_id 的 JWT；不提交事务。
    """
    stored = db.scalar(
        select(User).where(User.username == user.username.strip()).limit(1)
    )
    if stored is None or not verify_password(user.password, stored.password_hash):
        raise HTTPException(401, "用户名或密码错误")
    return {
        "access_token": create_access_token({"user_id": stored.id}),
        "token_type": "bearer",
        "user": user_info(stored),
    }


def me(user):
    """返回已通过认证的当前用户信息。

    输入：
        user: 已认证的 User ORM 对象；后台权限由路由依赖检查。

    输出：
        dict：当前用户的 id、username、role。

    流程：
        1. 直接调用 user_info 组装信息；身份校验已由路由依赖完成。
    """
    return user_info(user)
