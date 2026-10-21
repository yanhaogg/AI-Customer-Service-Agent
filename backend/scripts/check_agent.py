"""Explicit live DeepSeek smoke test using public product information only."""
import argparse
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from sqlalchemy import select
from app.database.database import SessionLocal
from app.database.models import User
from app.agent.config import load_settings
from app.agent.graph import support_agent
from app.agent.specialists import SPECIALISTS


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--live',action='store_true',help='Make billable model requests to test a product tool loop')
    parser.add_argument('--username',default='superadmin')
    args=parser.parse_args()
    try:
        settings=load_settings()
        if not args.live:
            print(json.dumps({'configured':True,'model':settings.model,'mode':'manager_multi_agent','agents':list(SPECIALISTS),'live_test':False}));return 0
        with SessionLocal() as db:user_id=db.scalar(select(User.id).where(User.username==args.username))
        if user_id is None:print('The requested local account does not exist.');return 1
        result=support_agent.invoke({'user_id':user_id,'user_input':'请先使用商品查询工具，找一款耳机，告诉我商品ID、名称、演示售价和币种，并给出站内链接。','conversation_history':[]})
        print(json.dumps(result,ensure_ascii=False))
        return 0 if result['agent_metadata']['tools'] else 1
    except Exception as error:
        # API errors can contain request headers/URLs; never print raw provider exceptions.
        print(json.dumps({'live_test':'failed','error_type':type(error).__name__}));return 1


if __name__=='__main__':
    sys.stdout.reconfigure(encoding='utf8')
    raise SystemExit(main())
