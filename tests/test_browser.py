"""Browser routing, bounded transport, independent proof and durable recovery."""
import copy
import json
from pathlib import Path
import socket
import struct
import tempfile
import threading
import unittest
from unittest.mock import Mock,patch
from app_agent.browser import Browser,browser_request
from app_agent.browser_protocol import DevTools,MAX_MESSAGE
from app_agent.browser_checks import FixturePlanner
from app_agent.catalog import Catalog
from app_agent.job_runtime import run_next
from app_agent.jobs import Jobs
from app_agent.research import public_https
from app_agent.runner import result_matches,reconcile_action
from app_agent.task_director import TaskDirector
from app_agent.tool_broker import choose_tool
from app_agent.workflow_replay import guard

TASK='Open "https://example.com/form" in a browser and fill Message, confirm, click Apply and verify exactly: "Saved: Hello 世界"'


def control(identity,name,kind='Text',actions=None,value='',state=None):
    return {'id':identity,'name':name,'type':kind,'automation_id':'page:output' if kind=='Text' else 'dom:'+str(identity),
            'actions':actions or [],'value':value,'state':state or {},'visible':True,'enabled':True,'password':False}


class Adapter:
    instances=[]
    def __init__(self,guard=lambda:None):
        self.guard=guard;self.info={'product':'FixtureBrowser/1','revision':'1','protocolVersion':'1'}
        self.text='';self.on=False;self.output='';self.actions=[];self.closed=False;self.instances.append(self)
    def start(self,url):self.url=url;return self
    def observe(self):
        self.guard()
        return {'window':'Managed browser page','window_handle':1,'process_id':2,'url':self.url,'controls':[
            control(0,'Page','Window'),control(2,'Message','Edit',['type'],self.text),
            control(3,'Confirmed','CheckBox',['toggle'],state={'toggle':'on' if self.on else 'off'}),
            control(4,'Apply','Button',['click']),control(5,self.output)]}
    def act(self,action):
        self.guard();self.actions.append(action)
        if action['kind']=='type':self.text=action['text']
        elif action['kind']=='toggle':self.on=action['state']=='on'
        elif action['kind']=='click':self.output='Saved: '+self.text
    def close(self):self.closed=True


class RequestTests(unittest.TestCase):
    def test_exact_browser_grammar_preserves_task_url_and_case(self):
        request=browser_request(TASK);self.assertEqual(request['url'],'https://example.com/form');self.assertEqual(request['expected_result'],'Saved: Hello 世界')
        self.assertEqual(choose_tool(TASK,[])['kind'],'browser')
        self.assertEqual(browser_request('Use the browser at "https://example.com" to click Go and verify exactly: "DONE".')['expected_result'],'DONE')
    def test_unspecified_url_or_output_is_not_silently_invented(self):
        for task in ('Open a browser and send my mail','Open "https://example.com" in a browser and fill Message',
                     'Open "https://example.com" in a browser and click Go and verify exactly: ""'):
            self.assertIsNone(browser_request(task))
    def test_selected_app_and_exact_editor_text_keep_original_route(self):
        self.assertEqual(choose_tool(TASK,[],{'id':'selected'})['kind'],'desktop')
        self.assertEqual(choose_tool('Type exactly: '+TASK,[])['kind'],'desktop')
    def test_oversized_goal_and_expected_result_are_rejected(self):
        self.assertIsNone(browser_request(TASK.replace('fill Message','x'*4001)))
        self.assertIsNone(browser_request(TASK.replace('Saved: Hello 世界','x'*2001)))
    def test_private_http_credential_and_nonstandard_ports_rejected(self):
        for url in ('http://example.com','https://localhost','https://127.0.0.1','https://user:pass@example.com','https://example.com:8443'):
            with self.subTest(url=url),self.assertRaises(ValueError):public_https(url)
    def test_production_browser_cannot_disable_sandbox(self):
        with self.assertRaises(ValueError):Browser(fixture_no_sandbox=True)
    def test_windows_browser_cannot_disable_sandbox_even_for_fixture(self):
        with patch('app_agent.browser.sys.platform','win32'),self.assertRaises(ValueError):Browser(check_url=lambda url:None,fixture_no_sandbox=True)
    def test_url_change_rejects_previously_approved_action(self):
        before=Adapter().start('https://example.com').observe();after={**before,'url':'https://different.example.com'}
        self.assertIsNone(reconcile_action({'kind':'type','target':2},before,after));self.assertNotEqual(guard(before),guard(after))
    def test_link_destination_change_invalidates_recipe_guard(self):
        before=Adapter().start('https://example.com').observe();after=copy.deepcopy(before)
        before['controls'][3]['href']='https://example.com/a';after['controls'][3]['href']='https://example.com/b'
        self.assertNotEqual(guard(before),guard(after))
    def test_input_button_body_text_cannot_certify_browser_result(self):
        snapshot={'controls':[control(1,'Saved: Hello 世界','Button'),control(2,'Message','Edit',['type'],'Saved: Hello 世界'),
                              {**control(3,'Saved: Hello 世界'),'automation_id':'page:text'}]}
        self.assertFalse(result_matches(snapshot,'Saved: Hello 世界',result_control_id='page:output'))
    def test_browser_output_requires_case_sensitive_complete_text(self):
        for value in ('not Saved: Hello 世界','Saved: Hello 世界 extra','saved: Hello 世界'):
            self.assertFalse(result_matches({'controls':[control(1,value)]},'Saved: Hello 世界',result_control_id='page:output'))
        self.assertTrue(result_matches({'controls':[control(1,'Saved: Hello 世界')]},'Saved: Hello 世界',result_control_id='page:output'))
    def test_truncated_output_cannot_certify_complete_result(self):
        self.assertFalse(result_matches({'controls':[control(1,'x'*2000,state={'truncated':True})]},'x'*2000,result_control_id='page:output'))
    def test_failed_executable_probe_leaves_no_profile(self):
        browser=Browser(check_url=lambda url:None)
        with patch('app_agent.browser.executable',side_effect=RuntimeError('Missing')),self.assertRaises(RuntimeError):browser.start('https://example.com')
        self.assertIsNone(browser.profile)
    def test_forbidden_browser_request_is_failed_before_network_dispatch(self):
        browser=Browser();browser.transport=Mock()
        browser.event({'method':'Fetch.requestPaused','params':{'requestId':'owned-request','request':{'url':'https://127.0.0.1/private'}}})
        self.assertEqual(browser.blocked,1);self.assertEqual(browser.transport.send.call_args.args[0],'Fetch.failRequest')


