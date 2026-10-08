import json
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch
from types import SimpleNamespace
from pathlib import Path
from app_agent.catalog import Catalog
from app_agent.installation_watch import record_snapshot, reconcile, study_preview, probe_installers
from app_agent.system_knowledge import graph_report
from test_catalog import app, snapshot


def incoming(pid=10,started='20261009',version='2'):
    return {'process_id':pid,'started':started,'name':'ContosoSetup.exe','product_name':'Contoso Writer',
            'product_version':version,'publisher':'Contoso','command_line':'secret --key=private'}


class InstallerTests(unittest.TestCase):
    def setUp(self):
        self.directory=tempfile.TemporaryDirectory();self.catalog=Catalog(self.directory.name)
        self.selected={**app(identity='start:writer',version='2'),'name':'Contoso Writer','aliases':['Contoso Writer']}
    def tearDown(self):self.catalog.close();self.directory.cleanup()
    def record(self,items,complete=True):return record_snapshot(self.catalog,{'candidates':items,'complete':complete})
    def row(self):return self.catalog.db.execute('SELECT * FROM installation_candidates ORDER BY first_seen').fetchone()

    def test_running_installer_does_not_become_installed_app_and_never_stores_arguments(self):
        self.assertTrue(self.record([incoming()]))
        self.assertEqual(self.catalog.apps(),[]);self.assertEqual(self.row()['state'],'running_candidate')
        self.assertNotIn('secret',self.row()['metadata']);self.assertNotIn('command_line',self.row()['metadata'])
        self.assertFalse(graph_report(self.catalog)['nodes'][-1]['body']['installed_identity_confirmed'])

    def test_preview_studies_before_registration_then_reuses_only_matching_name_version_after_exit(self):
        self.record([incoming()]);cloud=Mock()
        blueprint={'name':'Contoso Writer','version':'2','capabilities':[{'name':'Write','steps':['Type text']}],'sources':[]}
        with patch('app_agent.research.research_app',return_value=blueprint) as research:
            result=study_preview(self.catalog,cloud,lambda t:None)
        self.assertEqual(result['status'],'preview_documented');self.assertFalse(result['installed_operation_verified'])
        self.assertEqual(research.call_args.kwargs['focus']['installation_stage'],'unconfirmed_running_installer')
        self.catalog.sync(snapshot([self.selected]));self.assertEqual(reconcile(self.catalog),[])
        self.record([]);self.assertEqual(reconcile(self.catalog),['Contoso Writer'])
        self.assertTrue(self.catalog.get('start:writer')['blueprint']['preview_identity_confirmed'])
        self.assertEqual(self.catalog.workflows('start:writer',1),[])
        graph=graph_report(self.catalog)
        self.assertIn('matched_installed_identity',{e['relation'] for e in graph['edges']})

    def test_failed_install_and_partial_process_snapshot_do_not_confirm_or_remove_candidate(self):
        self.record([incoming()]);self.record([],complete=False)
        self.assertEqual(self.row()['state'],'running_candidate')
        self.record([]);self.assertEqual(self.row()['state'],'process_exited')
        self.assertEqual(reconcile(self.catalog),[]);self.assertEqual(self.catalog.apps(),[])

    def test_old_existing_registration_is_not_mistaken_for_successful_install(self):
        self.catalog.sync(snapshot([self.selected]));self.record([incoming()]);self.record([])
        self.assertEqual(reconcile(self.catalog),[])
        self.assertIsNone(self.row()['app_id'])

    def test_changed_generation_can_match_completed_updater_but_wrong_version_cannot(self):
        self.catalog.sync(snapshot([{**self.selected,'version':'1'}]));self.record([incoming()]);self.record([])
        self.assertEqual(reconcile(self.catalog),[])
        self.catalog.sync(snapshot([self.selected]));self.assertEqual(reconcile(self.catalog),['Contoso Writer'])
        self.catalog.sync(snapshot([{**self.selected,'version':'3'}]))
        graph=graph_report(self.catalog)
        self.assertNotIn('matched_installed_identity',{e['relation'] for e in graph['edges']})

    def test_reused_process_id_retains_two_distinct_candidate_identities(self):
        self.record([incoming()]);self.record([]);self.record([incoming(started='20261010')])
        self.assertEqual(self.catalog.db.execute('SELECT COUNT(*) FROM installation_candidates').fetchone()[0],2)

    def test_generic_installer_never_triggers_speculative_provider_research(self):
        self.record([{**incoming(),'product_name':'Windows Installer'}])
        with patch('app_agent.research.research_app') as research:
            self.assertEqual(study_preview(self.catalog,Mock(),lambda t:None)['status'],'no_candidate')
        research.assert_not_called()

    def test_cancelled_preview_and_budget_limit_do_not_call_provider(self):
        self.record([incoming()]);cancel=threading.Event();cancel.set()
        self.catalog.consume_budget('research_budget',1)
        with patch('app_agent.research.research_app') as research:
            self.assertEqual(study_preview(self.catalog,Mock(),lambda t:None,cancel=cancel)['status'],'cancelled')
            self.assertEqual(study_preview(self.catalog,Mock(),lambda t:None,daily_limit=1)['status'],'daily_limit')
        research.assert_not_called()

    def test_failed_preview_records_retry_without_claiming_documented_or_spinning(self):
        self.record([incoming()])
        with patch('app_agent.research.research_app',side_effect=RuntimeError('HTTP 429')) as research:
            self.assertEqual(study_preview(self.catalog,Mock(),lambda t:None)['status'],'preview_failed')
            self.assertEqual(study_preview(self.catalog,Mock(),lambda t:None)['status'],'no_candidate')
        research.assert_called_once();self.assertEqual(self.row()['study_status'],'research_failed')
        self.assertIsNone(self.row()['blueprint']);self.assertIsNone(self.row()['app_id'])

    def test_cancel_during_research_discards_blueprint(self):
        self.record([incoming()]);cancel=threading.Event()
        def stop(*args,**kwargs):cancel.set();return {'name':'Contoso Writer','version':'2'}
        with patch('app_agent.research.research_app',side_effect=stop):
            study_preview(self.catalog,Mock(),lambda t:None,cancel=cancel)
        self.assertIsNone(self.row()['blueprint'])

    def test_removed_app_cannot_leave_dangling_installer_edges(self):
        self.record([incoming()]);self.record([]);self.catalog.sync(snapshot([self.selected]));reconcile(self.catalog)
        self.catalog.sync(snapshot([]))
        report=graph_report(self.catalog);ids={n['id'] for n in report['nodes']}
        self.assertTrue(all(e['source'] in ids and e['target'] in ids for e in report['edges']))

    def test_native_probe_reads_only_fixed_process_properties_and_public_version_resources(self):
        path=Path(self.directory.name)/'ContosoSetup.exe';path.write_bytes(b'MZ')
        process=SimpleNamespace(Name='ContosoSetup.exe',ProcessId=10,ExecutablePath=str(path),CreationDate='20261009')
        com=Mock();api=Mock();client=Mock();wmi=Mock();client.GetObject.return_value=wmi;wmi.ExecQuery.return_value=[process]
        def version(path,field):
            if field=='\\VarFileInfo\\Translation':return [(1033,1200)]
            return {'ProductName':'Contoso Writer','ProductVersion':'2','CompanyName':'Contoso'}[field.split('\\')[-1]]
        api.GetFileVersionInfo.side_effect=version
        with patch.dict('sys.modules',{'pythoncom':com,'win32api':api,'win32com':SimpleNamespace(client=client),'win32com.client':client}),patch('app_agent.installation_watch.os',SimpleNamespace(name='nt')):
            result=probe_installers()
        self.assertEqual(result['candidates'][0]['product_name'],'Contoso Writer')
        self.assertNotIn('CommandLine',wmi.ExecQuery.call_args.args[0])
        com.CoInitialize.assert_called_once();com.CoUninitialize.assert_called_once()

    def test_campaign_prioritizes_preview_within_the_same_batch_allowance(self):
        from app_agent.campaign import study_campaign
        self.record([incoming()])
        blueprint={'name':'Contoso Writer','version':'2','capabilities':[],'sources':[]}
        with patch('app_agent.research.research_app',return_value=blueprint),patch('app_agent.parallel_study.study_batch',return_value=([],'progress')) as batch:
            report=study_campaign(self.catalog,Mock(),lambda t:None,daily_limit=0,max_apps=1,max_plans=0)
        self.assertEqual(report['research'][0]['status'],'preview_documented')
        self.assertEqual(batch.call_args.args[4],0)
