import json
from pathlib import Path
import struct
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch

from app_agent.catalog import Catalog
from app_agent.local_inspection import executable_path, inspect_installation, pe_metadata, safe_root
from app_agent.machine import onboard_snapshot, machine_report, scan_machine
from app_agent.learning import ensure_blueprint
from app_agent.parallel_study import study_batch
from app_agent.research import research_app
from app_agent.task_director import task_plan


def empty():
    return {'apps': [], 'complete_sources': ['registry', 'start_menu', 'store'], 'warnings': []}


def windows():
    return {'os': {'name': 'Microsoft Windows', 'version': '24H2', 'build': '26100.1', 'architecture': 'AMD64'},
            'app_paths': [], 'com_servers': [], 'file_types': [],
            'services': [{'name': 'EventLog', 'status': 'Running', 'start_type': 'Automatic'}], 'warnings': []}


def pe_file(path):
    data = bytearray(1024)
    data[:2] = b'MZ'; struct.pack_into('<I', data, 60, 128)
    data[128:132] = b'PE\0\0'; struct.pack_into('<HH', data, 132, 0x8664, 1)
    struct.pack_into('<H', data, 148, 240); struct.pack_into('<H', data, 152, 0x20b)
    struct.pack_into('<II', data, 152 + 112 + 8, 0x1000, 40)
    struct.pack_into('<IIII', data, 152 + 240 + 8, 512, 0x1000, 512, 512)
    struct.pack_into('<I', data, 512 + 12, 0x1050)
    data[592:605] = b'KERNEL32.dll\0'
    path.write_bytes(data)


class MachineOnboardingTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.root = Path(self.directory.name)
        self.catalog = Catalog(self.root / 'agent-data')
        self.install = self.root / 'Office'
        self.install.mkdir()
        self.exe = self.install / 'Word.exe'
        pe_file(self.exe)
        (self.install / 'manual.md').write_text('Create a blank document. Type the requested text into the editor. The editor displays the requested text.')
        (self.install / 'app.config').write_text('secret=must-not-be-uploaded')
        self.probe = windows()
        self.probe['app_paths'] = [{'name': 'Word.exe', 'executable': str(self.exe)}]
        self.probe['com_servers'] = [{'progid': 'Word.Application', 'clsid': '{00000000-0000-0000-0000-000000000000}',
                                      'server': '"' + str(self.exe) + '" /Automation private-argument'}]
        self.probe['file_types'] = [{'extension': '.docx', 'progid': 'Word.Document.12'}]

    def tearDown(self):
        self.catalog.close()
        self.directory.cleanup()

    def office(self):
        return next(a for a in self.catalog.apps() if a['name'] == 'Word')

    def test_clean_windows_then_office_has_local_evidence_before_any_provider_call(self):
        with patch('app_agent.research.CloudResearcher', side_effect=AssertionError('Local onboarding cannot call provider')):
            first = onboard_snapshot(empty(), self.catalog, windows())
            self.assertEqual(first['new'], ['Microsoft Windows'])
            self.assertEqual(self.catalog.get('system:windows')['role'], 'platform')
            second = onboard_snapshot(empty(), self.catalog, self.probe)
        app = self.office()
        self.assertIn('Word', second['new'])
        self.assertEqual(app['file_types'], ['.docx'])
        self.assertEqual(app['automation_registrations'][0]['progid'], 'Word.Application')
        self.assertNotIn('private-argument', json.dumps(app))
        evidence = self.catalog.local_evidence(app['id'], 1)
        self.assertEqual(evidence['binaries'][0]['imports'], ['KERNEL32.dll'])
        self.assertEqual(evidence['binaries'][0]['architecture'], 'x64')
        self.assertEqual(len(evidence['manuals']), 1)
        self.assertNotIn('must-not-be-uploaded', json.dumps(evidence))
        report = json.loads((self.catalog.data_dir / 'machine-report.json').read_text())
        self.assertEqual(report['summary']['with_observed_capabilities'], 0)
        self.assertFalse(report['universal_mastery_verified'])
        self.assertFalse(report['machine']['history_accessed'])
        self.assertEqual(report['machine']['services'][0]['name'], 'EventLog')
        self.assertEqual(self.catalog.next_research()['id'], app['id'])

    def test_repeat_scan_reuses_static_evidence_without_invalidating_and_survives_restart(self):
        onboard_snapshot(empty(), self.catalog, self.probe)
        app = self.office()
        with patch('app_agent.local_inspection.pe_metadata', side_effect=AssertionError('Unchanged binaries should use cache')):
            changes = onboard_snapshot(empty(), self.catalog, self.probe)
        self.assertEqual(changes['updated'], [])
        self.assertEqual(self.office()['generation'], 1)
        self.assertEqual(self.catalog.local_evidence(app['id'], 1)['status'], 'cached_installation')
        self.catalog.close(); self.catalog = Catalog(self.root / 'agent-data')
        self.assertEqual(machine_report(self.catalog)['summary']['locally_inspected'], 1)

    def test_same_version_binary_change_retires_workflow_and_old_research(self):
        onboard_snapshot(empty(), self.catalog, self.probe)
        app = self.office()
        self.catalog.save_blueprint(app['id'], 1, {'capabilities': [{'name': 'Write'}]})
        self.catalog.save_workflow(app['id'], 1, {'task': 'Write', 'outcome': 'result_observed', 'actions_executed': 1, 'history': []})
        self.exe.write_bytes(self.exe.read_bytes() + b'update')
        changed = onboard_snapshot(empty(), self.catalog, self.probe)
        updated = self.office()
        self.assertIn('Word', changed['updated'])
        self.assertEqual(updated['generation'], 2)
        self.assertIsNone(updated['blueprint'])
        self.assertEqual(self.catalog.workflows(updated['id'], 2), [])
        self.assertFalse(self.catalog.save_blueprint(app['id'], 1, {'stale': True}))
        self.assertIsNotNone(self.catalog.local_evidence(app['id'], 1))
        self.assertIsNotNone(self.catalog.local_evidence(app['id'], 2))

    def test_same_size_timestamp_preserved_binary_patch_is_still_detected(self):
        import os
        onboard_snapshot(empty(), self.catalog, self.probe)
        before = self.exe.stat()
        content = bytearray(self.exe.read_bytes()); content[-1] ^= 1
        self.exe.write_bytes(content)
        os.utime(self.exe, ns=(before.st_atime_ns, before.st_mtime_ns))
        result = onboard_snapshot(empty(), self.catalog, self.probe)
        self.assertIn('Word', result['updated'])
        self.assertEqual(self.office()['generation'], 2)
        self.assertEqual(self.catalog.local_evidence(self.office()['id'], 2)['status'], 'installation_observed')

    def test_local_manual_research_skips_web_search_and_does_not_claim_execution(self):
        onboard_snapshot(empty(), self.catalog, self.probe)
        app = self.office()
        cloud = Mock()
        cloud.find_sources.side_effect = AssertionError('Installed manual is sufficient')
        cloud.extract.return_value = {'capabilities': [{'name': 'Write', 'steps': ['Type'], 'expected_result': 'Text'}], 'limitations': []}
        blueprint = ensure_blueprint(self.catalog, app, cloud, lambda line: None)
        cloud.find_sources.assert_not_called()
        self.assertEqual(blueprint['evidence_origin'], 'installed_manuals')
        self.assertEqual(blueprint['installed_evidence']['automation_registrations'][0]['progid'], 'Word.Application')
        self.assertEqual(self.catalog.coverage(app['id'], 1)[0]['status'], 'documented_unverified')
        self.assertTrue(cloud.extract.call_args.args[2][0]['url'].startswith('installation-manual:'))

    def test_parallel_study_collects_database_context_on_owner_thread(self):
        onboard_snapshot(empty(), self.catalog, self.probe)
        # Prioritize the application, and take one item so OS docs are unrelated.
        self.catalog.set_setting('priority_apps', [self.office()['id']])
        cloud = Mock()
        cloud.extract.return_value = {'capabilities': [{'name': 'Write'}], 'limitations': []}
        with patch.object(self.catalog, 'local_evidence', wraps=self.catalog.local_evidence) as local:
            results, status = study_batch(self.catalog, cloud, lambda line: None, 0, 1, 3, threading.Event())
        self.assertEqual(results[0]['status'], 'documented')
        self.assertGreaterEqual(local.call_count, 1)
        cloud.find_sources.assert_not_called()

    def test_cancelled_onboarding_cannot_persist_partial_installation(self):
        stop = threading.Event(); stop.set()
        result = onboard_snapshot(empty(), self.catalog, self.probe, stop)
        self.assertEqual(result['status'], 'cancelled')
        self.assertEqual(self.catalog.apps(), [])
        self.assertFalse((self.catalog.data_dir / 'machine-report.json').exists())

    def test_failed_system_probe_retains_previous_machine_and_does_not_remove_apps(self):
        onboard_snapshot(empty(), self.catalog, self.probe)
        with patch('app_agent.windows_probe.probe_windows', side_effect=RuntimeError('Unavailable')):
            result = scan_machine(self.catalog, scanner=empty)
        self.assertIn('deferred', result['warnings'][0])
        self.assertEqual(self.office()['generation'], 1)
        self.assertEqual(self.catalog.get('system:windows')['version'], '26100.1')
        self.assertEqual(machine_report(self.catalog)['machine']['os']['build'], '26100.1')

    def test_complete_removal_and_reinstall_requeues_app(self):
        onboard_snapshot(empty(), self.catalog, self.probe)
        app = self.office()
        removed = onboard_snapshot(empty(), self.catalog, windows())
        self.assertIn('Word', removed['removed'])
        with self.assertRaises(KeyError): self.catalog.get(app['id'])
        onboard_snapshot(empty(), self.catalog, self.probe)
        self.assertEqual(self.office()['generation'], 2)
        self.assertEqual(self.office()['status'], 'queued')

    def test_task_planning_receives_installed_interfaces_but_cannot_choose_os_record(self):
        onboard_snapshot(empty(), self.catalog, self.probe)
        app = self.office(); task = 'Replace the document text with exactly: Hi'
        cloud = Mock(); cloud.request.return_value = {'output': [{'content': [{'type': 'output_text', 'text': json.dumps({'steps': [{'app_id': app['id'], 'task': task, 'expected_result': 'Hi'}]})}]}]}
        task_plan(task, self.catalog.apps(), cloud)
        inputs = json.loads(cloud.request.call_args.kwargs['input'])['apps']
        self.assertEqual(len(inputs), 1)
        self.assertTrue(inputs[0]['launchable'])
        self.assertEqual(inputs[0]['automation_interfaces'], ['Word.Application'])
        self.assertEqual(inputs[0]['file_types'], ['.docx'])
        self.assertNotIn('private-argument', json.dumps(inputs))
        cloud.request.return_value['output'][0]['content'][0]['text'] = json.dumps({'steps': [{'app_id': 'system:windows', 'task': task, 'expected_result': 'Hi'}]})
        with self.assertRaises(ValueError): task_plan(task, self.catalog.apps(), cloud)

    def test_registered_executable_launch_is_literal_and_missing_target_is_rejected(self):
        from app_agent.routing import launch_app
        onboard_snapshot(empty(), self.catalog, self.probe)
        with patch('app_agent.routing.subprocess.Popen') as run:
            launch_app(self.office())
            run.assert_called_once_with([str(self.exe)])
            self.exe.unlink()
            with self.assertRaises(RuntimeError): launch_app(self.office())
            self.assertEqual(run.call_count, 1)

    def test_inspector_refuses_symlinks_and_reports_partial_bounded_coverage(self):
        secret = self.root / 'private'; secret.mkdir()
        (secret / 'manual.txt').write_text('Private personal content')
        (self.install / 'help-link').symlink_to(secret, target_is_directory=True)
        with patch('app_agent.local_inspection.FILE_LIMIT', 1):
            evidence = inspect_installation({'location': str(self.install)}, deadline_seconds=3)
        self.assertFalse(evidence['complete'])
        self.assertNotIn('Private personal content', json.dumps(evidence))
        self.assertIsNone(safe_root('/'))
        self.assertIsNone(safe_root('//server/share'))
        self.assertIsNone(safe_root(str(self.install / 'help-link')))
        self.assertEqual(executable_path('"' + str(self.exe) + '" --token=private'), str(self.exe))
        self.assertEqual(executable_path('powershell.exe\nWrite-Output secret'), '')

    def test_unusable_local_manual_tries_online_but_rate_errors_do_not_retry(self):
        cloud = Mock(); docs = [{'url': 'installation-manual:abc/help', 'text': 'No procedures'}]
        cloud.extract.side_effect = [ValueError('No operations'), {'capabilities': [{'name': 'Write'}], 'limitations': []}]
        cloud.find_sources.return_value = ['https://example.com/manual']
        result = research_app('Word', '', cloud, local_documents=docs, fetcher=lambda u: {'url':u, 'text':'Type text'})
        self.assertEqual(cloud.find_sources.call_count, 1)
        self.assertIn('Installed manuals', result['retrieval_failures'][0])
        cloud.reset_mock(); cloud.extract.side_effect = RuntimeError('HTTP 429')
        with self.assertRaisesRegex(RuntimeError, 'HTTP 429'):
            research_app('Word', '', cloud, local_documents=docs)
        cloud.find_sources.assert_not_called()

    def test_office_start_registration_links_winword_path_without_a_duplicate_app(self):
        snapshot = empty()
        snapshot['apps'] = [{'id': 'start:word', 'name': 'Word', 'version': '16', 'app_id': 'Office.Word',
                             'aliases': ['Word'], 'source': 'start_menu'}]
        probe = dict(self.probe)
        probe['app_paths'] = [{'name': 'WINWORD.EXE', 'executable': str(self.exe)}]
        # Actual executable name and COM namespace often differ.
        onboard_snapshot(snapshot, self.catalog, probe)
        apps = [a for a in self.catalog.apps() if a.get('role') != 'platform']
        self.assertEqual(len(apps), 1)
        self.assertEqual(apps[0]['id'], 'start:word')
        self.assertEqual(apps[0]['executables'], [str(self.exe)])
        self.assertEqual(apps[0]['file_types'], ['.docx'])

    def test_partial_installation_scan_still_detects_changed_primary_binary(self):
        with patch('app_agent.local_inspection.FILE_LIMIT', 1):
            onboard_snapshot(empty(), self.catalog, self.probe)
            current = self.office()
            self.assertFalse(self.catalog.local_evidence(current['id'], 1)['complete'])
            self.exe.write_bytes(self.exe.read_bytes() + b'changed')
            result = onboard_snapshot(empty(), self.catalog, self.probe)
        self.assertIn('Word', result['updated'])
        self.assertEqual(self.office()['generation'], 2)

    def test_independent_new_app_study_runs_real_task_engine_and_keeps_verified_result(self):
        from app_agent.task_director import TaskDirector
        from test_task_director import Desktop, reply
        onboard_snapshot(empty(), self.catalog, windows())
        onboard_snapshot(empty(), self.catalog, self.probe)
        app = self.office(); task = 'Replace the document text with exactly: First Office task.'
        desktop = Desktop(); cloud = Mock()
        cloud.extract.return_value = {'capabilities': [{'name': 'Write', 'steps': ['Type text'], 'expected_result': 'Entered text'}], 'limitations': []}
        def respond(**payload):
            if payload['text']['format'].get('name') == 'personal_task_plan':
                return reply({'steps': [{'app_id': app['id'], 'task': task, 'expected_result': 'First Office task.'}]})
            inputs = json.loads(payload['input'])
            target = inputs['observation']['controls'][0]
            if target['value'] == 'First Office task.':
                return reply({'kind': 'finish', 'reason': 'Observed requested text', 'expected_text': 'First Office task.'})
            return reply({'kind': 'type', 'target': 1, 'automation_id': 'editor', 'target_name': 'Text Editor',
                          'text': 'First Office task.', 'reason': 'Write the requested text'})
        cloud.request.side_effect = respond
        result = TaskDirector(self.catalog, cloud, lambda *args: True, lambda line: None, self.catalog.data_dir,
                              resolve=lambda *args: desktop).run(task)
        self.assertEqual(result['outcome'], 'steps_verified')
        self.assertEqual(desktop.value, 'First Office task.')
        self.assertEqual(len(desktop.actions), 1)
        self.assertEqual(machine_report(self.catalog)['summary']['with_verified_workflows'], 1)
        self.assertEqual(len(self.catalog.workflows(app['id'], 1)), 1)
        cloud.find_sources.assert_not_called()
        # This is an adapter simulation, not a claim that Microsoft Word was
        # installed or operated on this Linux host.

    def test_open_window_structure_informs_research_without_sending_document_text(self):
        from app_agent.machine import observe_running_interfaces, installed_research_options
        onboard_snapshot(empty(), self.catalog, self.probe)
        desktop = Mock(); desktop.windows.return_value = [(8, 'Untitled - Word')]
        desktop.return_value.observe.return_value = {'window_handle': 8, 'process_id': 33,
            'controls': [{'type': 'Edit', 'actions': ['type'], 'name': 'Private title', 'value': 'Private document'},
                         {'type': 'Edit', 'actions': ['type'], 'password': True, 'value': 'secret'}]}
        self.assertEqual(observe_running_interfaces(self.catalog, desktop), ['Word'])
        context = installed_research_options(self.catalog, self.office())['focus']['observed_installation']
        self.assertEqual(context['observed_controls'], [{'type': 'Edit', 'actions': ['type']}])
        self.assertNotIn('Private document', json.dumps(context))
        self.assertNotIn('Private title', json.dumps(context))
        self.assertNotIn('secret', json.dumps(context))
        desktop.return_value.act.assert_not_called()
        desktop.windows.return_value = [(8, 'A - Word'), (9, 'B - Word')]
        self.assertEqual(observe_running_interfaces(self.catalog, desktop), [])

    def test_malformed_pe_file_is_never_loaded(self):
        bad = self.install / 'Bad.exe'; bad.write_bytes(b'MZ')
        self.assertEqual(pe_metadata(bad), {})