class TransportTests(unittest.TestCase):
    def setUp(self):
        self.local,self.peer=socket.socketpair();self.local.settimeout(.01)
        self.client=DevTools.__new__(DevTools);self.client.socket=self.local;self.client.guard=lambda:None
        self.client.buffer=b'';self.client.sequence=0;self.client.session='owned';self.client.events=lambda event:None
    def tearDown(self):self.local.close();self.peer.close()
    def frame(self,value,opcode=1,final=True):
        value=value if isinstance(value,bytes) else json.dumps(value).encode();size=len(value)
        return bytes([(128 if final else 0)|opcode,size])+value if size<126 else bytes([(128 if final else 0)|opcode,126])+struct.pack('!H',size)+value
    def test_commands_mask_payload_and_bind_owned_session(self):
        self.client.send('Runtime.enable',session='owned');raw=self.peer.recv(4096);self.assertEqual(raw[0],129);self.assertTrue(raw[1]&128)
        size=raw[1]&127;mask=raw[2:6];payload=bytes(c^mask[i%4] for i,c in enumerate(raw[6:6+size]))
        self.assertEqual(json.loads(payload)['sessionId'],'owned')
    def test_event_and_rpc_response_are_distinguished(self):
        events=[];self.client.events=events.append
        self.peer.sendall(self.frame({'method':'Fetch.requestPaused','params':{}})+self.frame({'id':1,'result':{'ok':True}}))
        self.assertEqual(self.client.call('Runtime.enable'),{'ok':True});self.assertEqual(events[0]['method'],'Fetch.requestPaused')
    def test_fragmented_json_and_ping_are_supported(self):
        self.peer.sendall(self.frame(b'{"result":',final=False)+self.frame(b'ping',opcode=9)+self.frame(b'42}',opcode=0))
        self.assertEqual(self.client._message(__import__('time').monotonic()+1),{'result':42})
        self.assertEqual(self.peer.recv(4096)[0],138)
    def test_oversized_message_is_rejected_before_reading_payload(self):
        self.peer.sendall(bytes([129,127])+struct.pack('!Q',MAX_MESSAGE+1))
        with self.assertRaises(ValueError):self.client._message(__import__('time').monotonic()+1)
    def test_invalid_masked_server_frame_is_rejected(self):
        self.peer.sendall(bytes([129,128]))
        with self.assertRaises(ValueError):self.client._message(__import__('time').monotonic()+1)
    def test_timeout_and_stop_interrupt_waits(self):
        with self.assertRaisesRegex(TimeoutError,r'Browser command timed out: Runtime\.enable.*do not retry an action automatically'):
            self.client.call('Runtime.enable',timeout=.01)
        self.client.guard=Mock(side_effect=RuntimeError('Stopped'))
        with self.assertRaisesRegex(RuntimeError,'Stopped'):self.client.call('Runtime.enable')
    def test_remote_devtools_endpoints_are_rejected_before_socket(self):
        with patch('app_agent.browser_protocol.socket.create_connection') as connect:
            for url in ('ws://example.com:99/devtools/browser/x','ws://127.0.0.1:100/devtools/browser/x','wss://127.0.0.1:99/devtools/browser/x','ws://127.0.0.1:99/devtools/page/x'):
                with self.assertRaises(ValueError):DevTools(url,99)
            connect.assert_not_called()
    def test_rpc_errors_do_not_become_success(self):
        self.peer.sendall(self.frame({'id':1,'error':{'message':'Unsupported command'}}))
        with self.assertRaisesRegex(RuntimeError,'Unsupported command'):self.client.call('Unknown.command')


class GoalTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name);Adapter.instances=[]
        self.catalog=Catalog(self.root);self.planner=FixturePlanner();self.cancel=threading.Event()
    def tearDown(self):self.catalog.close();self.temp.cleanup()
    def director(self,approve=lambda *args:True,checkpoint=None):
        return TaskDirector(self.catalog,self.planner,approve,lambda msg:None,self.root,self.cancel,checkpoint=checkpoint)
    def test_broker_operates_without_installed_app_and_records_exact_proof(self):
        with patch('app_agent.browser_tasks.Browser',Adapter):result=self.director().run(TASK)
        self.assertEqual(result['outcome'],'steps_verified');self.assertEqual(len(Adapter.instances[0].actions),3);self.assertTrue(Adapter.instances[0].closed)
        proof=result['steps'][0]['proof'];self.assertTrue(Path(proof['path']).is_file())
    def test_initial_permission_rejection_never_starts_browser(self):
        with patch('app_agent.browser_tasks.Browser',Adapter):result=self.director(approve=lambda *args:False).run(TASK)
        self.assertEqual(result['outcome'],'blocked');self.assertEqual(Adapter.instances,[])
    def test_stop_before_browser_start_never_dispatches(self):
        self.cancel.set()
        with patch('app_agent.browser_tasks.Browser',Adapter):result=self.director().run(TASK)
        self.assertEqual(result['outcome'],'cancelled');self.assertEqual(Adapter.instances,[])
    def test_runner_claim_cannot_replace_independent_output_proof(self):
        # A runner claim alone is not the final checkpoint proof.
        def lying_runner(*args):return Mock(run=Mock(return_value={'outcome':'result_observed'}))
        director=self.director();director.runner=lying_runner
        with patch('app_agent.browser_tasks.Browser',Adapter):result=director.run(TASK)
        self.assertEqual(result['outcome'],'verification_failed')
    def test_durable_queue_completes_and_reuses_without_provider(self):
        jobs=Jobs(self.root)
        try:identity=jobs.submit(TASK,autonomous=True)
        finally:jobs.close()
        with patch('app_agent.browser_tasks.Browser',Adapter):
            first=run_next(self.root,self.planner,lambda *args:True,lambda msg:None)
            self.assertEqual(first['id'],identity);self.assertEqual(first['status'],'completed')
            jobs=Jobs(self.root);jobs.submit(TASK,autonomous=True);jobs.close()
            no_provider=Mock(request=Mock(side_effect=RuntimeError('No provider')))
            second=run_next(self.root,no_provider,lambda *args:True,lambda msg:None)
        self.assertEqual(second['status'],'completed');no_provider.request.assert_not_called()
    def test_verified_restart_reuses_historical_proof_without_reopening(self):
        jobs=Jobs(self.root);identity=jobs.submit(TASK,autonomous=True);checkpoint=jobs.claim(identity)
        try:
            with patch('app_agent.browser_tasks.Browser',Adapter):first=self.director(checkpoint=checkpoint).run(TASK)
            count=len(Adapter.instances)
            with patch('app_agent.browser_tasks.Browser',Adapter):second=self.director(checkpoint=checkpoint).run(TASK)
            self.assertEqual(second['outcome'],'steps_verified');self.assertEqual(len(Adapter.instances),count)
            self.assertIn('not revalidated',second['scope']);self.assertEqual(second['verified_results'],first['verified_results'])
        finally:jobs.close()
    def test_tampered_historical_evidence_does_not_trigger_reclick(self):
        jobs=Jobs(self.root);identity=jobs.submit(TASK,autonomous=True);checkpoint=jobs.claim(identity)
        try:
            with patch('app_agent.browser_tasks.Browser',Adapter):first=self.director(checkpoint=checkpoint).run(TASK)
            Path(first['steps'][0]['proof']['path']).write_text('{}');count=len(Adapter.instances)
            with patch('app_agent.browser_tasks.Browser',Adapter):second=self.director(checkpoint=checkpoint).run(TASK)
            self.assertEqual(second['outcome'],'verification_failed');self.assertEqual(len(Adapter.instances),count)
        finally:jobs.close()
    def test_post_dispatch_exception_preserves_uncertain_effect(self):
        class Interrupted(Adapter):
            def act(self,action):super().act(action);raise ConnectionError('Interrupted after dispatch')
        jobs=Jobs(self.root);identity=jobs.submit(TASK,autonomous=True);checkpoint=jobs.claim(identity)
        try:
            with patch('app_agent.browser_tasks.Browser',Interrupted):result=self.director(checkpoint=checkpoint).run(TASK)
            self.assertEqual(jobs.settle(checkpoint,result)['status'],'needs_review');self.assertIsNone(jobs.claim(identity))
        finally:jobs.close()


if __name__=='__main__':unittest.main()
