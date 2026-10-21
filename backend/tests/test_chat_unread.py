"""Unread persistence, viewer isolation, late replies and administrator monitoring."""
from datetime import datetime,timedelta,timezone
from unittest.mock import patch
from uuid import uuid4
import unittest
from sqlalchemy.orm import Session
import test_aftersales as fixtures
from app.database.activity_models import ChatMessage,ChatSession,ChatReadState
from app.database.models import User


class ChatUnreadTests(unittest.TestCase):
    def setUp(self):
        fixtures.AftersalesTests.setUp(self)
        self.sid=self.client.post('/api/activity/sessions',headers=self.headers[0],json={'title':'普通 AI 会话'}).json()['id']

    def tearDown(self):fixtures.AftersalesTests.tearDown(self)

    def send(self):
        with patch('app.api.activity.support_agent.invoke',return_value={'answer':'AI 回答'}) as model:
            result=self.client.post(f'/api/activity/sessions/{self.sid}/messages',headers=self.headers[0],
                json={'content':'请介绍这款商品','request_key':uuid4().hex})
            self.assertEqual(result.status_code,200,result.text)
            return model

    def total(self,admin=False,user=None):
        index=(2 if admin else 0) if user is None else user
        base='/api/admin/support-sessions' if admin else '/api/activity'
        return self.client.get(f'{base}/unread',headers=self.headers[index]).json()['total']

    def detail(self,admin=False,user=None):
        index=(2 if admin else 0) if user is None else user
        base='/api/admin/support-sessions' if admin else '/api/activity/sessions'
        return self.client.get(f'{base}/{self.sid}',headers=self.headers[index]).json()

    def read(self,snapshot,admin=False,user=None):
        index=(2 if admin else 0) if user is None else user
        base='/api/admin/support-sessions' if admin else '/api/activity/sessions'
        return self.client.post(f'{base}/{self.sid}/read',headers=self.headers[index],json={'read_through':snapshot['read_through']})

    def test_unread_is_persistent_and_independent_of_read_only_fetches(self):
        self.send()
        self.assertEqual(self.total(),1);self.assertEqual(self.total(True),1);self.assertEqual(self.total(user=1),0)
        snapshot=self.detail();self.detail(True)
        self.assertEqual(self.total(),1);self.assertEqual(self.total(True),1)
        self.assertEqual(self.read(snapshot).status_code,200)
        self.assertEqual(self.total(),0);self.assertEqual(self.total(True),1)
        self.assertEqual(self.read(self.detail(True),True).status_code,200)
        self.assertEqual(self.total(True),0)
        self.client.post(f'/api/admin/support-sessions/{self.sid}/messages',headers=self.headers[2],json={'content':'人工回复','request_key':uuid4().hex})
        self.assertEqual(self.total(),1);self.assertEqual(self.total(True),0)
        self.read(snapshot)
        self.assertEqual(self.total(),1)
        latest=self.detail();self.read(latest);self.read(snapshot)
        self.assertEqual(self.total(),0)
        self.assertEqual(self.client.get('/api/activity/sessions',headers=self.headers[0]).json()['items'][0]['unread_count'],0)

    def test_admin_can_monitor_ai_conversations_and_take_over_without_order(self):
        self.send()
        listing=self.client.get('/api/admin/support-sessions?status=none',headers=self.headers[2]).json()['items']
        self.assertEqual(listing[0]['id'],self.sid);self.assertEqual(listing[0]['unread_count'],1)
        self.assertEqual(listing[0]['customer_name'],'u0')
        self.assertEqual(self.detail(True)['session']['human_status'],'none')
        self.assertEqual(self.send().call_count,1)
        reply=self.client.post(f'/api/admin/support-sessions/{self.sid}/messages',headers=self.headers[2],
            json={'content':'您好，由我来帮您。','request_key':uuid4().hex})
        self.assertEqual(reply.status_code,200,reply.text);self.assertTrue(reply.json()['is_mine'])
        self.assertEqual(self.detail(True)['session']['human_status'],'active')
        self.send().assert_not_called()

    def test_unread_first_sort_and_filter_happen_before_pagination(self):
        self.send()
        for index in range(22):
            self.client.post('/api/activity/sessions',headers=self.headers[0],json={'title':f'更新但没有未读的会话{index}'})
        path='/api/admin/support-sessions'
        listing=self.client.get(path,headers=self.headers[2]).json()
        self.assertEqual(listing['total'],23);self.assertEqual(listing['items'][0]['id'],self.sid)
        filtered=self.client.get(path+'?unread_only=true',headers=self.headers[2]).json()
        self.assertEqual(filtered['total'],1);self.assertEqual(filtered['total_pages'],1)
        self.assertEqual(filtered['items'][0]['id'],self.sid)
        self.assertEqual(self.client.get(path+'?unread_only=true&status=active',headers=self.headers[2]).json()['total'],0)
        self.read(self.detail(True),True)
        self.assertEqual(self.client.get(path+'?unread_only=true',headers=self.headers[2]).json()['total'],0)

    def test_each_admin_has_independent_reads_and_other_staff_is_incoming(self):
        with Session(self.db_engine) as db:
            db.get(User,self.users[1]).role='super_admin';db.commit()
        self.send();self.read(self.detail(True),True)
        self.assertEqual(self.total(True),0);self.assertEqual(self.total(True,user=1),1)
        self.client.post(f'/api/admin/support-sessions/{self.sid}/messages',headers=self.headers[1],
            json={'content':'另一位客服回复','request_key':uuid4().hex})
        self.assertEqual(self.total(True),1)
        self.assertFalse(self.detail(True)['items'][-1]['is_mine'])
        self.assertTrue(self.detail(True,user=1)['items'][-1]['is_mine'])

    def test_late_completion_remains_unread_after_old_snapshot_ack(self):
        with Session(self.db_engine) as db:
            user_message=ChatMessage(session_id=self.sid,role='user',content='问题',request_key=uuid4().hex)
            pending=ChatMessage(session_id=self.sid,role='assistant',content='',status='pending',request_key=uuid4().hex)
            db.add_all([user_message,pending]);db.commit();pending_id=pending.id
        snapshot=self.detail();self.assertEqual(self.total(),0)
        with Session(self.db_engine) as db:
            message=db.get(ChatMessage,pending_id);message.status='completed';message.content='迟到的回答';message.updated_at=datetime.now(timezone.utc);db.commit()
        self.read(snapshot)
        self.assertEqual(self.total(),1)
        self.read(self.detail());self.assertEqual(self.total(),0)

    def test_permissions_invalid_timestamp_and_deleted_session_cleanup(self):
        self.send();snapshot=self.detail()
        for path in ['/api/admin/support-sessions','/api/admin/support-sessions/unread',f'/api/admin/support-sessions/{self.sid}']:
            self.assertEqual(self.client.get(path,headers=self.headers[0]).status_code,403)
        for base in ['/api/activity/sessions','/api/admin/support-sessions']:
            result=self.client.post(f'{base}/{self.sid}/read',headers=self.headers[1],json={'read_through':snapshot['read_through']})
            self.assertIn(result.status_code,[403,404])
        result=self.client.post(f'/api/activity/sessions/{self.sid}/read',headers=self.headers[0],
            json={'read_through':(datetime.now(timezone.utc)+timedelta(days=1)).isoformat()})
        self.assertEqual(result.status_code,422)
        self.read(snapshot);self.read(self.detail(True),True)
        self.assertEqual(self.client.delete(f'/api/activity/sessions/{self.sid}',headers=self.headers[0]).status_code,204)
        self.assertEqual(self.total(),0);self.assertEqual(self.total(True),0)
        with Session(self.db_engine) as db:
            self.assertIsNone(db.get(ChatReadState,(self.sid,self.users[0])))
            self.assertIsNone(db.get(ChatSession,self.sid))
