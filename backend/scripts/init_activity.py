"""Non-destructive, repeatable creation of conversation and browsing tables."""
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.database.database import engine
from app.database.activity_migration import migrate_activity


if __name__=='__main__':
    with engine.begin() as connection:
        migrate_activity(connection)
    print('Chat sessions, messages and product browsing history tables ready.')
