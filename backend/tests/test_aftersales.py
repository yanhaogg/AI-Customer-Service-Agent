import base64
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime,timedelta,timezone
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Barrier,Event
import unittest
from unittest.mock import patch
from uuid import uuid4
from PIL import Image
from sqlalchemy import func,select,update,text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
import test_activity as fixtures
import test_shop as shop_fixtures
from app.api.aftersales import router,admin_router
from app.api.human_support import router as staff_router,user_router
from app.database.aftersales_models import RefundRequest,RefundEvent,ShipmentReminder
from app.database.activity_models import ChatSession,ChatMessage,ChatReadState
from app.database.order_chat_migration import migrate_order_chats
from app.database.shop_models import ShopOrder,SaleOffer


class AftersalesTests(unittest.TestCase):
    def setUp(self):
        fixtures.ActivityTests.setUp(self)
        for route in (router,admin_router,staff_router,user_router):self.client.app.include_router(route)
    def tearDown(self):fixtures.ActivityTests.tearDown(self)
    def order(self,user=0,pay=True,ship=False):
        response=self.client.post('/api/shop/orders',headers=self.headers[user],json=shop_fixtures.ShopTests.checkout_body(self,user=user))
        self.assertEqual(response.status_code,201,response.text);order=response.json()
        if pay:self.client.post(f"/api/shop/orders/{order['id']}/pay",headers=self.headers[user])
        if ship:self.client.post(f"/api/admin/orders/{order['id']}/ship",headers=self.headers[2],json={'carrier':'测试快递','tracking_number':'TEST123'})
        return order
    def body(self,**kwargs):
        return {'request_key':uuid4().hex,'reason':'not_needed','description':'由于个人原因不再需要此商品，申请整单退款。',
                'contact_phone':'13800000000','received':False,**kwargs}
    def stock(self):
        with Session(self.db_engine) as db:return db.get(SaleOffer,self.products[0]).stock

    def test_order_contact_is_immediately_bound_private_and_reused(self):
        c=self.client;h=self.headers[0];order=self.order();oid=order['id']
        path=f'/api/shop/orders/{oid}/contact'
        self.assertEqual(c.post(path,json={}).status_code,401)
        self.assertEqual(c.post(path,headers=self.headers[1],json={}).status_code,404)
        session=c.post(path,headers=h,json={}).json()['session_id']
        self.assertEqual(c.post(path,headers=h,json={}).json()['session_id'],session)
        self.assertEqual(c.get(f'/api/activity/sessions/{session}',headers=h).json()['session']['order_id'],oid)
        with patch('app.api.activity.support_agent.invoke',return_value={'answer':'已查询本订单'}) as invoke:
            response=c.post(f'/api/activity/sessions/{session}/messages',headers=h,json={'content':'这个订单怎么样','request_key':uuid4().hex})
            self.assertEqual(response.status_code,200);self.assertEqual(invoke.call_args.args[0]['order_id'],order['number'])

    def test_reminders_cooldown_and_staff_tracking(self):
        c=self.client;h=self.headers[0];order=self.order(pay=False);oid=order['id'];path=f'/api/shop/orders/{oid}/remind-shipping'
        self.assertEqual(c.post(path,headers=h,json={}).status_code,409)

        c.post(f'/api/shop/orders/{oid}/pay',headers=h)
        first=c.post(path,headers=h,json={});self.assertEqual(first.status_code,200,first.text)
        second=c.post(path,headers=h,json={});self.assertTrue(second.json()['repeated']);self.assertEqual(first.json()['id'],second.json()['id'])
        data=c.get(f"/api/activity/sessions/{first.json()['session_id']}",headers=h).json()['session'];self.assertEqual(data['order_id'],oid)
        mid=first.json()['id']
        self.assertEqual(c.post(f'/api/admin/reminders/{mid}/handle',headers=h,json={'note':'已跟进发货时间'}).status_code,403)
        self.assertEqual(c.post(f'/api/admin/reminders/{mid}/handle',headers=self.headers[2],json={'note':'已联系仓库加快处理'}).status_code,200)
        self.assertEqual(c.get(f'/api/shop/orders/{oid}',headers=h).json()['aftersales']['reminder']['status'],'handled')
        c.post(f'/api/admin/orders/{oid}/ship',headers=self.headers[2],json={'carrier':'测试','tracking_number':'T123'})
        self.assertEqual(c.post(path,headers=h,json={}).status_code,409)

    def test_all_order_consultation_entry_points_reuse_one_session(self):
        c=self.client;h=self.headers[0];order=self.order();oid=order['id']
        sid=c.post(f'/api/shop/orders/{oid}/contact',headers=h,json={}).json()['session_id']
        self.assertEqual(c.post(f'/api/shop/orders/{oid}/remind-shipping',headers=h,json={}).json()['session_id'],sid)
        self.assertEqual(c.post('/api/activity/sessions',headers=h,json={'order_number':order['number'],'title':'另一次订单咨询'}).json()['id'],sid)
        self.assertEqual(c.post(f'/api/shop/orders/{oid}/contact',headers=h,json={'intent':'human'}).json()['session_id'],sid)
        refund=c.post(f'/api/shop/orders/{oid}/refunds',headers=h,json=self.body())
        self.assertEqual(refund.status_code,201,refund.text);self.assertEqual(refund.json()['chat_session_id'],sid)
        with Session(self.db_engine) as db:
            self.assertEqual(db.scalar(select(func.count()).select_from(ChatSession).where(ChatSession.order_id==oid)),1)
        another=self.order()
        self.assertNotEqual(c.post(f"/api/shop/orders/{another['id']}/contact",headers=h,json={}).json()['session_id'],sid)

    def test_concurrent_order_entries_share_a_single_thread(self):
        order=self.order();oid=order['id'];barrier=Barrier(2)
        def enter(generic):
            barrier.wait(5)
            if generic:return self.client.post('/api/activity/sessions',headers=self.headers[0],json={'order_number':order['number']}).json()['id']
            return self.client.post(f'/api/shop/orders/{oid}/remind-shipping',headers=self.headers[0],json={}).json()['session_id']
        with ThreadPoolExecutor(max_workers=2) as pool:
            first=pool.submit(enter,True);second=pool.submit(enter,False)
            self.assertEqual(first.result(10),second.result(10))

    def test_legacy_order_threads_merge_preserves_messages_refunds_and_unread(self):
        order=self.order();oid=order['id'];h=self.headers[0]
        sid=self.client.post(f'/api/shop/orders/{oid}/contact',headers=h,json={}).json()['session_id']
        refund=self.client.post(f'/api/shop/orders/{oid}/refunds',headers=h,json=self.body()).json()
        with self.db_engine.begin() as connection:
            connection.execute(text(f'ALTER TABLE "{self.schema}".chat_sessions DROP CONSTRAINT uq_chat_order'))
        with Session(self.db_engine) as db:
            duplicate=ChatSession(user_id=self.users[0],order_id=oid,intent='refund',title='旧售后会话',human_status='active',staff_user_id=self.users[2])
            db.add(duplicate);db.flush();old_id=duplicate.id
            # Legacy threads may reuse request keys independently.
            for session_id in (sid,old_id):
                db.add_all([ChatMessage(session_id=session_id,request_key='same-request-key',role='user',content=f'问题{session_id}'),
                            ChatMessage(session_id=session_id,request_key='same-request-key',role='assistant',content=f'回答{session_id}')])
            db.add(ChatReadState(session_id=sid,user_id=self.users[0],last_read_at=datetime.now(timezone.utc)))
            db.execute(update(RefundRequest).where(RefundRequest.id==refund['id']).values(chat_session_id=old_id))
            db.commit()
            ids=list(db.scalars(select(ChatMessage.id).order_by(ChatMessage.id)))
        with self.db_engine.begin() as connection:
            self.assertEqual(migrate_order_chats(connection),{'merged_sessions':1,'preserved_messages':2})
        with self.db_engine.begin() as connection:
            self.assertEqual(migrate_order_chats(connection),{'merged_sessions':0,'preserved_messages':0})
        with Session(self.db_engine) as db:
            entries=db.scalars(select(ChatMessage).order_by(ChatMessage.id)).all()
            self.assertEqual([m.id for m in entries],ids);self.assertEqual({m.session_id for m in entries},{sid})
            self.assertEqual(len({(m.request_key,m.role) for m in entries}),4)
            self.assertEqual(db.get(RefundRequest,refund['id']).chat_session_id,sid)
            self.assertEqual(db.get(ChatSession,sid).human_status,'active');self.assertIsNone(db.get(ChatSession,old_id))
            with self.assertRaises(IntegrityError):
                db.add(ChatSession(user_id=self.users[0],order_id=oid,title='不能重复'));db.flush()
            db.rollback()
        self.assertEqual(self.client.get('/api/activity/unread',headers=h).json()['total'],2)

    def test_auto_refund_is_full_idempotent_and_restores_inventory_once(self):
        c=self.client;h=self.headers[0];order=self.order();oid=order['id'];body=self.body();path=f'/api/shop/orders/{oid}/refunds'
        self.assertEqual(self.stock(),4)
        self.assertEqual(c.post(path,headers=h,json={**body,'amount':'99999'}).status_code,422)
        self.assertEqual(c.post(path,headers=self.headers[1],json=body).status_code,404)
        first=c.post(path,headers=h,json=body);self.assertEqual(first.status_code,201,first.text)
        self.assertEqual(first.json()['status'],'refunded');self.assertEqual(first.json()['amount'],'12.50');self.assertEqual(self.stock(),5)
        self.assertEqual(c.post(path,headers=h,json=body).json()['id'],first.json()['id']);self.assertEqual(self.stock(),5)
        self.assertEqual(c.post(path,headers=h,json=self.body()).status_code,409)
        current=c.get(f'/api/shop/orders/{oid}',headers=h).json();self.assertEqual(current['status'],'refunded')
        self.assertEqual(c.post(f'/api/admin/orders/{oid}/ship',headers=self.headers[2],json={'carrier':'测试','tracking_number':'T123'}).status_code,409)
        self.assertEqual(c.get('/api/shop/orders?status=refunded',headers=h).json()['total'],1)

    def test_manual_paid_refund_blocks_shipping_and_can_reject_then_review(self):
        c=self.client;h=self.headers[0];ah=self.headers[2];oid=self.order()['id']
        with Session(self.db_engine) as db:
            db.execute(update(ShopOrder).where(ShopOrder.id==oid).values(paid_at=datetime.now(timezone.utc)-timedelta(hours=25)));db.commit()
        response=c.post(f'/api/shop/orders/{oid}/refunds',headers=h,json=self.body());self.assertEqual(response.status_code,201,response.text)
        request=response.json();rid=request['id'];self.assertEqual(request['status'],'review_pending');self.assertEqual(self.stock(),4)
        self.assertEqual(c.post(f'/api/admin/orders/{oid}/ship',headers=ah,json={'carrier':'测试','tracking_number':'T123'}).status_code,409)
        self.assertEqual(c.post(f'/api/shop/orders/{oid}/refunds',headers=h,json=self.body()).status_code,409)
        self.assertEqual(c.post(f'/api/admin/refunds/{rid}/review',headers=h,json={'action':'approve','note':'同意处理申请'}).status_code,403)
        self.assertEqual(c.post(f'/api/admin/refunds/{rid}/review',headers=ah,json={'action':'reject','note':'需要补充情况说明'}).json()['status'],'rejected')
        second=c.post(f'/api/shop/orders/{oid}/refunds',headers=h,json=self.body()).json();rid=second['id']
        approved=c.post(f'/api/admin/refunds/{rid}/review',headers=ah,json={'action':'approve','note':'核实未发货，同意退款'})
        self.assertEqual(approved.json()['status'],'refunded');self.assertEqual(self.stock(),5)
        self.assertEqual(c.post(f'/api/admin/refunds/{rid}/review',headers=ah,json={'action':'approve','note':'重复请求不会重复退款'}).status_code,200);self.assertEqual(self.stock(),5)

    def test_shipped_quality_evidence_private_and_return_inspection_flow(self):
        c=self.client;h=self.headers[0];ah=self.headers[2];order=self.order(ship=True);oid=order['id']
        body=self.body(reason='quality',received=True)
        self.assertEqual(c.post(f'/api/shop/orders/{oid}/refunds',headers=h,json=body).status_code,422)
        with TemporaryDirectory() as directory,patch('app.api.aftersales.MATERIALS_ROOT',Path(directory).resolve()):
            stream=BytesIO();Image.new('RGB',(20,20),'blue').save(stream,format='PNG')
            image=c.post(f'/api/shop/orders/{oid}/refund-evidence',headers=h,json={'data':base64.b64encode(stream.getvalue()).decode()})
            self.assertEqual(image.status_code,201,image.text);image=image.json()
            self.assertEqual(c.get(image['url'],headers=self.headers[1]).status_code,404)
            self.assertEqual(c.get(image['url'],headers=ah).status_code,404)
            body['evidence_ids']=[image['id']]
            response=c.post(f'/api/shop/orders/{oid}/refunds',headers=h,json=body)
            self.assertEqual(response.status_code,201,response.text);refund=response.json();rid=refund['id']
            self.assertEqual(refund['status'],'review_pending');self.assertEqual(refund['human_status'],'waiting')
            self.assertEqual(c.get(image['url'],headers=ah).status_code,200)
            self.assertEqual(c.get(image['url']).status_code,401)
            self.assertEqual(c.get(image['url'],headers=self.headers[1]).status_code,404)
            self.assertEqual(c.post(f'/api/shop/orders/{oid}/complete',headers=h).status_code,409)
            self.assertEqual(c.post(f'/api/admin/refunds/{rid}/review',headers=ah,json={'action':'approve','note':'审核同意退货退款'}).status_code,422)
            approved=c.post(f'/api/admin/refunds/{rid}/review',headers=ah,json={'action':'approve','note':'审核同意退货退款','return_address':'测试省测试市售后仓库一号，收件人测试客服，电话13800000000'})
            self.assertEqual(approved.json()['status'],'awaiting_return')
            self.assertEqual(c.post(f'/api/admin/refunds/{rid}/review',headers=ah,json={'action':'confirm_return','note':'不能跳过寄回阶段'}).status_code,409)
            self.assertEqual(c.post(f'/api/shop/refunds/{rid}/return-shipping',headers=self.headers[1],json={'carrier':'快递','tracking_number':'RETURN123'}).status_code,404)
            self.assertEqual(c.post(f'/api/shop/refunds/{rid}/return-shipping',headers=h,json={'carrier':'快递','tracking_number':'RETURN123'}).json()['status'],'return_in_transit')
            done=c.post(f'/api/admin/refunds/{rid}/review',headers=ah,json={'action':'confirm_return','note':'退货已经收到并验收，同意退款'})
            self.assertEqual(done.json()['status'],'refunded');self.assertEqual(self.stock(),4) # Shipped/returned goods are not automatically resaleable.
            self.assertGreaterEqual(len(done.json()['events']),4)

    def test_human_handoff_consent_staff_reply_and_resume_ai(self):
        c=self.client;h=self.headers[0];ah=self.headers[2];oid=self.order()['id']
        sid=c.post(f'/api/shop/orders/{oid}/contact',headers=h,json={}).json()['session_id']
        self.assertEqual(c.get(f'/api/admin/support-sessions/{sid}',headers=ah).status_code,200)
        self.assertEqual(c.post(f'/api/activity/sessions/{sid}/handoff',headers=self.headers[1]).status_code,404)
        self.assertEqual(c.post(f'/api/activity/sessions/{sid}/handoff',headers=h).status_code,200)
        self.assertEqual(c.get('/api/admin/support-sessions',headers=h).status_code,403)
        self.assertEqual(c.get('/api/admin/support-sessions',headers=ah).json()['total'],1)
        with patch('app.api.activity.support_agent.invoke') as agent:
            message=c.post(f'/api/activity/sessions/{sid}/messages',headers=h,json={'content':'请人工帮我处理这个订单','request_key':uuid4().hex})
            self.assertEqual(message.status_code,200);agent.assert_not_called()
        reply={'content':'您好，我是人工客服，正在核实此订单。','request_key':uuid4().hex}
        self.assertEqual(c.post(f'/api/admin/support-sessions/{sid}/messages',headers=h,json=reply).status_code,403)
        self.assertEqual(c.post(f'/api/admin/support-sessions/{sid}/messages',headers=ah,json=reply).status_code,200)
        self.assertEqual(c.post(f'/api/admin/support-sessions/{sid}/messages',headers=ah,json=reply).status_code,200)
        detail=c.get(f'/api/activity/sessions/{sid}',headers=h).json();self.assertEqual(len(detail['items']),3);self.assertEqual(detail['items'][-1]['role'],'human_agent')
        self.assertEqual(detail['session']['human_status'],'active')
        staff_items=c.get(f'/api/admin/support-sessions/{sid}',headers=ah).json()['items']
        self.assertEqual([item['is_mine'] for item in staff_items],[False,False,True])
        from app.database.models import User
        with Session(self.db_engine) as db:
            other_staff=db.get(User,self.users[1]);other_staff.role='super_admin';db.commit()
        other_items=c.get(f'/api/admin/support-sessions/{sid}',headers=self.headers[1]).json()['items']
        self.assertTrue(all(not item['is_mine'] for item in other_items))
        c.post(f'/api/admin/support-sessions/{sid}/close',headers=ah)
        with patch('app.api.activity.support_agent.invoke',return_value={'answer':'人工服务结束，现在由AI继续帮助你。'}) as agent:
            self.assertEqual(c.post(f'/api/activity/sessions/{sid}/messages',headers=h,json={'content':'继续查询','request_key':uuid4().hex}).status_code,200);agent.assert_called_once()

    def test_concurrent_refund_ship_has_one_consistent_outcome(self):
        c=self.client;h=self.headers[0];ah=self.headers[2];oid=self.order()['id'];barrier=Barrier(2)
        def refund():
            barrier.wait(5);return c.post(f'/api/shop/orders/{oid}/refunds',headers=h,json=self.body())
        def ship():
            barrier.wait(5);return c.post(f'/api/admin/orders/{oid}/ship',headers=ah,json={'carrier':'测试快递','tracking_number':'SHIP123'})
        with ThreadPoolExecutor(max_workers=2) as executor:
            f1=executor.submit(refund);f2=executor.submit(ship);r1=f1.result(10);r2=f2.result(10)
        self.assertEqual(r1.status_code,201,r1.text)
        if r1.json()['status']=='refunded':self.assertEqual(r2.status_code,409);self.assertEqual(self.stock(),5)
        else:self.assertEqual(r1.json()['status'],'review_pending');self.assertEqual(r2.status_code,200);self.assertEqual(self.stock(),4)

    def test_handoff_while_ai_runs_suppresses_late_ai_reply(self):
        c=self.client;h=self.headers[0];oid=self.order()['id']
        sid=c.post(f'/api/shop/orders/{oid}/contact',headers=h,json={}).json()['session_id']
        started=Event();finish=Event()
        def slow(_):
            started.set();finish.wait(5);return {'answer':'过期的AI答复不得发送'}
        with ThreadPoolExecutor(max_workers=1) as executor,patch('app.api.activity.support_agent.invoke',side_effect=slow):
            result=executor.submit(c.post,f'/api/activity/sessions/{sid}/messages',headers=h,json={'content':'我要咨询这个订单','request_key':uuid4().hex})
            self.assertTrue(started.wait(3))
            self.assertEqual(c.post(f'/api/activity/sessions/{sid}/handoff',headers=h).status_code,200)
            self.assertEqual(c.post(f'/api/admin/support-sessions/{sid}/messages',headers=self.headers[2],json={'content':'人工客服已接待','request_key':uuid4().hex}).status_code,200)
            finish.set();self.assertEqual(result.result(5).status_code,200)
        detail=c.get(f'/api/activity/sessions/{sid}',headers=h).json()
        self.assertNotIn('过期的AI答复',str(detail));self.assertEqual(detail['items'][-1]['role'],'human_agent')

    def test_withdraw_and_delete_chat_preserve_refund_audit(self):
        c=self.client;h=self.headers[0];oid=self.order()['id']
        request=c.post(f'/api/shop/orders/{oid}/refunds',headers=h,json=self.body(reason='payment_issue')).json()
        self.assertEqual(request['status'],'review_pending')
        sid=request['chat_session_id'];rid=request['id']
        self.assertEqual(c.delete(f'/api/activity/sessions/{sid}',headers=h).status_code,204)
        history=c.get(f'/api/shop/orders/{oid}/refunds',headers=h).json()['items']
        self.assertIsNone(history[0]['chat_session_id'])
        self.assertEqual(c.post(f'/api/shop/refunds/{rid}/withdraw',headers=self.headers[1]).status_code,404)
        self.assertEqual(c.post(f'/api/shop/refunds/{rid}/withdraw',headers=h).json()['status'],'withdrawn')
        self.assertEqual(self.stock(),4)
        self.assertEqual(c.post(f'/api/admin/orders/{oid}/ship',headers=self.headers[2],json={'carrier':'测试','tracking_number':'T123'}).status_code,200)


if __name__=='__main__':unittest.main()
