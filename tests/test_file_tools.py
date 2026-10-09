"""Actual filesystem bytes, ZIP members, durable jobs and process-loss evidence."""
import copy
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import types
import stat
import unittest
from unittest.mock import Mock,patch
import zipfile
from app_agent.catalog import Catalog
from app_agent.file_tools import file_request,prepare,inventory,execute,verify,validate_manifest,read_chunks,safe_path,windows_path,opened_matches_path
from app_agent.file_tasks import run_files
from app_agent.jobs import Jobs
from app_agent.job_runtime import run_next
from app_agent.task_director import TaskDirector
from app_agent.tool_broker import choose_tool
from app_agent.schedules import Schedules
from app_agent.resident import Supervisor


class FileFixture(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        self.source=self.root/'source';self.source.mkdir();(self.source/'empty').mkdir()
        (self.source/'nested').mkdir();(self.source/'nested'/'日本語.txt').write_bytes('Hello 世界\r\nSecond line'.encode())
        (self.source/'binary.bin').write_bytes(bytes(range(256))*8192);(self.source/'zero.txt').write_bytes(b'')
    def tearDown(self):self.temp.cleanup()
    def request(self,kind='copy_folder',destination=None):
        return {'kind':kind,'source':str(self.source/'binary.bin' if kind=='copy_file' else self.source),
                'destination':str(destination or self.root/('archive.zip' if kind=='zip_folder' else 'output.bin' if kind=='copy_file' else 'output'))}
    def run_operation(self,kind):
        request=self.request(kind);manifest=inventory(Path(request['source']),kind);execute(request,manifest)
        return request,manifest,verify(request['destination'],kind,manifest)


class RequestTests(unittest.TestCase):
    def test_windows_local_drive_syntax_rejects_devices_streams_unc_and_reserved_names(self):
        self.assertEqual(str(windows_path(r'D:\photos\日本語.txt')),r'D:\photos\日本語.txt')
        for value in (r'D:relative',r'\\server\share\file',r'\\?\C:\file',r'C:\x:stream',r'C:\NUL.txt',r'C:\COM1',r'C:\a\..\b',r'C:\bad.',r'C:\*.txt'):
            with self.subTest(value=value),self.assertRaises(ValueError):windows_path(value)

    def test_exact_copy_and_archive_requests_keep_literal_windows_paths(self):
        samples=[('Copy file "D:\\photos\\x.png" to "D:\\backup\\x.png".','copy_file'),
                 ('Copy all files from folder "D:\\photos" to new folder "D:\\backup" and verify.','copy_folder'),
                 ('Create a ZIP archive of folder "D:\\photos" at "D:\\backup.zip" and verify the archive.','zip_folder'),
                 ('Compress folder "D:\\photos" into "D:\\backup.zip"','zip_folder')]
        for task,kind in samples:
            with self.subTest(task=task):
                result=file_request(task);self.assertEqual(result['kind'],kind);self.assertTrue(result['source'].startswith('D:\\'))
                self.assertEqual(choose_tool(task,[])['kind'],'files')
    def test_ambiguous_compound_selected_app_and_literal_text_do_not_use_file_tool(self):
        for task in ('Copy all my photos to backup','Copy folder "D:\\a" to folder "D:\\b" and email it',
                     'Replace the document text with exactly: Copy file "D:\\a" to "D:\\b"',
                     'Create a ZIP archive of folder "D:\\a" at "D:\\b.zip" using 7-Zip',
                     'Delete folder "D:\\a"','Move file "D:\\a" to "D:\\b"'):
            with self.subTest(task=task):self.assertEqual(choose_tool(task,[])['kind'],'desktop')
        self.assertEqual(choose_tool('Copy file "D:\\a" to "D:\\b"',[],{'id':'selected'})['kind'],'desktop')


class ArtifactTests(FileFixture):
    def test_windows_creation_and_change_time_difference_does_not_block_unchanged_file(self):
        original=os.fstat
        def changed_ctime(fd):
            info=original(fd)
            return types.SimpleNamespace(**{key:getattr(info,key) for key in dir(info) if key.startswith('st_') and key!='st_ctime_ns'},st_ctime_ns=info.st_ctime_ns+1)
        def windows_binding(before,opened):return opened_matches_path(before,opened,windows=True)
        path=self.source/'binary.bin'
        with patch('app_agent.file_tools.os.fstat',side_effect=changed_ctime),patch('app_agent.file_tools.opened_matches_path',side_effect=windows_binding):
            self.assertEqual(b''.join(read_chunks(path,lambda:None)),path.read_bytes())

    def test_handle_change_time_remains_checked_independently_on_windows(self):
        original=os.fstat;calls=0
        def changed_ctime(fd):
            nonlocal calls
            calls+=1;info=original(fd)
            return types.SimpleNamespace(**{key:getattr(info,key) for key in dir(info) if key.startswith('st_') and key!='st_ctime_ns'},st_ctime_ns=info.st_ctime_ns+calls)
        def windows_binding(before,opened):return opened_matches_path(before,opened,windows=True)
        with patch('app_agent.file_tools.os.fstat',side_effect=changed_ctime),patch('app_agent.file_tools.opened_matches_path',side_effect=windows_binding),self.assertRaisesRegex(ValueError,'while being read'):
            list(read_chunks(self.source/'binary.bin',lambda:None))

    def test_file_binding_rejects_replaced_inode_and_creation_time_on_windows(self):
        info=(self.source/'binary.bin').stat()
        values={key:getattr(info,key) for key in dir(info) if key.startswith('st_')}
        for key in ('st_dev','st_ino','st_size','st_mtime_ns','st_birthtime_ns'):
            changed={**values,key:getattr(info,key,0)+1}
            with self.subTest(key=key):self.assertFalse(opened_matches_path(info,types.SimpleNamespace(**changed),windows=True))

    def test_posix_binding_still_rejects_change_time_mismatch(self):
        info=(self.source/'binary.bin').stat()
        values={key:getattr(info,key) for key in dir(info) if key.startswith('st_')}
        values['st_ctime_ns']+=1
        self.assertFalse(opened_matches_path(info,types.SimpleNamespace(**values),windows=False))

    def test_real_copy_folder_preserves_all_bytes_unicode_zero_length_and_empty_directories(self):
        request,manifest,proof=self.run_operation('copy_folder')
        self.assertEqual(inventory(Path(request['destination']),'copy_folder'),manifest)
        self.assertTrue((Path(request['destination'])/'empty').is_dir());self.assertEqual(proof['entries'],5)
        self.assertEqual((self.source/'binary.bin').read_bytes(),(Path(request['destination'])/'binary.bin').read_bytes())
    def test_single_file_copy_allows_new_name_and_checks_sha256(self):
        request,manifest,proof=self.run_operation('copy_file')
        self.assertEqual(proof['sha256'],hashlib.sha256((self.source/'binary.bin').read_bytes()).hexdigest())
        self.assertEqual(proof['size'],2*1024*1024);self.assertEqual(proof['entries'],1)
    def test_real_archive_is_readable_by_independent_zip_reader(self):
        request,manifest,proof=self.run_operation('zip_folder')
        with zipfile.ZipFile(request['destination']) as archive:
            self.assertIsNone(archive.testzip());self.assertIn('empty/',archive.namelist())
            for item in manifest['files']:self.assertEqual(archive.read(item['name']),(self.source/item['name']).read_bytes())
        self.assertEqual(proof['sha256'],hashlib.sha256(Path(request['destination']).read_bytes()).hexdigest())
    def test_empty_folder_is_not_false_failure_and_has_verifiable_empty_archive(self):
        for kind in ('copy_folder','zip_folder'):
            request=self.request(kind);request['source']=str(self.source/'empty')
            manifest=inventory(Path(request['source']),kind);execute(request,manifest)
            self.assertEqual(verify(request['destination'],kind,manifest)['entries'],0)
    def test_changed_copied_bytes_and_unexpected_files_are_rejected(self):
        request,manifest,_=self.run_operation('copy_folder');output=Path(request['destination'])
        (output/'extra.txt').write_text('extra')
        with self.assertRaises(ValueError):verify(output,'copy_folder',manifest)
        (output/'extra.txt').unlink();(output/'zero.txt').write_text('changed')
        with self.assertRaises(ValueError):verify(output,'copy_folder',manifest)
    def test_missing_empty_directory_is_rejected(self):
        request,manifest,_=self.run_operation('copy_folder');output=Path(request['destination'])
        (output/'empty').rmdir()
        with self.assertRaises(ValueError):verify(output,'copy_folder',manifest)
    def test_archive_with_forged_content_duplicate_or_extra_members_is_rejected(self):
        manifest=inventory(self.source,'zip_folder');output=self.root/'forged.zip'
        for defect in ('changed','extra','duplicate','missing'):
            with zipfile.ZipFile(output,'w') as archive:
                for name in manifest['directories']:archive.writestr(name+'/',b'')
                for index,item in enumerate(manifest['files']):
                    if defect=='missing' and index==0:continue
                    data=(self.source/item['name']).read_bytes()
                    if defect=='changed' and index==0:data=b'X'+data[1:]
                    archive.writestr(item['name'],data)
                if defect=='extra':archive.writestr('extra.txt',b'extra')
                if defect=='duplicate':
                    import warnings
                    with warnings.catch_warnings():warnings.simplefilter('ignore');archive.writestr(manifest['files'][0]['name'],b'')
            with self.subTest(defect=defect),self.assertRaises(ValueError):verify(output,'zip_folder',manifest)
    def test_archive_replaced_after_member_verification_cannot_be_reported_as_verified(self):
        request,manifest,_=self.run_operation('zip_folder');original=__import__('app_agent.file_tools',fromlist=['digest']).digest
        def change(path,guard):
            Path(path).write_bytes(b'not the verified archive');return original(path,guard)
        with patch('app_agent.file_tools.digest',side_effect=change),self.assertRaises(ValueError):verify(request['destination'],'zip_folder',manifest)
    def test_no_overwrite_missing_parent_or_output_inside_source(self):
        output=self.root/'already';output.write_bytes(b'keep')
        for request in (self.request(destination=output),self.request(destination=self.source/'new'),self.request(destination=self.root/'missing'/'new')):
            with self.subTest(request=request),self.assertRaises((ValueError,FileExistsError)):prepare(request)
        self.assertEqual(output.read_bytes(),b'keep');self.assertFalse((self.source/'new').exists())
    def test_source_changes_after_inventory_are_detected_with_partial_output_retained(self):
        request=self.request('copy_file');manifest=inventory(Path(request['source']),'copy_file')
        Path(request['source']).write_bytes(b'changed')
        with self.assertRaises(ValueError):execute(request,manifest)
        self.assertTrue(Path(request['destination']).exists())
        with self.assertRaises(ValueError):verify(request['destination'],'copy_file',manifest)
    def test_file_changes_during_read_fail_even_when_same_size(self):
        path=self.source/'binary.bin';changed=False
        def guard():
            nonlocal changed
            if not changed:
                changed=True
                with path.open('r+b') as stream:stream.write(b'changed!')
        with self.assertRaises(ValueError):list(read_chunks(path,guard))
    def test_new_source_entry_during_copy_prevents_success(self):
        request=self.request();manifest=inventory(self.source,'copy_folder');original=read_chunks;changed=False
        def altered(path,guard):
            nonlocal changed
            yield from original(path,guard)
            if not changed:changed=True;(self.source/'late.txt').write_bytes(b'late')
        with patch('app_agent.file_tools.read_chunks',side_effect=altered),self.assertRaises(ValueError):execute(request,manifest)
    def test_links_in_source_and_destination_ancestors_are_rejected(self):
        try:(self.source/'linked').symlink_to(self.root/'target')
        except (OSError,NotImplementedError):self.skipTest('This Windows account cannot create symlinks.')
        with self.assertRaises(ValueError):inventory(self.source,'copy_folder')
        (self.source/'linked').unlink();link=self.root/'parent-link';link.symlink_to(self.source,target_is_directory=True)
        with self.assertRaises(ValueError):prepare(self.request(destination=link/'new'))
    def test_relative_paths_parent_traversal_and_wrong_archive_extension_are_rejected(self):
        for value in ('relative/file',str(self.root/'..'/'outside')):
            with self.assertRaises(ValueError):safe_path(value)
        with self.assertRaises(ValueError):prepare(self.request('zip_folder',self.root/'not-zip.txt'))
    def test_windows_reparse_attribute_is_rejected_even_without_symlink_mode(self):
        info=types.SimpleNamespace(st_mode=stat.S_IFDIR,st_file_attributes=0x400)
        with patch.object(Path,'lstat',return_value=info),self.assertRaises(ValueError):safe_path(self.root/'junction')
    def test_entry_and_byte_bounds_prevent_creation(self):
        with patch('app_agent.file_tools.MAX_ENTRIES',1),self.assertRaises(ValueError):inventory(self.source,'copy_folder')
        with patch('app_agent.file_tools.MAX_BYTES',1),self.assertRaises(ValueError):inventory(self.source,'copy_folder')
        self.assertFalse((self.root/'output').exists())
    def test_inventory_rejects_traversal_duplicates_missing_parents_and_forged_hashes(self):
        manifest=inventory(self.source,'copy_folder')
        for name in ('../outside','/outside','a\\b','a:b','nested/../escape'):
            forged=copy.deepcopy(manifest);forged['files'][0]['name']=name
            with self.subTest(name=name),self.assertRaises(ValueError):execute(self.request(),forged)
        for alter in (lambda m:m['files'].append(m['files'][0]),lambda m:m.update(directories=[]),lambda m:m['files'][0].update(sha256='bad'),lambda m:m['files'][0].update(size=True)):
            forged=copy.deepcopy(manifest);alter(forged)
            with self.assertRaises(ValueError):validate_manifest(forged,'copy_folder')
        self.assertFalse((self.root/'output').exists())
    def test_case_colliding_names_are_rejected_on_case_sensitive_hosts(self):
        (self.source/'same').write_text('one')
        if (self.source/'SAME').exists():return
        (self.source/'SAME').write_text('two')
        with self.assertRaises(ValueError):inventory(self.source,'copy_folder')


class RuntimeTests(FileFixture):
    def setUp(self):
        super().setUp();self.data=self.root/'agent-data';self.catalog=Catalog(self.data);self.jobs=Jobs(self.data);self.cloud=Mock()
        self.cloud.request.side_effect=AssertionError('File tasks must not use provider calls')
        self.task=f'Copy folder "{self.source}" to new folder "{self.root / "output"}" and verify.'
    def tearDown(self):self.jobs.close();self.catalog.close();super().tearDown()
    def test_real_durable_goal_needs_no_installed_app_or_model(self):
        identity=self.jobs.submit(self.task,autonomous=True)
        result=run_next(self.data,self.cloud,lambda *args:True,lambda _:None,resolve=Mock(side_effect=AssertionError('No desktop should launch')))
        self.assertEqual(result['status'],'completed');self.assertEqual(result['id'],identity);self.assertEqual(len(result['verified']),1)
        self.cloud.request.assert_not_called();self.assertEqual(self.jobs.get(identity)['plan']['tool'],'files')
    def test_permission_rejection_happens_before_any_source_inventory(self):
        director=TaskDirector(self.catalog,self.cloud,lambda *args:False,lambda _:None,self.data)
        with patch('app_agent.file_tasks.inventory') as inspect:
            result=director.run(self.task);inspect.assert_not_called()
        self.assertEqual(result['outcome'],'blocked');self.assertFalse((self.root/'output').exists())
    def test_global_stop_between_files_fences_output_and_retains_uncertainty(self):
        identity=self.jobs.submit(self.task,autonomous=True);original=__import__('app_agent.file_tasks',fromlist=['execute']).execute
        def stopping(request,manifest,guard):
            def halt():self.jobs.pause();guard()
            original(request,manifest,halt)
        with patch('app_agent.file_tasks.execute',side_effect=stopping):result=run_next(self.data,self.cloud,lambda *args:True,lambda _:None)
        self.assertEqual(result['status'],'needs_review');self.jobs.resume();self.assertFalse(self.jobs.ready())
        self.assertEqual(self.jobs.get(identity)['status'],'needs_review')
    def test_verified_restart_rechecks_existing_bytes_without_recopying_source(self):
        identity=self.jobs.submit(self.task,autonomous=True);checkpoint=self.jobs.claim(identity)
        director=TaskDirector(self.catalog,self.cloud,lambda *args:True,lambda _:None,self.data,checkpoint=checkpoint)
        self.assertEqual(director.run(self.task)['outcome'],'artifacts_verified')
        with self.jobs.db:self.jobs.db.execute('UPDATE jobs SET owner_pid=-1,lease=0 WHERE id=?',(identity,))
        with patch('app_agent.file_tasks.execute',side_effect=AssertionError('Verified output must not be copied again')):
            result=run_next(self.data,self.cloud,lambda *args:True,lambda _:None)
        self.assertEqual(result['status'],'completed');self.assertEqual(result['attempts'],2)
    def test_upgrade_from_unused_desktop_plan_can_select_native_file_tool(self):
        identity=self.jobs.submit(self.task,autonomous=True);checkpoint=self.jobs.claim(identity)
        checkpoint.save_plan({'steps':[{'app_id':'old:explorer'}],'tool':'desktop'})
        with self.jobs.db:self.jobs.db.execute('UPDATE jobs SET lease=0 WHERE id=?',(identity,))
        result=run_next(self.data,self.cloud,lambda *args:True,lambda _:None)
        self.assertEqual(result['status'],'completed');self.assertEqual(result['plan']['tool'],'files')
    def test_upgrade_after_previous_verified_step_cannot_replace_the_saved_plan(self):
        identity=self.jobs.submit(self.task,autonomous=True);checkpoint=self.jobs.claim(identity)
        checkpoint.save_plan({'steps':[{'app_id':'old:explorer'}],'tool':'desktop'});checkpoint.verified('old output',{'old':True})
        with self.jobs.db:self.jobs.db.execute('UPDATE jobs SET lease=0 WHERE id=?',(identity,))
        result=run_next(self.data,self.cloud,lambda *args:True,lambda _:None)
        self.assertEqual(result['status'],'failed');self.assertFalse((self.root/'output').exists());self.assertEqual(result['verified'],['old output'])
    def test_changed_verified_output_cannot_be_completed_or_recreated_after_restart(self):
        identity=self.jobs.submit(self.task,autonomous=True);checkpoint=self.jobs.claim(identity)
        director=TaskDirector(self.catalog,self.cloud,lambda *args:True,lambda _:None,self.data,checkpoint=checkpoint)
        director.run(self.task);(self.root/'output'/'zero.txt').write_bytes(b'changed')
        with self.jobs.db:self.jobs.db.execute('UPDATE jobs SET owner_pid=-1,lease=0 WHERE id=?',(identity,))
        with patch('app_agent.file_tasks.execute',side_effect=AssertionError('No recreation')):result=run_next(self.data,self.cloud,lambda *args:True,lambda _:None)
        self.assertEqual(result['status'],'failed');self.assertEqual((self.root/'output'/'zero.txt').read_bytes(),b'changed')
    def test_actual_process_exit_after_dispatch_leaves_review_and_no_duplicate(self):
        identity=self.jobs.submit(self.task,autonomous=True)
        script="""import os,sys
from app_agent.catalog import Catalog
from app_agent.jobs import Jobs
from app_agent.task_director import TaskDirector
data,identity=sys.argv[1:];jobs=Jobs(data);checkpoint=jobs.claim(identity)
checkpoint.verified=lambda value,record:os._exit(24)
director=TaskDirector(Catalog(data),None,lambda *args:True,lambda _:None,data,checkpoint=checkpoint)
director.run(jobs.get(identity)['task'])
"""
        process=subprocess.run([sys.executable,'-c',script,str(self.data),identity],timeout=20)
        self.assertEqual(process.returncode,24);self.assertTrue((self.root/'output'/'binary.bin').is_file())
        self.assertIsNone(run_next(self.data,self.cloud,lambda *args:True,lambda _:None))
        self.assertEqual(self.jobs.get(identity)['status'],'needs_review')
    def test_resident_runs_real_file_goal_without_credentials(self):
        identity=self.jobs.submit(self.task,autonomous=True)
        worker=Supervisor(self.data,lambda _:None,available=lambda:True,idle=lambda:10,key_reader=lambda _:None,scanner=lambda *args,**kwargs:None,presence=lambda _:False)
        with patch('app_agent.resident.CloudResearcher',side_effect=AssertionError('No provider')):result=worker.step()
        self.assertEqual(result['id'],identity);self.assertEqual(result['status'],'completed')
    def test_schedule_enqueues_exact_file_goal_and_verified_occurrence_completes(self):
        schedules=Schedules(self.data)
        try:
            identity=schedules.create(self.task,at=0,autonomous=True);schedules.tick()
            result=run_next(self.data,self.cloud,lambda *args:True,lambda _:None)
            self.assertEqual(result['status'],'completed');schedules.tick();self.assertEqual(schedules.get(identity)['state'],'completed')
        finally:schedules.close()
    def test_existing_destination_race_is_not_overwritten_and_does_not_replay(self):
        self.jobs.submit(self.task,autonomous=True);original=__import__('app_agent.file_tasks',fromlist=['execute']).execute
        def collision(request,manifest,guard):
            Path(request['destination']).mkdir();(Path(request['destination'])/'keep').write_text('keep');original(request,manifest,guard)
        with patch('app_agent.file_tasks.execute',side_effect=collision):result=run_next(self.data,self.cloud,lambda *args:True,lambda _:None)
        self.assertEqual(result['status'],'needs_review');self.assertEqual((self.root/'output'/'keep').read_text(),'keep')

    def test_automatic_file_checks_execute_and_save_four_native_results(self):
        from app_agent.file_checks import file_smoke
        report=file_smoke(self.data,lambda _:None)
        self.assertEqual(report['status'],'passed');self.assertEqual(report['counts']['passed'],4)
        self.assertTrue(Path(report['report_path']).is_file());self.assertEqual(len(report['checks']),4)
        self.assertEqual(json.loads(Path(report['report_path']).read_text()),report)
        self.assertTrue(report['checks'][-1]['details']['changed_archive_rejected'])

    def test_automatic_file_checks_cancel_without_task_execution(self):
        from app_agent.file_checks import file_smoke
        cancel=threading.Event();cancel.set();report=file_smoke(self.data,lambda _:None,cancel)
        self.assertEqual(report['counts']['cancelled'],4);self.assertEqual(report['counts']['passed'],0)



if __name__=='__main__':unittest.main()
