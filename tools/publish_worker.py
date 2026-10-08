"""Prepare a pinned-controller-signed worker release after its tests pass."""
import argparse
import hashlib
import json
from pathlib import Path
import zipfile
from email.parser import Parser
from app_agent.remote_protocol import ControllerKeys, canonical, encode
from app_agent.worker_update import verify_manifest, verify_wheel


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('wheel', type=Path)
    parser.add_argument('--key-file', type=Path, required=True)
    parser.add_argument('--output-dir', type=Path, default=Path('downloads'))
    args = parser.parse_args()
    keys = ControllerKeys.load(args.key_file)
    expected = json.loads(Path('windows/cloud-controller.json').read_text())
    if keys.public() != expected:
        raise ValueError('Release signer does not match the pinned controller.')
    data = args.wheel.read_bytes()
    with zipfile.ZipFile(args.wheel) as archive:
        name = next(n for n in archive.namelist() if n.endswith('.dist-info/METADATA'))
        details = Parser().parsestr(archive.read(name).decode())
    release = {'version': details['Version'], 'minimum_host': '0.7.0', 'protocol': 1,
               'sha256': hashlib.sha256(data).hexdigest(), 'size': len(data)}
    signed = {'release': release, 'signature': encode(keys.signing.sign(canonical(release)))}
    verify_manifest(signed, expected, '0.0.0', '0.7.0')
    verify_wheel(data, release, details)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir/'agent-worker.whl').write_bytes(data)
    (args.output_dir/'worker-release.json').write_text(json.dumps(signed, indent=2)+'\n')
    print('Signed release prepared:', details['Version'], release['sha256'])


if __name__ == '__main__':
    main()
