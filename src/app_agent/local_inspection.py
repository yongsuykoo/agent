"""Read installation evidence without loading binaries or running help commands."""
from collections import deque
import hashlib
import json
import os
from pathlib import Path
import re
import struct
import time

DOC_NAME = re.compile(r'(readme|manual|guide|help|reference|tutorial)', re.I)
SKIP_DIRS = {'node_modules', '.git', '.venv', 'cache', 'logs', 'temp', 'userdata', 'user data', 'profiles'}
FILE_LIMIT = 256
ENTRY_LIMIT = 2048
DOC_BYTES = 128_000


def executable_path(value):
    """Extract only a registered .exe filename, discard its arguments."""
    if not isinstance(value, str) or len(value) > 4096 or any(ord(c) < 32 for c in value):
        return ''
    value = os.path.expandvars(value.strip())
    match = re.match(r'^"([^"\r\n]+\.exe)"(?:\s|$)|^([^"\r\n]+?\.exe)(?:\s|$)', value, re.I)
    return (match.group(1) or match.group(2)) if match else ''


def safe_root(value):
    if not value or not isinstance(value, str) or value.startswith(('\\\\', '//')):
        return None
    path = Path(value)
    # Never follow junctions/symlinks or inspect a drive root as an app folder.
    try:
        if not path.is_absolute() or any(parent.is_symlink() or (hasattr(parent, 'is_junction') and parent.is_junction())
                                         for parent in [path, *path.parents]):
            return None
        if not path.is_dir() or path == Path(path.anchor):
            return None
        return path.resolve()
    except OSError:
        return None


