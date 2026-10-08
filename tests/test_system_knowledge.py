import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch

from app_agent.catalog import Catalog
from app_agent.system_knowledge import graph_report, retrieve, task_context, relevant_apps
from app_agent.task_director import TaskDirector, resolve_window
from app_agent.routing import identify_windows, launch_app
from app_agent.machine import enrich_inventory
from app_agent.system_surfaces import launch_surface
from test_catalog import app, snapshot
from test_task_director import Desktop, reply


class KnowledgeTests(unittest.TestCase):
    def setUp(self):
        self.directory=tempfile.TemporaryDirectory();self.catalog=Catalog(self.directory.name)
        self.editor={**app(identity='start:writer'),'name':'Contoso Writer','aliases':['Contoso Writer']}
        self.catalog.sync({**snapshot([self.editor]),'machine':{'os':{'build':'26100.1'},
            'services':[{'name':'Spooler','status':'Running','start_type':'Automatic'}]},
            'local_evidence':{'start:writer':{'binaries':[{'path':'writer.exe','architecture':'x64','imports':['KERNEL32.dll']}],
                'manuals':[{'path':'manual.md','sha256':'abc','text':'ConfidentialOldDocument print report','truncated':False}]}}})
    def tearDown(self):self.catalog.close();self.directory.cleanup()

    def test_links_os_apps_services_binary_dependencies_and_manuals_without_mastery_claim(self):
        report=graph_report(self.catalog)
        self.assertEqual(report['summary']['kinds']['dependency'],1)
        self.assertIn('has_service',{e['relation'] for e in report['edges']})
        self.assertIn('imports',{e['relation'] for e in report['edges']})
        self.assertFalse(report['complete_blueprint']);self.assertFalse(report['universal_mastery_verified'])
        ids={n['id'] for n in report['nodes']}
        self.assertTrue(all(e['source'] in ids and e['target'] in ids for e in report['edges']))

    def test_retrieval_discovers_unfamiliar_app_from_documented_capability_without_network(self):
        self.catalog.save_blueprint('start:writer',1,{'capabilities':[{'name':'Mail merge','steps':['Combine spreadsheet rows with letter templates']}],
            'sources':[{'url':'https://example.com/manual'}]})
        with patch('app_agent.research.CloudResearcher',side_effect=AssertionError('Local retrieval cannot use provider')):
            hits=retrieve(self.catalog,'Combine spreadsheet rows with letter templates')
        cap=next(h for h in hits if h['kind']=='capability')
        self.assertEqual(cap['app_id'],'start:writer');self.assertFalse(cap['evidence']['operation_verified'])
        self.assertEqual(cap['level'],'documented')

    def test_graph_excludes_removed_and_old_generation_evidence(self):
        self.catalog.save_blueprint('start:writer',1,{'capabilities':[{'name':'Mail merge'}]})
        self.catalog.save_workflow('start:writer',1,{'task':'Merge letters','outcome':'result_observed','actions_executed':1})
        self.assertTrue(retrieve(self.catalog,'Merge letters'))
        self.catalog.sync(snapshot([{**self.editor,'version':'2'}]))
        self.assertFalse(retrieve(self.catalog,'Merge letters'))
        self.catalog.sync(snapshot([]))
        self.assertNotIn('application',graph_report(self.catalog)['summary']['kinds'])

    def test_private_document_controls_workflow_labels_and_manuals_not_sent_as_task_context(self):
        self.catalog.save_interface('start:writer',1,{'window':'Private window','controls':[
            {'name':'Private label','value':'PrivateDocumentText','type':'Edit','actions':['type'],'visible':True,'enabled':True},
            {'name':'Password','value':'secret','type':'Edit','actions':['type'],'visible':True,'password':True}]})
        self.catalog.save_workflow('start:writer',1,{'task':'PrivatePreviousRequest print report','outcome':'result_observed','actions_executed':1})
        encoded=json.dumps(task_context(self.catalog,'print report'))
        for private in ('PrivatePreviousRequest','ConfidentialOldDocument','Private window','Private label','PrivateDocumentText','secret'):
            self.assertNotIn(private,encoded)
        graph=json.dumps(graph_report(self.catalog))
        self.assertNotIn('PrivateDocumentText',graph);self.assertNotIn('secret',graph)

    def test_persistent_cached_graph_avoids_rebuild_and_research_change_invalidates_it(self):
        first=graph_report(self.catalog)
        calls=[];self.catalog.db.set_trace_callback(calls.append)
        self.assertEqual(first,graph_report(self.catalog))
        self.assertFalse(any('DELETE FROM knowledge' in c for c in calls))
        self.catalog.save_blueprint('start:writer',1,{'capabilities':[{'name':'Print'}]})
        self.assertNotEqual(first['revision'],graph_report(self.catalog)['revision'])

    def test_relevance_prioritizes_evidence_but_never_hides_unstudied_second_app(self):
        other={**app(identity='start:table'),'name':'Spreadsheet','aliases':['Spreadsheet']}
        self.catalog.sync(snapshot([self.editor,other]))
        selected=relevant_apps(self.catalog,'Write a letter in Contoso Writer and calculate totals',self.catalog.apps())
        self.assertEqual(selected[0]['id'],'start:writer')
        self.assertEqual({a['id'] for a in selected},{'start:writer','start:table'})

    def test_current_retrieved_evidence_reaches_general_planner_and_real_runner(self):
        task='Replace the document text with exactly: General agent works.'
        cloud=Mock();cloud.request.return_value=reply({'steps':[{'app_id':'start:writer','task':task,'expected_result':'General agent works.'}]})
        runner=Mock();runner.return_value.run.return_value={'task':task,'outcome':'result_observed','actions_executed':1,'history':[]}
        with patch('app_agent.task_director.ensure_blueprint',return_value={'capabilities':[]}):
            result=TaskDirector(self.catalog,cloud,lambda *args:True,lambda t:None,self.directory.name,
                resolve=lambda *args:Desktop(),runner=runner).run(task)
        self.assertEqual(result['outcome'],'steps_verified')
        self.assertEqual(json.loads(cloud.request.call_args.kwargs['input'])['system_knowledge']['os']['build'],'26100.1')
        self.assertIn('system_knowledge',runner.return_value.run.call_args.args[1])

    def test_os_build_change_invalidates_cached_plan(self):
        task='Inspect Contoso Writer'
        self.catalog.set_setting('task-plan:'+__import__('hashlib').sha256(task.encode()).hexdigest(),
            {'steps':[{'app_id':'start:writer','task':task,'expected_result':'ready'}],'generations':{'start:writer':1},'os_build':'26000.1'})
        cloud=Mock();cloud.request.return_value=reply({'steps':[{'app_id':'start:writer','task':task,'expected_result':'ready'}]})
        runner=Mock();runner.return_value.run.return_value={'outcome':'blocked','history':[],'actions_executed':0}
        with patch('app_agent.task_director.ensure_blueprint',return_value={}):
            TaskDirector(self.catalog,cloud,lambda *args:True,lambda t:None,self.directory.name,
                resolve=lambda *args:Desktop(),runner=runner).run(task)
        cloud.request.assert_called_once()


