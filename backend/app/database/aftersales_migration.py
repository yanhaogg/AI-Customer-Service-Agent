from sqlalchemy import text
from .aftersales_models import AFTERSALES_TABLES


def migrate_aftersales(connection):
    connection.execute(
        text("ALTER TABLE shop_orders ADD COLUMN IF NOT EXISTS refunded_at TIMESTAMPTZ")
    )
    connection.execute(
        text("ALTER TABLE shop_orders DROP CONSTRAINT IF EXISTS ck_shop_order_status")
    )
    connection.execute(
        text(
            "ALTER TABLE shop_orders ADD CONSTRAINT ck_shop_order_status CHECK (status IN ('pending_payment','paid','shipped','completed','cancelled','refunded'))"
        )
    )
    for statement in [
        "ALTER TABLE chat_sessions ADD COLUMN IF NOT EXISTS intent VARCHAR(30) NOT NULL DEFAULT 'general'",
        "ALTER TABLE chat_sessions ADD COLUMN IF NOT EXISTS human_status VARCHAR(20) NOT NULL DEFAULT 'none'",
        "ALTER TABLE chat_sessions ADD COLUMN IF NOT EXISTS staff_user_id INTEGER REFERENCES users(id)",
        "ALTER TABLE chat_messages ADD COLUMN IF NOT EXISTS staff_user_id INTEGER REFERENCES users(id)",
        "ALTER TABLE chat_messages DROP CONSTRAINT IF EXISTS ck_chat_message_role",
        "ALTER TABLE chat_messages ADD CONSTRAINT ck_chat_message_role CHECK (role IN ('user','assistant','human_agent'))",
    ]:
        connection.execute(text(statement))
    for table in AFTERSALES_TABLES:
        table.create(connection, checkfirst=True)
    connection.execute(
        text("ALTER TABLE refund_requests ALTER COLUMN chat_session_id DROP NOT NULL")
    )
    connection.execute(
        text(
            "ALTER TABLE refund_requests DROP CONSTRAINT IF EXISTS refund_requests_chat_session_id_fkey"
        )
    )
    connection.execute(
        text(
            "ALTER TABLE refund_requests ADD CONSTRAINT refund_requests_chat_session_id_fkey FOREIGN KEY (chat_session_id) REFERENCES chat_sessions(id) ON DELETE SET NULL"
        )
    )
