"""Opt-in, billable DeepSeek end-to-end check with synthetic data in a disposable schema."""
import os
import unittest
from uuid import uuid4
from sqlalchemy.orm import Session
import test_activity as fixtures
import test_shop as shop_fixtures
from app.database.activity_models import ChatMessage


@unittest.skipUnless(os.getenv('AGENT_LIVE_TEST')=='1','Set AGENT_LIVE_TEST=1 for billable DeepSeek integration')
class LiveAgentTests(unittest.TestCase):
    def setUp(self):fixtures.ActivityTests.setUp(self)
    def tearDown(self):fixtures.ActivityTests.tearDown(self)

    def test_real_manager_coordinates_product_order_and_aftersales(self):
        c=self.client;h=self.headers[0]
        order=c.post('/api/shop/orders',headers=h,json=shop_fixtures.ShopTests.checkout_body(self)).json()
        c.post('/api/activity/browsing',headers=h,json={'product_id':self.products[0],'visit_key':uuid4().hex})
        sid=fixtures.ActivityTests.new_session(self,order_number=order['number'])
        response=c.post(f'/api/activity/sessions/{sid}/messages',headers=h,json={'content':
            '请协作完成三个问题：查询我最近浏览的商品并核实商品详情；查询当前订单状态和明细；再按现行售后政策说明这笔订单是否需要退款，以及取消或售后需要如何操作。请分别通过商品、订单、售后专员核实后统一回答。',
            'request_key':uuid4().hex})
        self.assertEqual(response.status_code,200)
        answer=response.json()['items'][-1]
        self.assertEqual(answer['status'],'completed',answer['content'])
        meta=answer['agent_metadata'];self.assertEqual(meta['mode'],'manager_multi_agent')
        roles={entry['agent'] for entry in meta['agents'] if entry['status']=='completed'}
        self.assertEqual(roles,{'product_agent','order_agent','aftersales_agent'},str(meta))
        names={t['name'] for t in meta['tools'] if t['status']=='ok'}
        self.assertTrue({'get_my_browsing_history','get_product_details','get_my_order_details','get_refund_policy'}<=names,str(meta))
        self.assertLessEqual(meta['steps'],16);self.assertFalse(meta['limited'])

    def test_real_model_orders_browsing_and_conversation_memory(self):
        c=self.client;h=self.headers[0]
        order=c.post('/api/shop/orders',headers=h,json=shop_fixtures.ShopTests.checkout_body(self)).json()
        c.post('/api/activity/browsing',headers=h,json={'product_id':self.products[1],'visit_key':uuid4().hex})
        sid=fixtures.ActivityTests.new_session(self,product_id=self.products[1],order_number=order['number'])
        with Session(self.db_engine) as db:
            key=uuid4().hex
            db.add_all([ChatMessage(session_id=sid,request_key=key,role='user',content='我选购耳机时最看重续航。',status='completed'),
                        ChatMessage(session_id=sid,request_key=key,role='assistant',content='好的，会结合你的续航偏好继续咨询。',status='completed')])
            db.commit()
        first=c.post(f'/api/activity/sessions/{sid}/messages',headers=h,json={
            'content':'请先调用浏览记录工具及订单查询工具，查我最近看过的商品和当前订单，再结合前面提到的选购偏好，说明我下一步该怎么做。',
            'request_key':uuid4().hex})
        self.assertEqual(first.status_code,200)
        answer=first.json()['items'][-1];self.assertEqual(answer['status'],'completed',answer['content'])
        names={t['name'] for t in answer['agent_metadata']['tools'] if t['status']=='ok'}
        self.assertIn('get_my_browsing_history',names)
        self.assertTrue(names & {'list_my_orders','get_my_order_details'})
        self.assertIn('续航',answer['content'])
        second=c.post(f'/api/activity/sessions/{sid}/messages',headers=h,json={
            'content':'不需要再次查数据库，我之前说选购耳机最看重什么？','request_key':uuid4().hex})
        second_answer=second.json()['items'][-1]
        self.assertEqual(second_answer['status'],'completed',second_answer['content']);self.assertIn('续航',second_answer['content'])
        third=c.post(f'/api/activity/sessions/{sid}/messages',headers=h,json={
            'content':'请使用历史聊天搜索工具，搜索“续航”，找到我之前的偏好后概括回答。','request_key':uuid4().hex})
        third_answer=third.json()['items'][-1]
        self.assertEqual(third_answer['status'],'completed',third_answer['content'])
        self.assertIn('search_my_chat_history',{t['name'] for t in third_answer['agent_metadata']['tools'] if t['status']=='ok'})
        self.assertEqual(len(c.get(f'/api/activity/sessions/{sid}',headers=h).json()['items']),8)


if __name__=='__main__':unittest.main()
