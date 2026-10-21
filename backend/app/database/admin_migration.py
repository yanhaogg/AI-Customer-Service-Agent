"""Idempotent local migration. Existing users become ordinary users, never admins."""
from sqlalchemy import text
from app.database.database import Base
from app.database.models import User
from app.database.homepage_models import HomepageConfig

def migrate_admin(connection):
 User.__table__.create(connection, checkfirst=True)
 connection.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS role VARCHAR(20) NOT NULL DEFAULT 'user'"))
 HomepageConfig.__table__.create(connection, checkfirst=True)
