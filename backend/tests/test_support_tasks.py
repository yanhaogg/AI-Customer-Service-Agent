"""Manual analysis and explicit creation; no scanners or automatic task mutations."""
import json
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime,timedelta,timezone
from threading import Barrier
from unittest.mock import patch
from uuid import uuid4
import unittest
from langchain_core.messages import AIMessage
from sqlalchemy import func,select
from sqlalchemy.orm import Session
import test_aftersales as fixtures
from app.api.support_tasks import router
from app.database.models import User
from app.database.shop_models import ShopOrder
from app.database.activity_models import ChatMessage,ChatSession
from app.database.aftersales_models import RefundRequest
from app.database.support_task_models import SupportTask,SupportTaskEvent,SupportTaskPreview
from app.agent.order_followup import OrderFollowupAgent
from app.agent.config import ModelSettings


class SupportTasksTests(unittest.TestCase):
    order=fixtures.AftersalesTests.order
    body=fixtures.AftersalesTests.body
    def setUp(self):
        fixtures.AftersalesTests.setUp(self)
        self.client.app.include_router(router)
        self.admin=self.headers[2]
    def tearDown(self):fixtures.AftersalesTests.tearDown(self)
    def overdue_order(self,shipped=False):
        order=self.order(ship=shipped)
        with Session(self.db_engine) as db:
            row=db.get(ShopOrder,order['id']);row.paid_at=datetime.now(timezone.utc)-timedelta(hours=49)
            if shipped:row.shipped_at=datetime.now(timezone.utc)-timedelta(days=8)
            db.commit()
        return order
    def preview(self,order):
        advice={'analysis':'订单情况需要人工核实。','next_steps':['核对发货或售后安排。'],'suggested_reply':'您好，会先核实您的订单情况。'}
        with patch('app.services.support_tasks.order_followup_agent.invoke',return_value=advice):
            response=self.client.post('/api/admin/support-tasks/preview',headers=self.admin,json={'order_id':order['id']})
        self.assertEqual(response.status_code,200,response.text);return response.json()
    def create(self,preview,headers=None):
        return self.client.post('/api/admin/support-tasks',headers=headers or self.admin,json={'preview_id':preview['candidates'][0]['preview_id']})
    def task(self,order):
        result=self.create(self.preview(order));self.assertEqual(result.status_code,201,result.text);return result.json()
    def listing(self,query=''):
        return self.client.get('/api/admin/support-tasks'+query,headers=self.admin).json()
    def act(self,task,action,note='',headers=None):
        return self.client.post(f'/api/admin/support-tasks/{task}/actions',headers=headers or self.admin,json={'action':action,'note':note})

    def test_preview_does_not_create_task_or_change_order(self):
        order=self.overdue_order();result=self.preview(order)
        self.assertEqual(len(result['candidates']),1)
        self.assertEqual(self.listing()['total'],0)
        with Session(self.db_engine) as db:
            self.assertEqual(db.get(ShopOrder,order['id']).status,'paid')
            self.assertEqual(db.scalar(select(func.count()).select_from(ChatMessage)),0)
        created=self.create(result)
        self.assertEqual(created.status_code,201);self.assertTrue(created.json()['created'])
        self.assertEqual(created.json()['events'][0]['action'],'created')
        again=self.create(result)
        self.assertEqual(again.json()['id'],created.json()['id']);self.assertFalse(again.json()['created'])

    def test_three_kinds_are_checked_only_for_the_selected_order(self):
        paid=self.overdue_order();shipped=self.overdue_order(True);refund_order=self.overdue_order()
        refund=self.client.post(f"/api/shop/orders/{refund_order['id']}/refunds",headers=self.headers[0],json=self.body()).json()
        with Session(self.db_engine) as db:db.get(RefundRequest,refund['id']).created_at=datetime.now(timezone.utc)-timedelta(hours=25);db.commit()
        self.assertEqual(self.task(paid)['kind'],'shipping_overdue')
        self.assertEqual(self.task(shipped)['kind'],'receipt_overdue')
        self.assertEqual(self.task(refund_order)['kind'],'refund_overdue')
        self.assertEqual(self.listing()['total'],3)
        self.assertNotIn('13800000000',json.dumps(self.listing()));self.assertNotIn('101 室',json.dumps(self.listing()))

    def test_normal_order_has_no_candidate_and_no_task(self):
        self.assertEqual(self.preview(self.order())['candidates'],[])
        self.assertEqual(self.listing()['total'],0)

    def test_confirm_rechecks_facts_expiry_and_preview_owner(self):
        order=self.overdue_order();preview=self.preview(order)
        with Session(self.db_engine) as db:db.get(User,self.users[1]).role='super_admin';db.commit()
        self.assertEqual(self.create(preview,self.headers[1]).status_code,404)
        with Session(self.db_engine) as db:db.get(SupportTaskPreview,preview['candidates'][0]['preview_id']).expires_at=datetime.now(timezone.utc)-timedelta(seconds=1);db.commit()
        self.assertEqual(self.create(preview).status_code,409)
        preview=self.preview(order)
        self.client.post(f"/api/admin/orders/{order['id']}/ship",headers=self.admin,json={'carrier':'测试快递','tracking_number':'MANUAL123'})
        self.assertEqual(self.create(preview).status_code,409);self.assertEqual(self.listing()['total'],0)

    def test_concurrent_confirmation_has_one_task(self):
        preview=self.preview(self.overdue_order());barrier=Barrier(2)
        def create():barrier.wait(5);return self.create(preview)
        with ThreadPoolExecutor(max_workers=2) as pool:
            a=pool.submit(create);b=pool.submit(create);results=[a.result(10),b.result(10)]
        self.assertEqual({r.status_code for r in results},{201})
        self.assertEqual(len({r.json()['id'] for r in results}),1)
        self.assertEqual(sum(r.json()['created'] for r in results),1)

    def test_reading_does_not_create_close_or_analyze_tasks(self):
        order=self.overdue_order();task=self.task(order)
        with Session(self.db_engine) as db:before=db.scalar(select(func.count()).select_from(SupportTaskEvent))
        self.client.post(f"/api/admin/orders/{order['id']}/ship",headers=self.admin,json={'carrier':'测试快递','tracking_number':'MANUAL234'})
        with patch('app.services.support_tasks.order_followup_agent.invoke') as model:
            for _ in range(2):
                data=self.client.get(f"/api/admin/support-tasks/{task['id']}",headers=self.admin).json()
                self.assertEqual(data['status'],'pending');self.assertTrue(data['facts_changed']);self.assertEqual(data['advice'],{})
                self.listing();self.client.get('/api/admin/support-tasks/summary',headers=self.admin)
            model.assert_not_called()
        with Session(self.db_engine) as db:
            self.assertEqual(db.scalar(select(func.count()).select_from(SupportTaskEvent)),before)
            self.assertEqual(db.scalar(select(func.count()).select_from(SupportTask)),1)
        self.assertEqual(self.act(task['id'],'resolve','已核实发货，手动完成跟进。').json()['status'],'resolved')

    def test_claim_notes_release_and_concurrent_ownership(self):
        task=self.task(self.overdue_order())['id']
        self.assertEqual(self.act(task,'claim').json()['status'],'in_progress')
        self.assertEqual(self.act(task,'release').json()['status'],'pending')
        with Session(self.db_engine) as db:db.get(User,self.users[1]).role='super_admin';db.commit()
        barrier=Barrier(2)
        def claim(headers):barrier.wait(5);return self.act(task,'claim',headers=headers)
        with ThreadPoolExecutor(max_workers=2) as pool:
            a=pool.submit(claim,self.admin);b=pool.submit(claim,self.headers[1]);results=[a.result(10),b.result(10)]
        self.assertEqual(sorted(r.status_code for r in results),[200,409])
        winner=next(r.json()['assignee_id'] for r in results if r.status_code==200)
        owner=self.admin if winner==self.users[2] else self.headers[1]
        self.assertEqual(self.act(task,'resolve',headers=owner).status_code,422)
        self.assertEqual(self.act(task,'note','已核实当前情况。',headers=owner).status_code,200)
        self.assertEqual(self.act(task,'resolve','客服已完成本次人工跟进。',headers=owner).json()['status'],'resolved')

    def test_permissions_and_scan_endpoint_removal(self):
        for path in ['/api/admin/support-tasks','/api/admin/support-tasks/summary']:
            self.assertEqual(self.client.get(path,headers=self.headers[0]).status_code,403)
            self.assertEqual(self.client.get(path).status_code,401)
        self.assertEqual(self.client.post('/api/admin/support-tasks/preview',headers=self.headers[0],json={'order_id':1}).status_code,403)
        self.assertNotIn('/api/admin/support-tasks/scan',self.client.get('/openapi.json').json()['paths'])
        self.assertEqual(self.client.get('/api/admin/support-tasks/summary',headers=self.admin).json()['mode'],'manual')

    def test_manual_reanalysis_rejects_changed_order_without_closing_task(self):
        order=self.overdue_order();task=self.task(order)['id']
        def changed(snapshot):
            with Session(self.db_engine) as db:
                row=db.get(ShopOrder,order['id']);row.status='shipped';row.shipped_at=datetime.now(timezone.utc);db.commit()
            return {'analysis':'原订单待发货。','next_steps':['核实安排。'],'suggested_reply':'您好，我们会核实。'}
        with patch('app.services.support_tasks.order_followup_agent.invoke',side_effect=changed):
            response=self.client.post(f'/api/admin/support-tasks/{task}/analyze',headers=self.admin)
        self.assertEqual(response.status_code,409)
        self.assertEqual(self.client.get(f'/api/admin/support-tasks/{task}',headers=self.admin).json()['status'],'pending')

    def test_preview_model_errors_are_safe_and_no_task_is_created(self):
        order=self.overdue_order()
        with patch('app.services.support_tasks.order_followup_agent.invoke',side_effect=RuntimeError('SECRET_PROVIDER_KEY')):
            result=self.client.post('/api/admin/support-tasks/preview',headers=self.admin,json={'order_id':order['id']})
        self.assertEqual(result.status_code,503);self.assertNotIn('SECRET',result.text);self.assertEqual(self.listing()['total'],0)
