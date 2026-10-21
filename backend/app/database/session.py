# FastAPI接口后续通过它获取数据库连接。

from .database import SessionLocal


def get_db():

    db = SessionLocal()

    try:
        yield db

    finally:
        db.close()
