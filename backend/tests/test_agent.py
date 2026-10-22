"""Deterministic graph/tool integration tests. No paid model calls or real customer writes."""
import json
import unittest
from unittest.mock import patch
from uuid import uuid4
from langchain_core.messages import AIMessage,ToolMessage
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session
import test_activity as activity_fixtures
import test_shop as shop_fixtures
from app.agent.catalog_tools import build_tools
from app.agent.config import ModelSettings,AgentConfigurationError,load_settings
from app.agent.graph import SupportAgent,conversation_messages
from app.database.activity_models import ChatMessage
from app.database.shop_models import SaleOffer


def call(name,args,identifier='call_1'):
    return {'name':name,'args':args,'id':identifier,'type':'tool_call'}


class ScriptedModel:
    def __init__(self,answers):self.answers=iter(answers);self.inputs=[];self.tools=[];self.bindings=[]
    def bind_tools(self,tools):self.tools=tools;self.bindings.append({t.name for t in tools});return self
    def invoke(self,messages):
        self.inputs.append(list(messages))
        answer=next(self.answers)
        return answer(messages) if callable(answer) else answer


class AgentTests(unittest.TestCase):
    def setUp(self):activity_fixtures.ActivityTests.setUp(self)
    def tearDown(self):activity_fixtures.ActivityTests.tearDown(self)

    def agent(self,model,**settings):
        return SupportAgent(settings_loader=lambda:ModelSettings(api_key='test-secret',model='test-model',**settings),
                            model_factory=lambda config,timeout:model)

    def tools(self,**kwargs):
        return {t.name:t for t in build_tools(self.users[0],lambda:Session(self.db_engine),**kwargs)}

    def test_tools_bind_identity_and_exclude_other_users(self):
        c=self.client;h=self.headers[0];p=self.products
        own=c.post('/api/shop/orders',headers=h,json=shop_fixtures.ShopTests.checkout_body(self)).json()
        other=c.post('/api/shop/orders',headers=self.headers[1],json=shop_fixtures.ShopTests.checkout_body(self,user=1)).json()
        for index in (0,1):
            c.post('/api/activity/browsing',headers=self.headers[index],json={'product_id':p[index],'visit_key':uuid4().hex})
            sid=activity_fixtures.ActivityTests.new_session(self,user=index)
            with Session(self.db_engine) as db:
                db.add(ChatMessage(session_id=sid,role='user',content=f'私密偏好 USER_{index}',status='completed',request_key=uuid4().hex));db.commit()
        tools=self.tools(current_message_id=999999)
        self.assertEqual(len(tools),8)
        for tool in tools.values():
            self.assertNotIn('user_id',tool.args_schema.model_json_schema().get('properties',{}))
        self.assertEqual([o['order_id'] for o in tools['list_my_orders'].invoke({})['items']],[own['id']])
        self.assertIn('error',tools['get_my_order_details'].invoke({'order_id':other['id']}))
        self.assertIn('error',tools['get_my_order_details'].invoke({'order_number':other['number']}))
        self.assertEqual(tools['get_my_order_details'].invoke({'order_id':own['id']})['number'],own['number'])
        order_json=json.dumps(tools['get_my_order_details'].invoke({'order_id':own['id']}),ensure_ascii=False)
        self.assertNotIn('13800000000',order_json);self.assertNotIn('101 室',order_json)
        self.assertEqual([i['product_id'] for i in tools['get_my_browsing_history'].invoke({})['items']],[p[0]])
        history=tools['search_my_chat_history'].invoke({'query':'私密'})
        self.assertIn('USER_0',json.dumps(history));self.assertNotIn('USER_1',json.dumps(history))
        with self.assertRaises(ValidationError):tools['list_my_orders'].invoke({'user_id':self.users[1]})
        with self.assertRaises(ValidationError):tools['search_products'].invoke({'max_price':100})
        with self.assertRaises(ValidationError):tools['search_products'].invoke({'limit':100000})
        self.assertEqual(tools['search_products'].invoke({'currency':'CNY','max_price':20})['total'],2)
        self.assertEqual(tools['search_products'].invoke({'query':'%'})['total'],0)
        self.assertEqual(tools['get_product_details'].invoke({'product_id':p[0]})['product_id'],p[0])

    def test_manager_coordinates_three_specialists_and_preserves_context(self):
        self.client.post('/api/activity/browsing',headers=self.headers[0],json={'product_id':self.products[0],'visit_key':uuid4().hex})
        order=self.client.post('/api/shop/orders',headers=self.headers[0],json=shop_fixtures.ShopTests.checkout_body(self)).json()
        def inspect_browsing(messages):
            data=json.loads(next(m.content for m in reversed(messages) if isinstance(m,ToolMessage)))
            self.assertEqual(data['items'][0]['product_id'],self.products[0])
            return AIMessage(content='',tool_calls=[call('get_product_details',{'product_id':self.products[0]},'details')])
        def review_orders(messages):
            reports=[json.loads(m.content) for m in messages if isinstance(m,ToolMessage)]
            self.assertEqual([r['agent'] for r in reports],['product_agent','order_agent'])
            return AIMessage(content='',tool_calls=[call('aftersales_agent',{'task':'核实 '+order['number']+' 的退款规则'},'after')])
        model=ScriptedModel([
            AIMessage(content='',tool_calls=[call('product_agent',{'task':'查询最近浏览和商品详情'},'product'),call('order_agent',{'task':'核实当前订单'},'order')]),
            AIMessage(content='',tool_calls=[call('get_my_browsing_history',{})]),inspect_browsing,
            AIMessage(content='最近看过商品0，商品详情已核实。'),
            AIMessage(content='',tool_calls=[call('list_my_orders',{})]),
            AIMessage(content='',tool_calls=[call('get_my_order_details',{'order_id':order['id']})]),
            AIMessage(content='订单 '+order['number']+' 待支付。'),review_orders,
            AIMessage(content='',tool_calls=[call('get_refund_policy',{},'policy'),call('get_my_order_details',{'order_number':order['number']},'after_order')]),
            AIMessage(content='该订单待支付，可在订单页取消，无需退款。'),
            AIMessage(content='你最近看过商品0，订单待支付，可在订单页取消，无需退款。')])
        question='刚才看的商品和我的订单怎样，退款有什么要求？'
        result=self.agent(model).invoke({'user_id':self.users[0],'session_factory':lambda:Session(self.db_engine),
            'product_id':self.products[0],'order_id':order['number'],'user_input':question,
            'conversation_history':[{'role':'user','content':'我喜欢蓝牙耳机'},{'role':'assistant','content':'我记下了'},{'role':'user','content':question}]})
        meta=result['agent_metadata']
        self.assertEqual(meta['mode'],'manager_multi_agent');self.assertEqual(meta['steps'],11);self.assertEqual(meta['manager_rounds'],3)
        self.assertEqual([a['agent'] for a in meta['agents']],['product_agent','order_agent','aftersales_agent'])
        self.assertEqual([a['status'] for a in meta['agents']],['completed']*3)
        self.assertEqual([t['name'] for t in meta['tools']],['get_my_browsing_history','get_product_details','list_my_orders','get_my_order_details','get_refund_policy','get_my_order_details'])
        self.assertEqual(sum(m.content==question for m in model.inputs[0]),1)
        self.assertTrue(any(m.content=='我喜欢蓝牙耳机' for m in model.inputs[1]))
        self.assertIn(order['number'],model.inputs[0][0].content)
        self.assertTrue(any(order['number'] in m.content for m in model.inputs[8]))
        self.assertEqual(model.bindings[0],{'product_agent','order_agent','aftersales_agent'})
        self.assertNotIn('get_my_order_details',model.bindings[1])
        self.assertNotIn('search_products',model.bindings[4])
        self.assertNotIn('get_refund_policy',model.bindings[4])
        self.assertEqual({t['agent'] for t in meta['tools']},{'product_agent','order_agent','aftersales_agent'})
        self.assertNotIn('summary',json.dumps(meta));self.assertNotIn('test-secret',json.dumps(meta))

    def test_manager_and_workers_reject_excess_capabilities_and_limit_loops(self):
        model=ScriptedModel([
            AIMessage(content='',tool_calls=[call('create_refund',{'amount':1})]),
            AIMessage(content='',tool_calls=[call('order_agent',{'task':'查询其他人','user_id':self.users[1]})]),
            AIMessage(content='',tool_calls=[call('product_agent',{'task':'尝试查订单'})]),
            AIMessage(content='',tool_calls=[call('get_my_order_details',{'order_id':1})]),
            AIMessage(content='商品专员无权查询订单。'),AIMessage(content='只能查询当前账号，无法执行退款。')])
        result=self.agent(model).invoke({'user_id':self.users[0],'session_factory':lambda:Session(self.db_engine),'user_input':'查其他人的订单并退款'})
        self.assertEqual([t['status'] for t in result['agent_metadata']['agents']],['rejected','invalid_arguments','incomplete'])
        self.assertEqual(result['agent_metadata']['tools'][0]['status'],'rejected')
        repeating=ScriptedModel([
            AIMessage(content='',tool_calls=[call('product_agent',{'task':'查询商品'})]),
            AIMessage(content='',tool_calls=[call('search_products',{},'one'),call('search_products',{},'two')]),
            AIMessage(content='只能取得部分结果。'),AIMessage(content='部分查询受限，请缩小范围。')])
        result=self.agent(repeating,max_tools=1).invoke({'user_id':self.users[0],'session_factory':lambda:Session(self.db_engine),'user_input':'一直查询'})
        self.assertTrue(result['agent_metadata']['limited'])
        self.assertEqual([t['status'] for t in result['agent_metadata']['tools']],['ok','limit'])
        with Session(self.db_engine) as db:self.assertEqual(db.get(SaleOffer,self.products[0]).stock,5)

    def test_shared_model_and_delegation_limits_stop_whole_team(self):
        model=ScriptedModel([AIMessage(content='',tool_calls=[call('product_agent',{'task':'查询商品'})]),
            AIMessage(content='',tool_calls=[call('search_products',{})])])
        result=self.agent(model,max_steps=2).invoke({'user_id':self.users[0],'session_factory':lambda:Session(self.db_engine),'user_input':'商品咨询'})
        self.assertEqual(result['agent_metadata']['steps'],2);self.assertTrue(result['agent_metadata']['limited'])
        model=ScriptedModel([AIMessage(content='',tool_calls=[call('product_agent',{'task':'介绍服务'})]),AIMessage(content='可以咨询商品。'),
            AIMessage(content='',tool_calls=[call('order_agent',{'task':'继续查询'})]),AIMessage(content='本轮调度已达上限。')])
        result=self.agent(model,max_delegations=1).invoke({'user_id':self.users[0],'session_factory':lambda:Session(self.db_engine),'user_input':'反复调度'})
        self.assertEqual([a['status'] for a in result['agent_metadata']['agents']],['completed','limit'])
        self.assertTrue(result['agent_metadata']['limited'])

    def test_specialist_failure_does_not_discard_other_results_or_expose_errors(self):
        def inspect_partial(messages):
            reports=[json.loads(m.content) for m in messages if isinstance(m,ToolMessage)]
            self.assertEqual([r['status'] for r in reports],['unavailable','completed'])
            return AIMessage(content='商品暂时无法核实，当前没有订单。')
        model=ScriptedModel([AIMessage(content='',tool_calls=[call('product_agent',{'task':'商品'},'p'),call('order_agent',{'task':'订单'},'o')]),
            lambda _:(_ for _ in ()).throw(RuntimeError('SECRET_PROVIDER_ERROR')),
            AIMessage(content='',tool_calls=[call('list_my_orders',{})]),AIMessage(content='当前账号没有订单。'),inspect_partial])
        result=self.agent(model).invoke({'user_id':self.users[0],'session_factory':lambda:Session(self.db_engine),'user_input':'商品和订单'})
        self.assertEqual([a['status'] for a in result['agent_metadata']['agents']],['unavailable','completed'])
        self.assertNotIn('SECRET_PROVIDER_ERROR',json.dumps(result));self.assertIn('当前没有订单',result['answer'])

    def test_manager_round_deadline_and_final_synthesis_failure_fall_back_safely(self):
        payload={'user_id':self.users[0],'session_factory':lambda:Session(self.db_engine),'user_input':'查询商品'}
        model=ScriptedModel([])
        result=self.agent(model,budget=0).invoke(payload)
        self.assertTrue(result['agent_metadata']['limited']);self.assertEqual(result['agent_metadata']['steps'],0)
        self.assertEqual(model.inputs,[])
        model=ScriptedModel([AIMessage(content='',tool_calls=[call('product_agent',{'task':'介绍服务'})]),AIMessage(content='可提供商品咨询。')])
        result=self.agent(model,max_manager_steps=1).invoke(payload)
        self.assertTrue(result['agent_metadata']['limited']);self.assertIn('可提供商品咨询',result['answer'])
        model=ScriptedModel([AIMessage(content='',tool_calls=[call('product_agent',{'task':'介绍服务'})]),AIMessage(content='可提供商品咨询。'),
            lambda _:(_ for _ in ()).throw(RuntimeError('SECRET_FINAL_ERROR'))])
        result=self.agent(model).invoke(payload)
        self.assertIn('可提供商品咨询',result['answer']);self.assertIn('部分查询未能完成',result['answer'])
        self.assertNotIn('SECRET_FINAL_ERROR',json.dumps(result))

    def test_chat_endpoint_persists_team_trace_and_next_turn_context(self):
        sid=activity_fixtures.ActivityTests.new_session(self,product_id=self.products[0])
        self.client.post('/api/activity/browsing',headers=self.headers[0],json={'product_id':self.products[0],'visit_key':uuid4().hex})
        model=ScriptedModel([AIMessage(content='',tool_calls=[call('product_agent',{'task':'最近浏览'})]),
            AIMessage(content='',tool_calls=[call('get_my_browsing_history',{})]),AIMessage(content='最近浏览商品0。'),
            AIMessage(content='你最近浏览的是商品0。'),AIMessage(content='你刚才问过最近浏览的商品。')])
        with patch('app.services.chat.support_agent',self.agent(model)):
            first=self.client.post(f'/api/activity/sessions/{sid}/messages',headers=self.headers[0],json={'content':'我最近看了什么？','request_key':uuid4().hex})
            self.assertEqual(first.status_code,200,first.text)
            meta=first.json()['items'][-1]['agent_metadata']
            self.assertEqual(meta['tools'][0]['name'],'get_my_browsing_history');self.assertEqual(meta['agents'][0]['agent'],'product_agent')
            second=self.client.post(f'/api/activity/sessions/{sid}/messages',headers=self.headers[0],json={'content':'我刚才问过什么？','request_key':uuid4().hex})
            self.assertEqual(second.status_code,200,second.text)
        self.assertTrue(any(m.content=='你最近浏览的是商品0。' for m in model.inputs[-1]))
        messages=self.client.get(f'/api/activity/sessions/{sid}',headers=self.headers[0]).json()['items']
        self.assertEqual(len(messages),4);self.assertEqual(messages[1]['agent_metadata']['model'],'test-model')

    def test_missing_configuration_and_provider_errors_are_safe(self):
        sid=activity_fixtures.ActivityTests.new_session(self)
        broken=SupportAgent(settings_loader=lambda:(_ for _ in ()).throw(AgentConfigurationError('请配置 DS_API_KEY')))
        with patch('app.services.chat.support_agent',broken):
            response=self.client.post(f'/api/activity/sessions/{sid}/messages',headers=self.headers[0],json={'content':'你好','request_key':uuid4().hex})
        self.assertEqual(response.json()['items'][-1]['status'],'failed')
        self.assertIn('DS_API_KEY',response.json()['items'][-1]['content'])
        model=ScriptedModel([lambda _:(_ for _ in ()).throw(RuntimeError('SECRET_PROVIDER_ERROR'))])
        with patch('app.services.chat.support_agent',self.agent(model)):
            response=self.client.post(f'/api/activity/sessions/{sid}/messages',headers=self.headers[0],json={'content':'重试另一个问题','request_key':uuid4().hex})
        self.assertEqual(response.json()['items'][-1]['status'],'failed');self.assertNotIn('SECRET_PROVIDER_ERROR',response.text)
        with patch('app.agent.config.dotenv_values',return_value={'DS_API_KEY':'secret-value','DS_API_BASE':'https://api.deepseek.com','DEEPSEEK':'deepseek-flash'}),patch.dict('os.environ',{},clear=True):
            settings=load_settings()
            self.assertEqual(settings.model,'deepseek-flash');self.assertNotIn('secret-value',repr(settings))


if __name__=='__main__':unittest.main()
