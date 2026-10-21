"""Real PostgreSQL integration/concurrency checks in disposable isolated schemas."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys
from threading import Barrier
import unittest
from uuid import uuid4
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select, text, update
from sqlalchemy.orm import Session
from sqlalchemy.schema import DropSchema
from app.database.database import engine, Base
from app.database.models import User
from app.database.catalog_models import CATALOG_TABLES, CatalogCategory, Product
from app.database.shop_models import SHOP_TABLES, SaleOffer, ShopOrder, ShopOrderItem
from app.database.session import get_db
from app.database.activity_models import ACTIVITY_TABLES
from app.database.aftersales_models import AFTERSALES_TABLES
from app.database.support_task_models import SUPPORT_TASK_TABLES
from app.auth.jwt import create_access_token
from app.api.shop import router, admin_router
from app.api.catalog import router as catalog_router


class ShopTests(unittest.TestCase):
    def setUp(self):
        self.schema='shop_test_'+uuid4().hex
        self.db_engine=engine.execution_options(schema_translate_map={None:self.schema})
        with self.db_engine.begin() as connection:
            connection.execute(text(f'CREATE SCHEMA "{self.schema}"'))
            Base.metadata.create_all(connection,tables=[User.__table__,*CATALOG_TABLES,*SHOP_TABLES,*ACTIVITY_TABLES,*AFTERSALES_TABLES,*SUPPORT_TASK_TABLES])
        with Session(self.db_engine) as db:
            users=[User(username=f'u{i}',password_hash='unused',role='super_admin' if i==2 else 'user') for i in range(3)]
            db.add_all(users);db.flush();self.users=[u.id for u in users]
            category=CatalogCategory(code='test',name='测试分类');db.add(category);db.flush()
            self.products=[]
            for i in range(3):
                product=Product(import_key=f'test:{i}',category_id=category.id,name_original=f'Product {i}',
                    name_zh=f'商品{i}',description_original='Original description',introduction_zh='介绍',status='published')
                db.add(product);db.flush();self.products.append(product.id)
                db.add(SaleOffer(product_id=product.id,price='12.50',currency='USD' if i==2 else 'CNY',stock=5,is_active=True))
            db.commit()
        app=FastAPI();app.include_router(router);app.include_router(admin_router);app.include_router(catalog_router)
        def override():
            with Session(self.db_engine) as db:yield db
        app.dependency_overrides[get_db]=override
        self.client=TestClient(app)
        self.headers=[{'Authorization':'Bearer '+create_access_token({'user_id':i})} for i in self.users]
        self.address_body={'recipient':'测试收货人','phone':'13800000000','region':'广东省 深圳市 南山区',
                           'detail':'测试路 1 号 101 室','postal_code':'518000','is_default':True}
        self.addresses=[self.client.post('/api/shop/addresses',headers=h,json=self.address_body).json()['id'] for h in self.headers[:2]]

    def tearDown(self):
        self.client.close()
        if not self.schema.startswith('shop_test_') or len(self.schema)!=42:
            raise AssertionError('Unexpected test schema')
        with engine.begin() as connection:
            connection.execute(DropSchema(self.schema,cascade=True))

    def checkout_body(self, user=0, product=None, quantity=1):
        return {'items':[{'product_id':product or self.products[0],'quantity':quantity,'expected_price':'12.50','currency':'CNY'}],
                'address_id':self.addresses[user],'request_key':uuid4().hex,'note':'测试订单'}

    def stock(self,product=None):
        with Session(self.db_engine) as db:return db.get(SaleOffer,product or self.products[0]).stock

    def test_cart_checkout_snapshots_idempotence_and_fulfillment(self):
        c=self.client;h=self.headers[0];ah=self.headers[2];p=self.products
        added=c.post('/api/shop/cart',headers=h,json={'product_id':p[0],'quantity':2})
        self.assertEqual(added.status_code,201,added.text)
        extra=c.post('/api/shop/cart',headers=h,json={'product_id':p[1],'quantity':1}).json()['id']
        preview=c.post('/api/shop/checkout/preview',headers=h,json={'items':[{'product_id':p[0],'quantity':2}]})
        self.assertEqual(preview.json()['total'],'25.00')
        body=self.checkout_body(quantity=2);body['cart_item_ids']=[added.json()['id']]
        response=c.post('/api/shop/orders',headers=h,json=body)
        self.assertEqual(response.status_code,201,response.text)
        order=response.json();oid=order['id'];self.assertEqual(order['total'],'25.00');self.assertEqual(self.stock(),3)
        repeated=c.post('/api/shop/orders',headers=h,json=body)
        self.assertEqual(repeated.json()['id'],oid);self.assertEqual(self.stock(),3)
        self.assertEqual(c.post('/api/shop/orders',headers=h,json={**body,'note':'changed'}).status_code,409)
        self.assertEqual([i['id'] for i in c.get('/api/shop/cart',headers=h).json()['items']],[extra])
        new_address={**self.address_body,'detail':'修改后的其他地址 999 室'}
        self.assertEqual(c.put(f'/api/shop/addresses/{self.addresses[0]}',headers=h,json=new_address).status_code,200)
        with Session(self.db_engine) as db:
            db.execute(update(Product).where(Product.id==p[0]).values(name_zh='商品改名'))
            db.execute(update(SaleOffer).where(SaleOffer.product_id==p[0]).values(price='99.00'));db.commit()
        snapshot=c.get(f'/api/shop/orders/{oid}',headers=h).json()
        self.assertEqual(snapshot['shipping_address']['detail'],self.address_body['detail'])
        self.assertEqual(snapshot['items'][0]['name'],'商品0');self.assertEqual(snapshot['items'][0]['unit_price'],'12.50')
        self.assertEqual(c.post(f'/api/admin/orders/{oid}/ship',headers=ah,json={'carrier':'测试快递','tracking_number':'TEST123'}).status_code,409)
        self.assertEqual(c.post(f'/api/shop/orders/{oid}/pay',headers=h).json()['status'],'paid')
        self.assertEqual(c.post(f'/api/shop/orders/{oid}/pay',headers=h).status_code,200)
        self.assertEqual(c.post(f'/api/shop/orders/{oid}/cancel',headers=h).status_code,409)
        self.assertEqual(c.post(f'/api/admin/orders/{oid}/ship',headers=h,json={'carrier':'测试快递','tracking_number':'TEST123'}).status_code,403)
        self.assertEqual(c.post(f'/api/admin/orders/{oid}/ship',headers=ah,json={'carrier':'测试快递','tracking_number':'TEST123'}).json()['status'],'shipped')
        self.assertEqual(c.post(f'/api/shop/orders/{oid}/complete',headers=h).json()['status'],'completed')
        self.assertEqual(c.get('/api/shop/orders?status=completed',headers=h).json()['total'],1)
        self.assertEqual(c.get('/api/admin/orders',headers=ah).json()['total'],1)

    def test_authorization_validation_expiry_and_inventory(self):
        c=self.client;h=self.headers[0];other=self.headers[1];p=self.products;body=self.checkout_body()
        self.assertEqual(c.post('/api/shop/orders',json=body).status_code,401)
        self.assertEqual(c.post('/api/shop/orders',headers=h,json={**body,'address_id':self.addresses[1]}).status_code,404)
        self.assertEqual(c.post('/api/shop/orders',headers=h,json={**body,'total':'0.01'}).status_code,422)
        self.assertEqual(c.post('/api/shop/orders',headers=h,json={**body,'items':[{**body['items'][0],'expected_price':'0.01'}]}).status_code,409)
        self.assertEqual(c.post('/api/shop/cart',headers=h,json={'product_id':p[0],'quantity':6}).status_code,409)
        self.assertEqual(c.post('/api/shop/cart',headers=h,json={'product_id':p[0],'quantity':True}).status_code,422)
        self.assertEqual(c.post('/api/shop/checkout/preview',headers=h,json={'items':[{'product_id':p[0],'quantity':1},{'product_id':p[2],'quantity':1}]}).status_code,422)
        self.assertEqual(c.post('/api/shop/orders',headers=h,json={**body,'items':body['items']*2}).status_code,422)
        oid=c.post('/api/shop/orders',headers=h,json=body).json()['id'];self.assertEqual(self.stock(),4)
        for suffix in ('','/pay','/cancel','/complete'):
            response=c.get(f'/api/shop/orders/{oid}',headers=other) if not suffix else c.post(f'/api/shop/orders/{oid}{suffix}',headers=other)
            self.assertEqual(response.status_code,404)
        self.assertEqual(c.delete(f'/api/shop/addresses/{self.addresses[0]}',headers=other).status_code,404)
        ci=c.post('/api/shop/cart',headers=h,json={'product_id':p[0],'quantity':1}).json()['id']
        self.assertEqual(c.delete(f'/api/shop/cart/{ci}',headers=other).status_code,404)
        self.assertEqual(c.patch(f'/api/shop/cart/{ci}',headers=other,json={'quantity':2}).status_code,404)
        self.assertEqual(c.get('/api/admin/orders',headers=h).status_code,403)
        self.assertEqual(c.put(f'/api/admin/offers/{p[0]}',headers=h,json={}).status_code,403)
        self.assertEqual(c.post(f'/api/shop/orders/{oid}/cancel',headers=h).json()['status'],'cancelled')
        self.assertEqual(self.stock(),5)
        self.assertEqual(c.post(f'/api/shop/orders/{oid}/cancel',headers=h).status_code,200);self.assertEqual(self.stock(),5)
        expiring=c.post('/api/shop/orders',headers=h,json=self.checkout_body()).json()['id']
        with Session(self.db_engine) as db:
            db.execute(update(ShopOrder).where(ShopOrder.id==expiring).values(expires_at=datetime.now(timezone.utc)-timedelta(seconds=1)));db.commit()
        self.assertEqual(c.get(f'/api/shop/orders/{expiring}',headers=h).json()['status'],'cancelled')
        self.assertEqual(self.stock(),5)
        self.assertEqual(c.post(f'/api/shop/orders/{expiring}/pay',headers=h).status_code,409)
        self.assertEqual(c.get(f'/api/shop/orders/{expiring}',headers=h).status_code,200);self.assertEqual(self.stock(),5)
        # Offer updates are versioned independently of historical catalog prices.
        offer=c.get(f'/api/admin/offers/{p[0]}',headers=self.headers[2]).json()['offer']
        update_body={**offer,'stock':8,'is_active':False}
        self.assertEqual(c.put(f'/api/admin/offers/{p[0]}',headers=self.headers[2],json=update_body).status_code,200)
        self.assertEqual(c.put(f'/api/admin/offers/{p[0]}',headers=self.headers[2],json=update_body).status_code,409)
        self.assertEqual(c.post('/api/shop/orders',headers=h,json=self.checkout_body()).status_code,409)

    def test_concurrent_last_item_and_duplicate_checkout(self):
        with Session(self.db_engine) as db:
            db.get(SaleOffer,self.products[0]).stock=1;db.commit()
        barrier=Barrier(2)
        def place(index):
            barrier.wait(timeout=10)
            return self.client.post('/api/shop/orders',headers=self.headers[index],json=self.checkout_body(user=index))
        with ThreadPoolExecutor(max_workers=2) as executor:
            results=list(executor.map(place,[0,1]))
        self.assertEqual(sorted(r.status_code for r in results),[201,409]);self.assertEqual(self.stock(),0)
        winner=next(r.json() for r in results if r.status_code==201)
        owner=next(i for i,r in enumerate(results) if r.status_code==201)
        self.client.post(f"/api/shop/orders/{winner['id']}/cancel",headers=self.headers[owner])
        self.assertEqual(self.stock(),1)
        body=self.checkout_body();barrier=Barrier(2)
        def duplicate(_):
            barrier.wait(timeout=10)
            return self.client.post('/api/shop/orders',headers=self.headers[0],json=body)
        with ThreadPoolExecutor(max_workers=2) as executor:
            results=list(executor.map(duplicate,[0,1]))
        self.assertEqual([r.status_code for r in results],[201,201])
        self.assertEqual(results[0].json()['id'],results[1].json()['id']);self.assertEqual(self.stock(),0)

    def test_multiselect_cart_atomic_validation_and_address_defaults(self):
        c=self.client;h=self.headers[0];p=self.products
        invalid_phone={**self.address_body,'phone':'------'}
        self.assertEqual(c.post('/api/shop/addresses',headers=h,json=invalid_phone).status_code,422)
        second=c.post('/api/shop/addresses',headers=h,json={**self.address_body,'recipient':'第二联系人'}).json()
        addresses=c.get('/api/shop/addresses',headers=h).json()['items']
        self.assertEqual(sum(a['is_default'] for a in addresses),1);self.assertEqual(addresses[0]['id'],second['id'])
        self.assertEqual(c.delete(f"/api/shop/addresses/{second['id']}",headers=h).status_code,204)
        self.assertTrue(c.get('/api/shop/addresses',headers=h).json()['items'][0]['is_default'])
        cart_ids=[]
        for product in p:
            response=c.post('/api/shop/cart',headers=h,json={'product_id':product,'quantity':1})
            self.assertEqual(response.status_code,201,response.text);cart_ids.append(response.json()['id'])
        body=self.checkout_body();body['items'].append({'product_id':p[1],'quantity':1,'expected_price':'12.50','currency':'CNY'})
        body['cart_item_ids']=cart_ids[:2]
        self.assertEqual(c.patch(f'/api/shop/cart/{cart_ids[0]}',headers=h,json={'quantity':2}).status_code,200)
        self.assertEqual(c.post('/api/shop/orders',headers=h,json=body).status_code,409)
        self.assertEqual(self.stock(),5);self.assertEqual(self.stock(p[1]),5)
        body['items'][0]['quantity']=2
        response=c.post('/api/shop/orders',headers=h,json=body)
        self.assertEqual(response.status_code,201,response.text)
        self.assertEqual(response.json()['total'],'37.50');self.assertEqual(len(response.json()['items']),2)
        self.assertEqual([i['id'] for i in c.get('/api/shop/cart',headers=h).json()['items']],[cart_ids[2]])
        self.assertEqual(self.stock(),3);self.assertEqual(self.stock(p[1]),4)
        oid=response.json()['id']
        # Source product deletion does not erase the ordered product/address snapshots.
        with Session(self.db_engine) as db:
            db.execute(update(Product).where(Product.id==p[0]).values(status='deleted'));db.commit()
        self.assertEqual(c.delete(f'/api/shop/addresses/{self.addresses[0]}',headers=h).status_code,204)
        self.assertEqual(len(c.get(f'/api/shop/orders/{oid}',headers=h).json()['items']),2)
        self.assertEqual(c.post(f'/api/shop/orders/{oid}/cancel',headers=h).status_code,200)
        self.assertEqual(self.stock(),5);self.assertEqual(self.stock(p[1]),5)


if __name__=='__main__':unittest.main()
