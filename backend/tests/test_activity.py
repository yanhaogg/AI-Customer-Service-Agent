"""History persistence, isolation, retries and concurrency in disposable PostgreSQL schemas."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime,timedelta,timezone
from threading import Event
from unittest.mock import patch
from uuid import uuid4
import unittest
import test_shop as fixtures
from sqlalchemy import func,select,update
from sqlalchemy.orm import Session
from app.database.database import Base
from app.database.activity_models import ACTIVITY_TABLES,ChatMessage,ChatSession
from app.database.catalog_models import Product
from app.api.activity import router


class ActivityTests(unittest.TestCase):
    def setUp(self):
        fixtures.ShopTests.setUp(self)
        with self.db_engine.begin() as connection:Base.metadata.create_all(connection,tables=ACTIVITY_TABLES)
        self.client.app.include_router(router)

    def tearDown(self):fixtures.ShopTests.tearDown(self)

    def new_session(self,user=0,**kwargs):
        response=self.client.post('/api/activity/sessions',headers=self.headers[user],json={'title':'测试会话',**kwargs})
        self.assertEqual(response.status_code,201,response.text)
        return response.json()['id']

    def test_messages_persist_context_isolation_and_idempotency(self):
        c=self.client;h=self.headers[0]
        body=fixtures.ShopTests.checkout_body(self)
        order=c.post('/api/shop/orders',headers=h,json=body).json()
        sid=self.new_session(product_id=self.products[0],order_number=order['number'])
        self.assertEqual(c.post('/api/activity/sessions',headers=self.headers[1],json={'order_number':order['number']}).status_code,404)
        self.assertEqual(c.post('/api/activity/sessions',headers=h,json={'product_id':999999}).status_code,404)
        payload={'content':'你好，我想咨询这款商品','request_key':uuid4().hex}
        with patch('app.services.chat.support_agent.invoke',return_value={'answer':'这是测试回复。'}) as invoke:
            response=c.post(f'/api/activity/sessions/{sid}/messages',headers=h,json=payload)
            self.assertEqual(response.status_code,200,response.text)
            self.assertEqual([m['role'] for m in response.json()['items']],['user','assistant'])
            self.assertEqual(c.post(f'/api/activity/sessions/{sid}/messages',headers=h,json=payload).status_code,200)
            self.assertEqual(invoke.call_count,1)
            state=invoke.call_args.args[0]
            self.assertEqual(state['user_id'],self.users[0]);self.assertEqual(state['order_id'],order['number'])
            self.assertEqual(state['conversation_history'][-1]['content'],payload['content'])
        detail=c.get(f'/api/activity/sessions/{sid}',headers=h).json()
        self.assertEqual(len(detail['items']),2);self.assertEqual(detail['items'][1]['content'],'这是测试回复。')
        self.assertEqual(detail['session']['product_id'],self.products[0]);self.assertEqual(detail['session']['order_id'],order['id'])
        self.assertEqual(c.get('/api/activity/sessions',params={'q':order['number']},headers=h).json()['total'],1)
        self.assertEqual(c.get('/api/activity/sessions',headers=self.headers[1]).json()['total'],0)
        self.assertEqual(c.post(f'/api/activity/sessions/{sid}/messages',headers=h,json={**payload,'content':'changed'}).status_code,409)
        for user in (1,2):
            for method,path in [('get',f'/api/activity/sessions/{sid}'),('delete',f'/api/activity/sessions/{sid}'),('post',f'/api/activity/sessions/{sid}/messages')]:
                args={'json':payload} if method=='post' else {}
                self.assertEqual(getattr(c,method)(path,headers=self.headers[user],**args).status_code,404)
        self.assertEqual(c.post('/api/activity/sessions',headers=h,json={'user_id':self.users[1]}).status_code,422)
        self.assertEqual(c.post(f'/api/activity/sessions/{sid}/messages',headers=h,json={**payload,'role':'assistant'}).status_code,422)
        self.assertEqual(c.get('/api/activity/sessions').status_code,401)
        self.assertEqual(c.post(f'/api/activity/sessions/{sid}/messages',json=payload).status_code,401)
        self.assertEqual(c.delete(f'/api/activity/sessions/{sid}',headers=h).status_code,204)
        with Session(self.db_engine) as db:
            self.assertEqual(db.scalar(select(func.count()).select_from(ChatMessage).where(ChatMessage.session_id==sid)),0)

    def test_failed_generation_saved_retry_and_message_pagination(self):
        c=self.client;h=self.headers[0];sid=self.new_session()
        body={'content':'回复失败后请重试','request_key':uuid4().hex}
        def fail(_):
            with Session(self.db_engine) as db:
                self.assertEqual(db.scalar(select(func.count()).select_from(ChatMessage).where(ChatMessage.session_id==sid)),2)
            raise RuntimeError('simulated provider outage')
        with patch('app.services.chat.support_agent.invoke',side_effect=fail):
            response=c.post(f'/api/activity/sessions/{sid}/messages',headers=h,json=body)
        self.assertEqual(response.status_code,200,response.text)
        self.assertEqual(response.json()['items'][1]['status'],'failed')
        message_ids=[m['id'] for m in response.json()['items']]
        with patch('app.services.chat.support_agent.invoke',return_value={'answer':'重试成功'}):
            response=c.post(f'/api/activity/sessions/{sid}/messages',headers=h,json=body)
        self.assertEqual([m['id'] for m in response.json()['items']],message_ids)
        self.assertEqual(response.json()['items'][1]['content'],'重试成功')
        with Session(self.db_engine) as db:
            for index in range(26):
                key=uuid4().hex
                db.add_all([ChatMessage(session_id=sid,request_key=key,role='user',content=f'问题{index}',status='completed'),
                            ChatMessage(session_id=sid,request_key=key,role='assistant',content=f'回复{index}',status='completed')])
            db.commit()
        latest=c.get(f'/api/activity/sessions/{sid}',headers=h).json()
        self.assertEqual(len(latest['items']),50);self.assertTrue(latest['has_more'])
        earlier=c.get(f"/api/activity/sessions/{sid}?before_id={latest['items'][0]['id']}",headers=h).json()
        self.assertEqual(len(earlier['items']),4);self.assertFalse(earlier['has_more'])
        self.assertFalse({m['id'] for m in latest['items']} & {m['id'] for m in earlier['items']})

    def test_pending_and_late_reply_cannot_overwrite_retry(self):
        c=self.client;h=self.headers[0];sid=self.new_session();started=Event();finish=Event()
        body={'content':'测试并发回复','request_key':uuid4().hex}
        def slow(_):
            started.set()
            if not finish.wait(10):raise RuntimeError('timeout in test')
            return {'answer':'过期的原始回复'}
        with ThreadPoolExecutor(max_workers=1) as executor:
            with patch('app.services.chat.support_agent.invoke',side_effect=slow):
                original=executor.submit(c.post,f'/api/activity/sessions/{sid}/messages',headers=h,json=body)
                self.assertTrue(started.wait(5))
                repeated=c.post(f'/api/activity/sessions/{sid}/messages',headers=h,json=body)
                self.assertEqual(repeated.status_code,202)
                self.assertEqual(c.post(f'/api/activity/sessions/{sid}/messages',headers=h,json={**body,'request_key':uuid4().hex}).status_code,409)
                with Session(self.db_engine) as db:
                    db.execute(update(ChatMessage).where(ChatMessage.session_id==sid,ChatMessage.role=='assistant').values(
                        updated_at=datetime.now(timezone.utc)-timedelta(minutes=3)));db.commit()
                recovered=c.get(f'/api/activity/sessions/{sid}',headers=h)
                self.assertEqual(recovered.json()['items'][-1]['status'],'failed')
                with patch('app.services.chat.support_agent.invoke',return_value={'answer':'新的重试回复'}):
                    self.assertEqual(c.post(f'/api/activity/sessions/{sid}/messages',headers=h,json=body).status_code,200)
                finish.set();self.assertEqual(original.result(timeout=5).status_code,200)
        self.assertEqual(c.get(f'/api/activity/sessions/{sid}',headers=h).json()['items'][-1]['content'],'新的重试回复')

    def test_browsing_deduplicates_orders_retains_snapshot_and_private_deletes(self):
        c=self.client;h=self.headers[0];payload={'product_id':self.products[0],'visit_key':uuid4().hex}
        self.assertEqual(c.post('/api/activity/browsing',json=payload).status_code,401)
        self.assertEqual(c.post('/api/activity/browsing',headers=h,json={**payload,'user_id':self.users[1]}).status_code,422)
        first=c.post('/api/activity/browsing',headers=h,json=payload)
        self.assertEqual(first.status_code,200,first.text);entry_id=first.json()['id']
        self.assertEqual(c.post('/api/activity/browsing',headers=h,json=payload).json()['view_count'],1)
        self.assertEqual(c.post('/api/activity/browsing',headers=h,json={**payload,'visit_key':uuid4().hex}).json()['view_count'],2)
        other=c.post('/api/activity/browsing',headers=h,json={'product_id':self.products[1],'visit_key':uuid4().hex}).json()['id']
        records=c.get('/api/activity/browsing',headers=h).json()
        self.assertEqual(records['total'],2);self.assertEqual(records['items'][0]['id'],other)
        self.assertEqual(c.get('/api/activity/browsing',headers=self.headers[1]).json()['total'],0)
        self.assertEqual(c.delete(f'/api/activity/browsing/{entry_id}',headers=self.headers[1]).status_code,404)
        self.assertEqual(c.delete('/api/activity/browsing',headers=self.headers[1]).status_code,204)
        self.assertEqual(c.get('/api/activity/browsing',headers=h).json()['total'],2)
        with Session(self.db_engine) as db:
            db.execute(update(Product).where(Product.id==self.products[0]).values(status='deleted'));db.commit()
        record=next(r for r in c.get('/api/activity/browsing',headers=h).json()['items'] if r['id']==entry_id)
        self.assertFalse(record['available']);self.assertEqual(record['name'],'商品0')
        self.assertEqual(c.post('/api/activity/browsing',headers=h,json=payload).status_code,404)
        self.assertEqual(c.delete(f'/api/activity/browsing/{entry_id}',headers=h).status_code,204)
        self.assertEqual(c.delete('/api/activity/browsing',headers=h).status_code,204)
        self.assertEqual(c.get('/api/activity/browsing',headers=h).json()['total'],0)


if __name__=='__main__':unittest.main()
