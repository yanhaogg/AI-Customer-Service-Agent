"""Transactional, repeatable migration: one customer conversation per order."""
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.database.database import engine
from app.database.order_chat_migration import migrate_order_chats

if __name__=='__main__':
    with engine.begin() as connection:result=migrate_order_chats(connection)
    print(result)
