"""Idempotent conversation/history table and agent metadata migration."""
from sqlalchemy import text
from .activity_models import ACTIVITY_TABLES


def migrate_activity(connection):
    for table in ACTIVITY_TABLES:table.create(connection,checkfirst=True)
    connection.execute(text("ALTER TABLE chat_messages ADD COLUMN IF NOT EXISTS agent_metadata JSONB NOT NULL DEFAULT '{}'::jsonb"))
