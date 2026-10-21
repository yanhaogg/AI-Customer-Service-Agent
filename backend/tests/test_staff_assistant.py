"""Copilot access, scoped facts, bounded snapshots and draft-only behavior."""
import json
import unittest
from unittest.mock import patch
from uuid import uuid4
from langchain_core.messages import AIMessage
from sqlalchemy import func,select
from sqlalchemy.orm import Session
import test_aftersales as fixtures
from app.agent.staff_assistant import StaffAssistant
from app.agent.config import ModelSettings,AgentConfigurationError
from app.database.activity_models import ChatMessage,ChatReadState,ChatSession
from app.database.shop_models import ShopOrder


class AdviceModel:
    def __init__(self,content=None):
        self.inputs=[];self.options={}
        self.content=content or json.dumps({'summary':'用户正在咨询订单，尚未解决。','customer_needs':['确认发货时间'],
            'suggested_reply':'您好，我会先核实订单状态，再向您说明后续安排。'},ensure_ascii=False)
    def bind(self,**options):self.options=options;return self
    def invoke(self,messages):self.inputs.append(messages);return AIMessage(content=self.content)


class StaffAssistantTests(unittest.TestCase):
    order=fixtures.AftersalesTests.order
    def setUp(self):
        fixtures.AftersalesTests.setUp(self)
        self.current_order=self.order(pay=False)
        self.sid=self.client.post(f"/api/shop/orders/{self.current_order['id']}/contact",headers=self.headers[0],json={}).json()['session_id']
        with Session(self.db_engine) as db:
            db.add(ChatMessage(session_id=self.sid,role='user',content='这个订单什么时候发货？',request_key=uuid4().hex));db.commit()
        self.path=f'/api/admin/support-sessions/{self.sid}/assistant'
    def tearDown(self):fixtures.AftersalesTests.tearDown(self)
    def assistant(self,model):
        return StaffAssistant(settings_loader=lambda:ModelSettings(api_key='test-secret'),model_factory=lambda settings,timeout:model)

    def test_only_admin_can_generate_and_it_never_sends_or_changes_reception(self):
        self.assertEqual(self.client.post(self.path).status_code,401)
        self.assertEqual(self.client.post(self.path,headers=self.headers[0]).status_code,403)
        self.assertEqual(self.client.post(self.path,headers=self.headers[1]).status_code,403)
        model=AdviceModel()
        with patch('app.api.human_support.staff_assistant',self.assistant(model)):
            result=self.client.post(self.path,headers=self.headers[2])
        self.assertEqual(result.status_code,200,result.text);advice=result.json()
        detail=self.client.get(f'/api/admin/support-sessions/{self.sid}',headers=self.headers[2]).json()
        self.assertEqual(advice['snapshot_version'],detail['assist_version'])
        self.assertEqual(advice['included_messages'],1);self.assertFalse(advice['has_older_messages'])
        self.assertEqual(model.options,{'response_format':{'type':'json_object'}})
        context=json.loads(model.inputs[0][-1].content)
        self.assertEqual(context['verified_facts']['get_my_order_details']['order_id'],self.current_order['id'])
        self.assertIn('get_refund_policy',context['verified_facts'])
        with Session(self.db_engine) as db:
            self.assertEqual(db.scalar(select(func.count()).select_from(ChatMessage)),1)
            self.assertEqual(db.scalar(select(func.count()).select_from(ChatReadState)),0)
            self.assertEqual(db.get(ChatSession,self.sid).human_status,'none')
            self.assertEqual(db.get(ShopOrder,self.current_order['id']).status,'pending_payment')
        edited=advice['suggested_reply']+' 请先确认是否已支付。'
        response=self.client.post(f'/api/admin/support-sessions/{self.sid}/messages',headers=self.headers[2],json={'content':edited,'request_key':uuid4().hex})
        self.assertEqual(response.status_code,200);self.assertEqual(response.json()['content'],edited)

    def test_snapshot_marks_new_messages_and_bounds_model_context(self):
        with Session(self.db_engine) as db:
            db.add_all([ChatMessage(session_id=self.sid,role='user',content='长对话内容'*800,request_key=uuid4().hex) for _ in range(55)]);db.commit()
        model=AdviceModel()
        with patch('app.api.human_support.staff_assistant',self.assistant(model)):
            advice=self.client.post(self.path,headers=self.headers[2]).json()
        self.assertTrue(advice['has_older_messages']);self.assertLessEqual(advice['included_messages'],50)
        context=json.loads(model.inputs[0][-1].content)
        self.assertLessEqual(sum(len(m['content']) for m in context['messages']),24000)
        with Session(self.db_engine) as db:
            db.add(ChatMessage(session_id=self.sid,role='user',content='还有一个新问题',request_key=uuid4().hex));db.commit()
        detail=self.client.get(f'/api/admin/support-sessions/{self.sid}',headers=self.headers[2]).json()
        self.assertNotEqual(detail['assist_version'],advice['snapshot_version'])

    def test_invalid_model_response_and_missing_config_are_safe(self):
        with patch('app.api.human_support.staff_assistant',self.assistant(AdviceModel('SECRET_INVALID_JSON'))):
            response=self.client.post(self.path,headers=self.headers[2])
        self.assertEqual(response.status_code,503);self.assertNotIn('SECRET',response.text)
        broken=StaffAssistant(settings_loader=lambda:(_ for _ in ()).throw(AgentConfigurationError('SECRET_CONFIG')))
        with patch('app.api.human_support.staff_assistant',broken):
            response=self.client.post(self.path,headers=self.headers[2])
        self.assertEqual(response.status_code,503);self.assertNotIn('SECRET',response.text)
        with Session(self.db_engine) as db:self.assertEqual(db.scalar(select(func.count()).select_from(ChatMessage)),1)

    def test_unknown_session_and_extra_identity_are_rejected(self):
        self.assertEqual(self.client.post('/api/admin/support-sessions/999999/assistant',headers=self.headers[2]).status_code,404)
        model=AdviceModel()
        # Client-supplied identities are rejected before invoking the assistant.
        with patch('app.api.human_support.staff_assistant',self.assistant(model)):
            result=self.client.post(self.path,headers=self.headers[2],json={'user_id':self.users[1]})
        self.assertEqual(result.status_code,422);self.assertEqual(model.inputs,[])
