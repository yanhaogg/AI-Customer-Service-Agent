"""bcrypt helpers compatible with existing bcrypt hashes."""
import bcrypt

def hash_password(password: str):
 return bcrypt.hashpw(password.encode('utf8'),bcrypt.gensalt(rounds=12)).decode('ascii')

def verify_password(plain_password: str, hashed_password: str):
 try:
  return bcrypt.checkpw(plain_password.encode('utf8'),hashed_password.encode('ascii'))
 except (ValueError,TypeError,UnicodeError):
  return False