class IdentityAndSystemTests(unittest.TestCase):
    def test_unfamiliar_title_matches_only_full_registered_executable_not_basename(self):
        selected={'name':'Contoso Writer','aliases':['Contoso Writer'],'executables':[r'C:\Apps\Contoso\Writer.exe']}
        desktop=Mock();desktop.executable.side_effect=[r'C:\Other\Writer.exe',r'c:\apps\contoso\writer.exe']
        windows=[(1,'Other document'),(2,'Untitled')]
        self.assertEqual(identify_windows(selected,windows,desktop),[windows[1]])

    def test_process_access_failure_and_sensitive_window_never_become_fallback_target(self):
        selected={'name':'Contoso Writer','executables':[r'C:\Apps\Writer.exe']}
        desktop=Mock();desktop.executable.side_effect=OSError('Access denied')
        self.assertEqual(identify_windows(selected,[(1,'Untitled'),(2,'Password prompt')],desktop),[])
        desktop.executable.assert_called_once_with(1)

    def test_general_resolver_uses_executable_identity_without_launching_second_document(self):
        desktop=Mock();desktop.windows.return_value=[(10,'Untitled')];desktop.executable.return_value=r'C:\Apps\Writer.exe'
        launch=Mock()
        resolve_window({'name':'Contoso Writer','executables':[r'C:\Apps\Writer.exe']},threading.Event(),desktop=desktop,launch=launch)
        launch.assert_not_called();desktop.assert_called_once_with(10)

    def test_shared_explorer_process_cannot_identify_unrelated_os_surface(self):
        desktop=Mock();desktop.executable.return_value=r'C:\Windows\explorer.exe'
        self.assertEqual(identify_windows({'name':'Control Panel','system_surface':'control_panel','executables':[r'C:\Windows\explorer.exe']},[(1,'Private folder')],desktop),[])
        desktop.executable.assert_not_called()

    def test_file_explorer_fallback_requires_folder_window_class_as_well_as_full_executable(self):
        desktop=Mock();desktop.executable.return_value=r'C:\Windows\explorer.exe'
        desktop.window_class.side_effect=['Shell_TrayWnd','CabinetWClass']
        windows=[(1,'Taskbar'),(2,'Home')]
        self.assertEqual(identify_windows({'name':'File Explorer','system_surface':'file_explorer','executables':[r'C:\Windows\explorer.exe']},windows,desktop),[windows[1]])

    def test_os_surfaces_are_available_as_apps_with_build_generation_and_fixed_route(self):
        values=enrich_inventory(snapshot([]),{'os':{'build':'26100.1'},'system_surfaces':[{'id':'settings','executable':r'C:\Windows\ImmersiveControlPanel\SystemSettings.exe'}, {'id':'invented_shell'}]})
        surface=next(a for a in values['apps'] if a['id']=='system:settings')
        self.assertEqual(surface['version'],'26100.1');self.assertEqual(surface['name'],'Windows Settings')
        self.assertNotIn('system:invented_shell',{a['id'] for a in values['apps']})
        with patch('app_agent.system_surfaces.launch_surface') as launch:
            launch_app(surface);launch.assert_called_once_with('settings')
        with self.assertRaises(ValueError):launch_surface('settings; execute arbitrary code')

    def test_native_process_identity_closes_handle_when_os_query_fails(self):
        import ctypes
        from app_agent.desktop import window_process_executable
        kernel=Mock();kernel.OpenProcess.return_value=123;kernel.QueryFullProcessImageNameW.return_value=0
        with patch('app_agent.desktop.sys.platform','win32'),patch('ctypes.WinDLL',return_value=kernel,create=True),patch('app_agent.desktop.window_process_id',return_value=44):
            self.assertIsNone(window_process_executable(3))
        kernel.CloseHandle.assert_called_once_with(123)

    def test_os_launch_uses_trusted_system_directory_and_fixed_settings_uri(self):
        kernel=Mock()
        def windows(buffer,size):buffer.value=r'C:\Windows';return len(buffer.value)
        def system(buffer,size):buffer.value=r'C:\Windows\System32';return len(buffer.value)
        kernel.GetWindowsDirectoryW.side_effect=windows;kernel.GetSystemDirectoryW.side_effect=system
        with patch('app_agent.system_surfaces.sys.platform','win32'),patch('ctypes.WinDLL',return_value=kernel,create=True),patch('app_agent.system_surfaces.Path.is_file',return_value=True),patch('app_agent.system_surfaces.subprocess.Popen') as run:
            launch_surface('settings')
        run.assert_called_once_with([str(Path(r'C:\Windows')/'explorer.exe'),'ms-settings:'])
