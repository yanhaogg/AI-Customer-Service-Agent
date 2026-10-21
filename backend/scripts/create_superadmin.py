"""Offline-only superadmin provisioning. No HTTP endpoint creates privileged users."""
import argparse
import getpass
import os
from pathlib import Path
import secrets
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.auth.password import hash_password
from app.database.database import engine
from app.database.models import User
from app.database.admin_migration import migrate_admin
from app.schemas.user import UserCreate

def main():
 parser=argparse.ArgumentParser(description='本地创建超级管理员（拒绝覆盖或提升现有普通账号）')
 parser.add_argument('--username',default='superadmin')
 parser.add_argument('--generate-password',action='store_true')
 parser.add_argument('--credentials-file',type=Path,default=Path(__file__).resolve().parents[1]/'.superadmin_credentials.txt')
 parser.add_argument('--password-env',help='读取指定环境变量中的密码，避免密码进入命令行历史')
 args=parser.parse_args()
 password = secrets.token_urlsafe(24) if args.generate_password else os.getenv(args.password_env) if args.password_env else getpass.getpass('管理员密码（至少12位）: ')
 if not password or len(password)<12:
  parser.error('超级管理员密码至少 12 个字符')
 if not args.generate_password and not args.password_env and password != getpass.getpass('确认密码: '):
  parser.error('两次密码不一致')
 account=UserCreate(username=args.username,password=password)
 credential_path=args.credentials_file.resolve()
 output=None
 created_credentials=False
 try:
  with engine.begin() as connection:
   migrate_admin(connection)
   session=Session(bind=connection)
   if session.scalar(select(User.id).where(User.username==account.username)) is not None:
    raise ValueError('用户名已存在；不会覆盖密码或自动提升现有账号')
   session.add(User(username=account.username,password_hash=hash_password(password),role='super_admin'))
   session.flush()
   if args.generate_password:
    # Exclusive creation prevents overwriting an existing credential file.
    output=credential_path.open('x',encoding='utf8')
    created_credentials=True
    output.write(f'用户名: {account.username}\n密码: {password}\n登录地址: http://127.0.0.1:5173/login\n')
    output.close()
    os.chmod(credential_path,0o600)
  print(f'超级管理员已创建: {account.username}')
  if args.generate_password:print(f'初始密码已保存到本地文件: {credential_path}')
 except Exception:
  if output and not output.closed:output.close()
  if created_credentials:credential_path.unlink(missing_ok=True)
  print('创建失败，事务已回滚。请检查用户名是否已存在、密码文件是否已存在、数据库是否已准备好。',file=sys.stderr)
  return 1
 return 0
if __name__=='__main__':
 sys.stdout.reconfigure(encoding='utf8');sys.stderr.reconfigure(encoding='utf8')
 raise SystemExit(main())