def pe_metadata(path):
    """Bounded PE header/import inspection, including native DLL dependencies."""
    with path.open('rb') as stream:
        def read_at(offset, size):
            if offset < 0 or offset > 1_000_000_000 or size > 65536:
                raise ValueError('Invalid PE offset.')
            stream.seek(offset)
            return stream.read(size)
        dos = read_at(0, 64)
        if len(dos) != 64 or dos[:2] != b'MZ':
            return {}
        offset = struct.unpack_from('<I', dos, 60)[0]
        header = read_at(offset, 24)
        if len(header) != 24 or header[:4] != b'PE\0\0':
            return {}
        machine, sections = struct.unpack_from('<HH', header, 4)
        opt_size = struct.unpack_from('<H', header, 20)[0]
        if sections > 96 or opt_size > 4096:
            return {}
        optional = read_at(offset + 24, opt_size)
        magic = struct.unpack_from('<H', optional)[0]
        directory = 112 if magic == 0x20b else 96 if magic == 0x10b else None
        if directory is None or len(optional) < directory + 16:
            return {}
        section_data = read_at(offset + 24 + opt_size, sections * 40)
        if len(section_data) != sections * 40:
            return {}
        mappings = [struct.unpack_from('<IIII', section_data, i * 40 + 8) for i in range(sections)]
        def mapped(rva):
            for virtual_size, start, raw_size, raw in mappings:
                if start <= rva < start + min(max(virtual_size, raw_size), raw_size):
                    return raw + rva - start
            return None
        import_rva, import_size = struct.unpack_from('<II', optional, directory + 8)
        imports = []
        base = mapped(import_rva) if import_rva and import_size else None
        if base is not None:
            descriptors = read_at(base, min(128 * 20, import_size))
            for i in range(len(descriptors) // 20):
                row = descriptors[i * 20:(i + 1) * 20]
                if row == bytes(20):
                    break
                name_rva = struct.unpack_from('<I', row, 12)[0]
                name_offset = mapped(name_rva)
                if name_offset is not None:
                    name = read_at(name_offset, 256).split(b'\0', 1)[0].decode('ascii', errors='replace')
                    if re.fullmatch(r'[\w.+-]+\.dll', name, re.I):
                        imports.append(name)
        return {'architecture': {0x14c: 'x86', 0x8664: 'x64', 0xaa64: 'arm64'}.get(machine, hex(machine)),
                'imports': sorted(set(imports)), 'import_inspection': 'bounded_static_metadata'}


def inspect_installation(app, previous=None, deadline_seconds=1.0):
    started = time.monotonic()
    roots = []
    for candidate in [app.get('location', ''), *[str(Path(p).parent) for p in app.get('executables', [])]]:
        root = safe_root(candidate)
        if root is not None and root not in roots:
            roots.append(root)
    evidence = {'schema': 1, 'roots': [str(p) for p in roots[:3]], 'files': [], 'manuals': [],
                'binaries': [], 'manifests': [], 'warnings': [], 'complete': True, 'status': 'metadata_only'}
    if not roots:
        evidence['complete'] = False
        evidence['warnings'].append('No accessible installation folder; registrations remain available.')
        return evidence
    files, queue, entries = [], deque((p, p, 0) for p in roots[:3]), 0
    while queue:
        root, folder, depth = queue.popleft()
        if time.monotonic() - started > deadline_seconds or entries >= ENTRY_LIMIT or len(files) >= FILE_LIMIT:
            evidence['complete'] = False
            evidence['warnings'].append('Installation inspection is partial; time or entry allowance reached.')
            break
        try:
            with os.scandir(folder) as children:
                for child in children:
                    entries += 1
                    if entries > ENTRY_LIMIT or time.monotonic() - started > deadline_seconds:
                        evidence['complete'] = False
                        break
                    path = Path(child.path)
                    if child.is_symlink() or (hasattr(path, 'is_junction') and path.is_junction()):
                        continue
                    if child.is_dir(follow_symlinks=False):
                        if child.name.casefold() not in SKIP_DIRS and depth < 3:
                            queue.append((root, path, depth + 1))
                        elif child.name.casefold() not in SKIP_DIRS:
                            evidence['complete'] = False
                        continue
                    extension = path.suffix.lower()
                    kind = ('binary' if extension in ('.exe', '.dll') else
                            'manifest' if extension in ('.manifest', '.config') or path.name.casefold() in ('package.json', 'appxmanifest.xml', 'pyproject.toml') else
                            'manual' if extension in ('.txt', '.md', '.html', '.htm', '.pdf') and DOC_NAME.search(path.stem) else None)
                    if kind and len(files) < FILE_LIMIT:
                        stat = child.stat(follow_symlinks=False)
                        files.append({'root': str(root), 'path': path.relative_to(root).as_posix(),
                                      'size': stat.st_size, 'mtime_ns': stat.st_mtime_ns, 'kind': kind})
                    elif kind:
                        evidence['complete'] = False
        except OSError:
            evidence['complete'] = False
            evidence['warnings'].append('An installation directory is inaccessible.')
    if not evidence['complete'] and not evidence['warnings']:
        evidence['warnings'].append('Inspection covers selected installation files only; directories or entries remain uninspected.')
    evidence['files'] = sorted(files, key=lambda f: (f['root'], f['path']))
    evidence['fingerprint'] = hashlib.sha256(json.dumps(evidence['files'], sort_keys=True).encode()).hexdigest()
    # Reuse static analysis when the inspected file set has not changed. Never
    # confuse this bounded installation fingerprint with a full binary checksum.
    if previous and previous.get('fingerprint') == evidence['fingerprint']:
        for key in ('manuals', 'binaries', 'manifests'):
            evidence[key] = previous.get(key, [])
        evidence['status'] = 'cached_installation'
        return evidence
    explicit = {Path(p).name.casefold() for p in app.get('executables', [])}
    ordered = sorted(evidence['files'], key=lambda f: (f['path'].split('/')[-1].casefold() not in explicit, f['path']))
    for item in ordered:
        if time.monotonic() - started > deadline_seconds:
            evidence['complete'] = False
            break
        path = Path(item['root']) / item['path']
        try:
            if item['kind'] == 'manual' and len(evidence['manuals']) < 3:
                if path.suffix.lower()=='.pdf':
                    from .pdf_documents import MAX_PDF_BYTES
                    from .file_tools import open_read
                    with os.fdopen(open_read(path),'rb') as stream:raw=stream.read(MAX_PDF_BYTES+1)
                    if len(raw)>MAX_PDF_BYTES:raise ValueError('PDF manual exceeds its byte limit.')
                    evidence['manuals'].append({'path':item['path'],'root':item['root'],'format':'pdf',
                        'sha256':hashlib.sha256(raw).hexdigest(),'truncated':False,'status':'pending_extraction'})
                    continue
                with path.open('rb') as stream:
                    raw = stream.read(DOC_BYTES + 1)
                encoding = 'utf-16' if raw[:2] in (b'\xff\xfe', b'\xfe\xff') else 'utf-8-sig'
                text = raw[:DOC_BYTES].decode(encoding, errors='replace')
                if path.suffix.lower() in ('.html', '.htm'):
                    from .research import PageText
                    parser = PageText(); parser.feed(text); text = '\n'.join(parser.parts)
                evidence['manuals'].append({'path': item['path'], 'text': text[:16000],
                    'sha256': hashlib.sha256(raw).hexdigest(), 'truncated': len(raw) > DOC_BYTES or len(text) > 16000})
            elif item['kind'] == 'manifest' and len(evidence['manifests']) < 8:
                with path.open('rb') as stream:
                    raw = stream.read(16384)
                # Contents can include settings/secrets: retain names and hashes
                # only; package.json's public package identity is whitelisted.
                record = {'path': item['path'], 'sample_sha256': hashlib.sha256(raw).hexdigest()}
                if path.name.casefold() == 'package.json':
                    value = json.loads(raw)
                    if isinstance(value, dict):
                        record['package'] = {k: str(value[k])[:200] for k in ('name', 'version') if k in value and isinstance(value[k], str)}
                        if isinstance(value.get('dependencies'), dict):
                            record['dependencies'] = sorted(str(k)[:200] for k in value['dependencies'])[:100]
                evidence['manifests'].append(record)
            elif item['kind'] == 'binary' and len(evidence['binaries']) < 8:
                with path.open('rb') as stream:
                    raw = stream.read(16384)
                evidence['binaries'].append({'path': item['path'], 'sample_sha256': hashlib.sha256(raw).hexdigest(), **pe_metadata(path)})
        except (OSError, ValueError, struct.error):
            evidence['warnings'].append('A selected installation file could not be analyzed: ' + item['path'])
            evidence['complete'] = False
    evidence['status'] = 'installation_observed'
    return evidence
