"""Credential-free automatic checks of disposable native file workflows."""
from pathlib import Path
import threading
import uuid
import zipfile
from .file_tools import safe_path,inventory,verify
from .jobs import Jobs
from .job_runtime import run_next
from .self_test import run_checks


def file_smoke(directory,emit=print,cancel=None):
    cancel=cancel or threading.Event()
    root=safe_path(Path(directory).absolute());root.mkdir(parents=True,exist_ok=True)
    run_dir=root/('file-tests-'+uuid.uuid4().hex);run_dir.mkdir(exist_ok=False)
    source=run_dir/'source';source.mkdir();(source/'empty').mkdir();(source/'nested').mkdir()
    (source/'nested'/'你好.txt').write_bytes('Hello 世界\r\nFile test'.encode());(source/'binary.bin').write_bytes(bytes(range(256))*128)
    (source/'zero.txt').write_bytes(b'')
    data=run_dir/'isolated-agent-data'
    def goal(task):
        jobs=Jobs(data)
        try:identity=jobs.submit(task,autonomous=True)
        finally:jobs.close()
        result=run_next(data,None,lambda *args:not cancel.is_set(),emit,cancel)
        if not result or result['id']!=identity or result['status']!='completed':
            raise RuntimeError('Disposable native file task failed: '+str(result.get('detail') if result else 'No result'))
        return {'status':result['status'],'verified':result['verified']}
    def corrupt_archive():
        if cancel.is_set():raise RuntimeError('File checks cancelled.')
        manifest=inventory(source,'zip_folder');corrupt=run_dir/'deliberately-invalid.zip'
        with zipfile.ZipFile(corrupt,'w') as archive:
            for name in manifest['directories']:archive.writestr(name+'/',b'')
            for item in manifest['files']:archive.writestr(item['name'],b'wrong bytes')
        try:verify(corrupt,'zip_folder',manifest)
        except ValueError:return {'changed_archive_rejected':True}
        raise RuntimeError('File verifier accepted incorrect archived bytes.')
    checks=[('Native single-file copy and SHA-256 verification',lambda:goal(f'Copy file "{source / "binary.bin"}" to "{run_dir / "copied.bin"}" and verify.')),
            ('Native folder copy including Unicode and empty directories',lambda:goal(f'Copy folder "{source}" to new folder "{run_dir / "copied-folder"}" and verify.')),
            ('Native ZIP creation and member verification',lambda:goal(f'Create a ZIP archive of folder "{source}" at "{run_dir / "archive.zip"}" and verify.')),
            ('Incorrect archive is rejected',corrupt_archive)]
    emit('File tests create disposable data only; no desktop interaction or provider calls.')
    return run_checks(checks,run_dir/'report.json',cancel,emit,
        scope='Named native file tests against disposable local data; no desktop/model calls or all-app certification.')
