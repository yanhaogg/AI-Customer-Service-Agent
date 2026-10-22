"""统一建表入口：显式注册全部 ORM 模型，再创建缺失表并执行基础升级。"""

from app.database.database import Base, engine

# 导入模型会将表注册到同一个 Base.metadata，不会在导入时执行建表。
# 显式列出全部模块，避免依赖某个业务模块“顺便导入”其他模型。
from app.database import (
    models,
    catalog_models,
    homepage_models,
    shop_models,
    activity_models,
    aftersales_models,
    support_task_models,
)
from app.database.admin_migration import migrate_admin
from app.database.activity_migration import migrate_activity
from app.database.aftersales_migration import migrate_aftersales


def init_database():
    # create_all 根据外键依赖安排建表顺序，而不是按照上方 import 的顺序。
    # 只创建缺失表，不删除数据；已有表的字段升级仍需显式迁移。
    with engine.begin() as connection:
        Base.metadata.create_all(bind=connection)
        migrate_admin(connection)
        migrate_activity(connection)
        migrate_aftersales(connection)


if __name__ == "__main__":

    init_database()

    print(f"Database initialized: {len(Base.metadata.tables)} ORM tables registered.")
