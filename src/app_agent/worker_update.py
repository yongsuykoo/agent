"""Signed, fixed-source worker updates without reinstalling the active helper."""
import hashlib
import io
import json
from importlib.metadata import metadata, version
from pathlib import Path
import re
import subprocess
import threading
import time
from urllib.request import Request, build_opener
import zipfile
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from .remote_protocol import canonical, decode
from .research import NoRedirects
from .worker_process import command, run_worker

BASE = 'https://raw.githubusercontent.com/yongsuykoo/agent/main/downloads/'
MANIFEST_URL = BASE + 'worker-release.json'
WHEEL_URL = BASE + 'agent-worker.whl'
MAX_WHEEL = 2_000_000


def release_number(value):
    if not isinstance(value, str) or not re.fullmatch(r'\d+\.\d+\.\d+', value):
        raise ValueError('Invalid release version.')
    return tuple(int(i) for i in value.split('.'))


def download(url, limit):
    if url not in (MANIFEST_URL, WHEEL_URL):
        raise ValueError('Only the fixed project release sources are permitted.')
    with build_opener(NoRedirects()).open(Request(url, headers={'User-Agent': 'AppAgent-Updater/0.7'}), timeout=30) as response:
        data = response.read(limit + 1)
        if len(data) > limit:
            raise ValueError('Update artifact exceeds its size limit.')
        return data


def verify_manifest(value, public, current, host):
    if not isinstance(value, dict) or set(value) != {'release', 'signature'}:
        raise ValueError('Invalid signed release.')
    release = value['release']
    if not isinstance(release, dict) or set(release) != {'version', 'minimum_host', 'protocol', 'sha256', 'size'}:
        raise ValueError('Invalid release metadata.')
    Ed25519PublicKey.from_public_bytes(decode(public['signing_key'], 32)).verify(decode(value['signature'], 64), canonical(release))
    if type(release['protocol']) is not int or release['protocol'] != 1:
        raise ValueError('Worker protocol requires a host upgrade.')
    if release_number(release['minimum_host']) > release_number(host):
        raise ValueError('Worker requires a newer connection host.')
    if type(release['size']) is not int or not 1 <= release['size'] <= MAX_WHEEL or not re.fullmatch(r'[0-9a-f]{64}', release['sha256']):
        raise ValueError('Invalid artifact identity.')
    return release if release_number(release['version']) > release_number(current) else None


def verify_wheel(data, release, baseline_metadata):
    if len(data) != release['size'] or hashlib.sha256(data).hexdigest() != release['sha256']:
        raise ValueError('Worker checksum mismatch; current worker retained.')
    from email.parser import Parser
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        names = archive.namelist()
        if len(names) != len(set(names)) or sum(i.file_size for i in archive.infolist()) > 12_000_000:
            raise ValueError('Invalid worker archive size or duplicate entries.')
        if any('..' in Path(name).parts or name.startswith(('/', '\\')) or '\\' in name for name in names):
            raise ValueError('Invalid worker archive path.')
        metas = [n for n in names if n.endswith('.dist-info/METADATA')]
        if len(metas) != 1 or not any(n == 'app_agent/worker_process.py' for n in names):
            raise ValueError('Worker entry point or metadata is missing.')
        details = Parser().parsestr(archive.read(metas[0]).decode('utf-8'))
        if details['Name'] != 'app-agent' or details['Version'] != release['version']:
            raise ValueError('Worker package identity mismatch.')
        if details.get('Requires-Python') != baseline_metadata.get('Requires-Python') or sorted(details.get_all('Requires-Dist', [])) != sorted(baseline_metadata.get_all('Requires-Dist', [])):
            raise ValueError('Dependency changes require a host setup update; current worker retained.')
        if archive.testzip() is not None:
            raise ValueError('Worker archive integrity failed.')


class WorkerUpdates:
    def __init__(self, directory, public, enabled=True, fetch=download, host_version=None):
        self.directory = Path(directory) / 'worker-updates'
        self.public, self.enabled, self.fetch = public, enabled, fetch
        self.host_version = host_version or version('app-agent')
        self.version, self.wheel = self.host_version, None
        self.next_check = 0
        self.lock = threading.Lock()
        self.baseline = metadata('app-agent')

    def check(self, emit):
        if not self.enabled or time.monotonic() < self.next_check:
            return
        self.next_check = time.monotonic() + 300
        try:
            release = verify_manifest(json.loads(self.fetch(MANIFEST_URL, 16384)), self.public, self.version, self.host_version)
            if release is None:
                return
            data = self.fetch(WHEEL_URL, MAX_WHEEL)
            verify_wheel(data, release, self.baseline)
            self.directory.mkdir(parents=True, exist_ok=True)
            candidate = self.directory / ('app_agent-' + release['version'] + '-' + release['sha256'] + '.whl')
            candidate.write_bytes(data)
            result = subprocess.run(command(candidate, preflight=True), capture_output=True, text=True, timeout=30)
            if result.returncode or result.stdout.strip() != 'worker-ready':
                candidate.unlink(missing_ok=True)
                raise RuntimeError('Worker preflight failed; current worker retained.')
            # This switch happens only between serialized jobs. The active relay,
            # signing identity, grants and credentials remain in the parent.
            self.wheel, self.version = candidate, release['version']
            emit('Verified worker update activated: ' + self.version + '. Connection retained.')
        except Exception as error:
            emit('Automatic update deferred: ' + type(error).__name__ + '. Current worker retained; retry in five minutes.')

    def execute(self, job, directory, cancel, emit, permission=None):
        with self.lock:
            if cancel.is_set():
                raise RuntimeError('Connection stopped.')
            self.check(emit)
            if cancel.is_set():
                raise RuntimeError('Connection stopped.')
            if self.wheel:
                return run_worker(self.wheel, job, directory, cancel, emit, permission)
            from .remote_bridge import execute_job
            return execute_job(job, directory, cancel, emit, permission)
