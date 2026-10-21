"""Idempotently add per-account conversation read state without modifying messages."""
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.database.database import engine
from app.database.activity_models import ChatReadState

if __name__=='__main__':
    ChatReadState.__table__.create(engine,checkfirst=True)
    print('Chat read states ready.')
