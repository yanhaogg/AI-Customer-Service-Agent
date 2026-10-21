from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.database.database import engine,Base
from app.database.support_task_models import SUPPORT_TASK_TABLES

if __name__=='__main__':
    with engine.begin() as connection:Base.metadata.create_all(connection,tables=SUPPORT_TASK_TABLES)
    print('Support tasks, action history and manual analysis preview tables ready.')
