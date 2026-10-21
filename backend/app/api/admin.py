"""All homepage administration requires a verified JWT and a live DB super-admin role."""
from datetime import datetime, timezone
from typing import Annotated
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field, StrictInt, model_validator
from sqlalchemy import select, text
from sqlalchemy.orm import Session
from app.auth.dependencies import require_superadmin
from app.database.models import User
from app.database.homepage_models import HomepageConfig
from app.database.catalog_models import Product
from app.database.session import get_db
from app.api.catalog import default_home_data, configured_home_data, product_query

router=APIRouter(prefix='/api/admin',tags=['admin'],dependencies=[Depends(require_superadmin)])
PositiveId=Annotated[StrictInt,Field(gt=0)]

class HomepageUpdate(BaseModel):
 model_config=ConfigDict(extra='forbid')
 hero_product_id: PositiveId
 spotlight_ids: list[PositiveId] = Field(max_length=2)
 featured_ids: list[PositiveId] = Field(max_length=8)
 revision: Annotated[StrictInt,Field(ge=0)]
 @model_validator(mode='after')
 def unique_products(self):
  ids=[self.hero_product_id,*self.spotlight_ids,*self.featured_ids]
  if len(ids)!=len(set(ids)):
   raise ValueError('首页各区域不能重复选择同一商品')
  return self

def config_response(db,config):
 preview=configured_home_data(db,config) if config else default_home_data(db)
 return {'revision':config.revision if config else 0,
         'hero_product_id':config.hero_product_id if config else preview['hero']['id'] if preview['hero'] else None,
         'spotlight_ids':config.spotlight_ids if config else [item['id'] for item in preview['spotlights']],
         'featured_ids':config.featured_ids if config else [item['id'] for item in preview['featured']],
         'preview':preview}

@router.get('/homepage')
def get_homepage(db: Session = Depends(get_db)):
 return config_response(db,db.get(HomepageConfig,1))

@router.put('/homepage')
def save_homepage(body: HomepageUpdate, db: Session = Depends(get_db), user: User = Depends(require_superadmin)):
 try:
  db.execute(text("SET LOCAL lock_timeout = '15s'"))
  db.execute(text('SELECT pg_advisory_xact_lock(734120402)'))
  config=db.scalar(select(HomepageConfig).where(HomepageConfig.id==1).with_for_update())
  current_revision=config.revision if config else 0
  if body.revision!=current_revision:
   raise HTTPException(409,'首页配置已被修改，请重新加载后再保存')
  ids=[body.hero_product_id,*body.spotlight_ids,*body.featured_ids]
  available=db.execute(product_query().where(Product.id.in_(ids)).with_for_update(read=True)).all()
  missing=set(ids)-{row[0].id for row in available}
  if missing:
   raise HTTPException(422,'部分商品不存在或不可展示，请重新选择')
  if config is None:
   config=HomepageConfig(id=1)
   db.add(config)
  config.hero_product_id=body.hero_product_id
  config.spotlight_ids=body.spotlight_ids
  config.featured_ids=body.featured_ids
  config.revision=current_revision+1
  config.updated_by=user.id
  config.updated_at=datetime.now(timezone.utc)
  db.flush()
  result=config_response(db,config)
  db.commit()
  return result
 except Exception:
  db.rollback()
  raise
