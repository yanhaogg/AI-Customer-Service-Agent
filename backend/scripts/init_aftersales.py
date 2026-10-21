from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.database.database import engine
from app.database.activity_migration import migrate_activity
from app.database.aftersales_migration import migrate_aftersales

if __name__=='__main__':
    with engine.begin() as connection:
        migrate_activity(connection);migrate_aftersales(connection)
    print('Order support, refund workflow, private evidence and reminder tables ready.')
