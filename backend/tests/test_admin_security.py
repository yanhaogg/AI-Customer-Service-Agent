"""Rollback-only PostgreSQL tests for role authorization and homepage management."""
from datetime import datetime, timedelta, timezone
from pathlib import Path
import importlib.util
import json
import sys
import unittest
import uuid
import base64
from io import BytesIO
from tempfile import TemporaryDirectory
from unittest.mock import patch
from PIL import Image
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from fastapi import FastAPI
from fastapi.testclient import TestClient
from jose import jwt
from sqlalchemy import select, text, update
from sqlalchemy.orm import Session
from app.auth.jwt import create_access_token, SECRET_KEY, ALGORITHM
from app.auth.password import hash_password
from app.database.database import engine, Base
from app.database.models import User
from app.database.catalog_models import CATALOG_TABLES, Product, ProductPriceRecord, ProductSource
from app.database.homepage_models import HomepageConfig
from app.database.shop_models import SHOP_TABLES
from app.database.activity_models import ACTIVITY_TABLES
from app.database.aftersales_models import AFTERSALES_TABLES
from app.database.session import get_db
from app.api.auth import router as auth_router
from app.api.admin import router as admin_router
from app.api.catalog import router as catalog_router
from app.api.admin_products import router as admin_products_router

class AdminSecurityTests(unittest.TestCase):
 def test_registration_roles_tokens_homepage_and_revocation(self):
  schema='admin_test_'+uuid.uuid4().hex
  connection=engine.connect();transaction=connection.begin()
  try:
   connection.execute(text(f'CREATE SCHEMA "{schema}"'))
   connection=connection.execution_options(schema_translate_map={None:schema})
   Base.metadata.create_all(connection,tables=[User.__table__,*CATALOG_TABLES,HomepageConfig.__table__,*SHOP_TABLES,*ACTIVITY_TABLES,*AFTERSALES_TABLES])
   importer_path=Path(__file__).resolve().parents[1]/'scripts/import_products.py'
   spec=importlib.util.spec_from_file_location('admin_test_importer',importer_path)
   importer=importlib.util.module_from_spec(spec);spec.loader.exec_module(importer)
   root=Path(__file__).resolve().parents[2]/'product_materials'
   materials=importer.load_materials(root/'products.jsonl',root)[:12]
   importer.import_materials(connection,materials)
   session=Session(bind=connection,join_transaction_mode='create_savepoint')
   admin=User(username='test_admin',password_hash=hash_password('Admin-test-Password123'),role='super_admin')
   regular=User(username='test_regular',password_hash=hash_password('Regular-test-Password123'),role='user')
   session.add_all([admin,regular]);session.flush()
   admin_id,regular_id=admin.id,regular.id;session.commit();session.close()
   app=FastAPI();app.include_router(auth_router,prefix='/auth');app.include_router(catalog_router);app.include_router(admin_router);app.include_router(admin_products_router)
   def override_db():
    with Session(bind=connection,join_transaction_mode='create_savepoint') as db:yield db
   app.dependency_overrides[get_db]=override_db
   client=TestClient(app)
   admin_login=client.post('/auth/login',json={'username':'test_admin','password':'Admin-test-Password123'})
   self.assertEqual(admin_login.status_code,200)
   ah={'Authorization':'Bearer '+admin_login.json()['access_token']}
   uh={'Authorization':'Bearer '+create_access_token({'user_id':regular_id,'role':'super_admin'})}
   # Public registration must not accept any role or permission fields.
   for extra in [{'role':'super_admin'},{'is_superuser':True},{'role':'user'}]:
    response=client.post('/auth/register',json={'username':'attack_user','password':'Ordinary-pass123',**extra})
    self.assertEqual(response.status_code,422)
   response=client.post('/auth/register',json={'username':'public_user','password':'Ordinary-pass123'})
   self.assertEqual(response.status_code,201)
   self.assertEqual(connection.scalar(select(User.role).where(User.username=='public_user')),'user')
   self.assertEqual(client.get('/auth/me',headers=uh).json()['role'],'user')
   for method in ['get','put']:
    self.assertEqual(getattr(client,method)('/api/admin/homepage',**({'json':{}} if method=='put' else {})).status_code,401)
    self.assertEqual(getattr(client,method)('/api/admin/homepage',headers=uh,**({'json':{}} if method=='put' else {})).status_code,403)
   for payload,key,algorithm in [
    ({'user_id':admin_id,'exp':datetime.now(timezone.utc)+timedelta(hours=1)},'invalid-signing-secret',ALGORITHM),
    ({'user_id':admin_id,'exp':datetime.now(timezone.utc)-timedelta(seconds=10)},SECRET_KEY,ALGORITHM),
    ({'user_id':admin_id},SECRET_KEY,ALGORITHM),
    ({'user_id':admin_id,'exp':datetime.now(timezone.utc)+timedelta(hours=1)},SECRET_KEY,'HS384'),
   ]:
    forged={'Authorization':'Bearer '+jwt.encode(payload,key,algorithm=algorithm)}
    self.assertEqual(client.get('/api/admin/homepage',headers=forged).status_code,401)
   initial=client.get('/api/admin/homepage',headers=ah)
   self.assertEqual(initial.status_code,200);self.assertEqual(initial.json()['revision'],0)
   ids=connection.execute(select(Product.id).order_by(Product.id)).scalars().all()
   body={'hero_product_id':ids[1],'spotlight_ids':[ids[0],ids[2]],'featured_ids':[ids[6],ids[5],ids[4]],'revision':0}
   before=client.get('/api/catalog/home').json()['hero']['id']
   invalid={**body,'spotlight_ids':[ids[1]]}
   self.assertEqual(client.put('/api/admin/homepage',headers=ah,json=invalid).status_code,422)
   self.assertEqual(client.put('/api/admin/homepage',headers=ah,json={**body,'hero_product_id':9999999}).status_code,422)
   self.assertEqual(client.get('/api/catalog/home').json()['hero']['id'],before)
   self.assertEqual(client.put('/api/admin/homepage',headers=ah,json={**body,'hero_product_id':True}).status_code,422)
   saved=client.put('/api/admin/homepage',headers=ah,json=body)
   self.assertEqual(saved.status_code,200,saved.text);self.assertEqual(saved.json()['revision'],1)
   public=client.get('/api/catalog/home').json()
   self.assertEqual(public['hero']['id'],body['hero_product_id'])
   self.assertEqual([p['id'] for p in public['spotlights']],body['spotlight_ids'])
   self.assertEqual([p['id'] for p in public['featured']],body['featured_ids'])
   self.assertEqual(client.put('/api/admin/homepage',headers=ah,json=body).status_code,409)
   # Every management route must enforce backend authorization, regardless of payload.
   routes=[('get','/api/admin/products'),('get','/api/admin/product-categories'),
           ('get',f'/api/admin/products/{ids[0]}'),('post','/api/admin/products'),
           ('put',f'/api/admin/products/{ids[0]}'),('delete',f'/api/admin/products/{ids[0]}'),
           ('post','/api/admin/product-images')]
   for method,path in routes:
    kwargs={'json':{}} if method in ('post','put') else {}
    self.assertEqual(getattr(client,method)(path,**kwargs).status_code,401,(method,path))
    self.assertEqual(getattr(client,method)(path,headers=uh,**kwargs).status_code,403,(method,path))
   category=client.get('/api/admin/product-categories',headers=ah).json()['items'][0]
   new={'category_id':category['id'],'name_original':'Test Everyday Speaker','name_zh':'测试日常音箱',
        'brand':'ServAI','model':'S1','description_original':'A compact everyday speaker.',
        'introduction_zh':'适合日常使用的便携音箱。','specs':{'连接':'蓝牙'},'price_amount':'199.00','price_currency':'CNY'}
   for invalid in [{**new,'category_id':999999},{**new,'price_amount':'-1'},{**new,'name_original':'  '},
                   {**new,'image_asset_id':999999},{**new,'status':'published'}]:
    self.assertEqual(client.post('/api/admin/products',headers=ah,json=invalid).status_code,422)
   # Upload to a temporary material root, so no test files are left in the real library.
   with TemporaryDirectory() as temporary, patch('app.api.admin_products.MATERIALS_ROOT',Path(temporary)):
    output=BytesIO();Image.new('RGB',(24,24),'blue').save(output,format='PNG')
    image_body={'data':base64.b64encode(output.getvalue()).decode()}
    image_response=client.post('/api/admin/product-images',headers=ah,json=image_body)
    self.assertEqual(image_response.status_code,201,image_response.text)
    asset_id=image_response.json()['asset_id'];new['image_asset_id']=asset_id
    self.assertEqual(client.post('/api/admin/product-images',headers=ah,json=image_body).json()['asset_id'],asset_id)
    self.assertEqual(client.post('/api/admin/product-images',headers=ah,json={'data':'invalid!'}).status_code,422)
    created=client.post('/api/admin/products',headers=ah,json=new)
    self.assertEqual(created.status_code,201,created.text)
    product_id=created.json()['id']
    public=client.get(f'/api/catalog/products/{product_id}')
    self.assertEqual(public.status_code,200);self.assertEqual(public.json()['name'],'测试日常音箱')
    self.assertEqual(public.json()['image']['url'],image_response.json()['url'])
    self.assertEqual(public.json()['price']['amount'],'199.00')
    initial_version=created.json()['updated_at']
    edited={**new,'name_zh':'已修改的日常音箱','price_amount':'209.00','updated_at':initial_version}
    updated=client.put(f'/api/admin/products/{product_id}',headers=ah,json=edited)
    self.assertEqual(updated.status_code,200,updated.text)
    self.assertEqual(client.get(f'/api/catalog/products/{product_id}').json()['name'],'已修改的日常音箱')
    self.assertEqual(client.put(f'/api/admin/products/{product_id}',headers=ah,json=edited).status_code,409)
    # Deleting a configured hero replaces it with an available item and invalidates old revisions.
    homepage={'hero_product_id':product_id,'spotlight_ids':[ids[0]],'featured_ids':[ids[1]],'revision':1}
    self.assertEqual(client.put('/api/admin/homepage',headers=ah,json=homepage).status_code,200)
    self.assertEqual(client.delete(f'/api/admin/products/{product_id}',headers=ah).status_code,204)
    self.assertEqual(client.get(f'/api/catalog/products/{product_id}').status_code,404)
    self.assertEqual(client.get(f'/api/admin/products/{product_id}',headers=ah).status_code,404)
    self.assertEqual(client.get('/api/admin/products?q=Everyday',headers=ah).json()['total'],0)
    self.assertNotEqual(client.get('/api/catalog/home').json()['hero']['id'],product_id)
    self.assertEqual(client.get('/api/admin/homepage',headers=ah).json()['revision'],3)
    self.assertEqual(connection.scalar(select(Product.status).where(Product.id==product_id)),'deleted')
    self.assertEqual(client.delete(f'/api/admin/products/{product_id}',headers=ah).status_code,404)
   # Editing an imported item preserves the original evidence and source price history.
   imported=client.get(f'/api/admin/products/{ids[2]}',headers=ah).json()
   source_before=connection.scalar(select(ProductSource.raw_data).where(ProductSource.product_id==ids[2]))
   specs_before=connection.scalar(select(Product.specs).where(Product.id==ids[2]))
   imported_body={key:imported[key] for key in ['category_id','name_original','name_zh','brand','model',
                    'description_original','introduction_zh','specs','image_asset_id','updated_at']}
   imported_body.update(brand=imported_body['brand'] or '',model=imported_body['model'] or '',
                        price_amount='42.50',price_currency='CNY',specs={'测试参数':'已核实'})
   changed=client.put(f'/api/admin/products/{ids[2]}',headers=ah,json=imported_body)
   self.assertEqual(changed.status_code,200,changed.text)
   self.assertEqual(connection.scalar(select(ProductSource.raw_data).where(ProductSource.product_id==ids[2],
                    ProductSource.source_name!='admin')),source_before)
   specs_after=connection.scalar(select(Product.specs).where(Product.id==ids[2]))
   self.assertEqual({k:v for k,v in specs_after.items() if k!='verified'},
                    {k:v for k,v in specs_before.items() if k!='verified'})
   self.assertEqual(len(connection.execute(select(ProductPriceRecord.id).where(ProductPriceRecord.product_id==ids[2])).all()),2)
   imported_body.update(updated_at=changed.json()['updated_at'],image_asset_id=None)
   self.assertEqual(client.put(f'/api/admin/products/{ids[2]}',headers=ah,json=imported_body).status_code,200)
   self.assertIsNone(client.get(f'/api/catalog/products/{ids[2]}').json()['image'])
   # A previously issued token loses admin privileges as soon as DB role changes.
   connection.execute(update(User).where(User.id==admin_id).values(role='user'))
   self.assertEqual(client.get('/api/admin/homepage',headers=ah).status_code,403)
   self.assertEqual(client.put('/api/admin/homepage',headers=ah,json={**body,'revision':1}).status_code,403)
   self.assertEqual(client.post('/api/admin/products',headers=ah,json=new).status_code,403)
   self.assertEqual(client.delete(f'/api/admin/products/{ids[0]}',headers=ah).status_code,403)
   self.assertEqual(client.post('/auth/register-admin',json={}).status_code,404)
  finally:
   transaction.rollback();connection.close()
  with engine.connect() as check:
   self.assertEqual(check.scalar(text('select count(*) from pg_namespace where nspname=:name'),{'name':schema}),0)
if __name__=='__main__':unittest.main()
