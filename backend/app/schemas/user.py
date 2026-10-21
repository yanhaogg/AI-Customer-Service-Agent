from pydantic import BaseModel, ConfigDict, Field, field_validator

class UserCreate(BaseModel):
 model_config = ConfigDict(extra='forbid')
 username: str = Field(min_length=3, max_length=50)
 password: str = Field(min_length=8)
 @field_validator('username')
 @classmethod
 def username_clean(cls, value):
  value = value.strip()
  if len(value) < 3 or any(ord(c) < 32 for c in value):
   raise ValueError('用户名至少 3 个字符，且不能包含控制字符')
  return value
 @field_validator('password')
 @classmethod
 def password_size(cls, value):
  if len(value.encode('utf8')) > 72:
   raise ValueError('密码的 UTF-8 编码不能超过 72 字节')
  return value

class UserLogin(BaseModel):
 model_config = ConfigDict(extra='forbid')
 username: str = Field(min_length=1, max_length=50)
 password: str = Field(min_length=1)
 @field_validator('password')
 @classmethod
 def password_size(cls, value):
  if len(value.encode('utf8')) > 72:
   raise ValueError('密码的 UTF-8 编码不能超过 72 字节')
  return value
