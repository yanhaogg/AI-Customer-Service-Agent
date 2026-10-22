import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[2] / ".env")

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase

#DATABASE_URL = "postgresql://" "postgres:123456@localhost:5432/customer_service"
DATABASE_URL = "postgresql://postgres:123456@localhost:5432/customer_service"

DATABASE_URL = os.getenv("DATABASE_URL") or DATABASE_URL

engine = create_engine(DATABASE_URL)


SessionLocal = sessionmaker(bind=engine)


class Base(DeclarativeBase):
    """所有 ORM 模型共用的声明式基类，表定义统一注册到 metadata。"""

    pass
