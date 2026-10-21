"""JWT authentication. Authorization always uses the current database role."""
from datetime import datetime, timedelta, timezone
import os
from pathlib import Path
from dotenv import load_dotenv
from jose import jwt
load_dotenv(Path(__file__).resolve().parents[2] / '.env')
SECRET_KEY = os.getenv('SECRET_KEY')
ALGORITHM = 'HS256'

def create_access_token(data: dict):
 if not SECRET_KEY:
  raise RuntimeError('SECRET_KEY is not configured')
 payload = {**data, 'exp': datetime.now(timezone.utc) + timedelta(hours=24)}
 return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)
