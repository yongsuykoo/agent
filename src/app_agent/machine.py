"""Automatic local onboarding and versioned evidence for the installed machine."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re

from .local_inspection import executable_path, inspect_installation, safe_root


def _under(executable, location):
    root = safe_root(location)
    if root is None:
        return False
    try:
        return Path(executable).resolve().is_relative_to(root)
    except (OSError, ValueError):
        return False


def _file_types(probe, progids):
    families = {p.split('.')[0].casefold() for p in progids}
    return sorted({str(p.get('extension', ''))[:40] for p in probe.get('file_types', [])
                   if isinstance(p.get('progid'), str) and p['progid'].split('.')[0].casefold() in families})[:100]


def enrich_inventory(snapshot, probe):
    apps = [dict(a) for a in snapshot['apps']]
    paths = []
    for row in probe.get('app_paths', []):
        exe = executable_path(row.get('executable'))
        if exe:
            paths.append({'executable': exe, 'name': Path(exe).stem, 'registration': str(row.get('name', ''))[:200]})
    servers = []
    for row in probe.get('com_servers', []):
        exe = executable_path(row.get('server'))
        if exe and isinstance(row.get('progid'), str):
            servers.append({'executable': exe, 'progid': row['progid'][:200], 'clsid': str(row.get('clsid', ''))[:80]})
    used = set()
    for app in apps:
        registered_exes = {p.casefold() for p in app.get('executables', []) if isinstance(p, str)}
        names = {name.casefold() for name in app.get('aliases', [app['name']])}
        own = [p for p in paths if p['name'].casefold() in names or p['executable'].casefold() in registered_exes or _under(p['executable'], app.get('location', ''))]
        own_servers = [p for p in servers if p['progid'].split('.')[0].casefold() in names or p['executable'].casefold() in registered_exes or _under(p['executable'], app.get('location', ''))]
        executables = list(dict.fromkeys([*app.get('executables', []), *[p['executable'] for p in own], *[p['executable'] for p in own_servers]]))[:16]
        app['executables'] = executables
        if not app.get('location') and executables:
            app['location'] = str(Path(executables[0]).parent)
        launchers = [p for p in own if p['name'].casefold() in names] or (own if len(own) == 1 else [])
        if not app.get('app_id') and len(launchers) == 1:
            app['launch_executable'] = launchers[0]['executable']
            app['launch_source'] = 'app_paths'
        app['automation_registrations'] = [{k:v for k,v in p.items() if k != 'executable'} for p in own_servers][:100]
        progids = {p['progid'] for p in own_servers}
        app['file_types'] = _file_types(probe, progids)
        used.update(p.casefold() for p in executables)
    for entry in paths:
        if entry['executable'].casefold() in used:
            continue
        identity = 'app_paths:' + hashlib.sha256(entry['executable'].casefold().encode()).hexdigest()[:24]
        own_servers = [p for p in servers if p['executable'].casefold() == entry['executable'].casefold()]
        progids = {p['progid'] for p in own_servers}
        apps.append({'id': identity, 'name': entry['name'], 'aliases': [entry['name']], 'version': '',
                     'source': 'app_paths', 'app_id': '', 'publisher': '', 'location': str(Path(entry['executable']).parent),
                     'executables': [entry['executable']], 'launch_executable': entry['executable'], 'launch_source': 'app_paths',
                     'automation_registrations': [{k:v for k,v in p.items() if k != 'executable'} for p in own_servers][:100],
                     'file_types': _file_types(probe, progids)})
        used.add(entry['executable'].casefold())
    os = probe.get('os', {})
    complete = set(snapshot.get('complete_sources', []))
    if not any('App Paths' in w for w in probe.get('warnings', [])):
        complete.add('app_paths')
    if os.get('build'):
        apps.append({'id': 'system:windows', 'name': 'Microsoft Windows', 'role': 'platform', 'source': 'windows_system',
                     'version': str(os['build']), 'publisher': 'Microsoft', 'app_id': '', 'location': '',
                     'aliases': ['Windows'], 'help_url': 'https://learn.microsoft.com/windows/'})
        complete.add('windows_system')
    return {**snapshot, 'apps': apps, 'complete_sources': sorted(complete),
            'warnings': sorted(set(snapshot.get('warnings', []) + probe.get('warnings', [])))}


def onboard_snapshot(snapshot, catalog, probe, cancel=None):
    """Local stage has no provider calls or daily cap. Owner commits all SQLite."""
    enriched = enrich_inventory(snapshot, probe)
    jobs = []
    for app in enriched['apps']:
        if app.get('role') == 'platform':
            continue
        try:
            previous_app = catalog.get(app['id'])
            previous = catalog.local_evidence(app['id'], previous_app['generation'])
        except KeyError:
            previous = None
        jobs.append((app, previous))
    def inspect(job):
        app, previous = job
        if cancel is not None and cancel.is_set():
            return app['id'], None
        evidence = inspect_installation(app, previous)
        # A small, stable set of already observed primary files is checked even
        # when a large installation cannot be fully enumerated in one pass.
        watched = []
        candidates = list(app.get('executables', [])) + [str(Path(p['root']) / p['path']) for p in (previous or evidence).get('files', [])[:16]]
        for name in dict.fromkeys(candidates):
            path = Path(name)
            if safe_root(str(path.parent)) is None or path.is_symlink():
                continue
            try:
                stat = path.stat()
                with path.open('rb') as stream:
                    sample = stream.read(4096)
                    if stat.st_size > 4096:
                        stream.seek(max(4096, stat.st_size - 4096)); sample += stream.read(4096)
                watched.append({'path': str(path), 'size': stat.st_size, 'mtime_ns': stat.st_mtime_ns,
                                'sample_sha256': hashlib.sha256(sample).hexdigest()})
            except OSError:
                # Missing previously observed primary files also change identity.
                watched.append({'path': str(path), 'missing': True})
        evidence['identity_fingerprint'] = hashlib.sha256(json.dumps({'watched': watched,
            'automation': app.get('automation_registrations', []), 'file_types': app.get('file_types', [])}, sort_keys=True).encode()).hexdigest() if watched or app.get('automation_registrations') else None
        if previous and evidence.get('status') == 'cached_installation' and previous.get('identity_fingerprint') != evidence['identity_fingerprint']:
            refreshed = inspect_installation(app)
            refreshed['identity_fingerprint'] = evidence['identity_fingerprint']
            evidence = refreshed
        return app['id'], evidence
    evidence = {}
    with ThreadPoolExecutor(max_workers=4, thread_name_prefix='installation-probe') as pool:
        for identity, item in pool.map(inspect, jobs):
            if item is not None:
                evidence[identity] = item
    if cancel is not None and cancel.is_set():
        return {'status': 'cancelled', 'new': [], 'updated': [], 'removed': [], 'warnings': []}
    system = {'schema': 1, 'observed_at': datetime.now(timezone.utc).isoformat(), 'os': probe.get('os', {}),
              'services': probe.get('services', []), 'warnings': enriched['warnings'],
              'inspection': 'read_only_metadata', 'history_accessed': False,
              'limitations': ['Installation inspection is bounded and may be partial.',
                             'Registrations and static files do not prove that an operation works.',
                             'Windows build, service and registration metadata are not a complete operating-system blueprint.']}
    changes = catalog.sync({**enriched, 'machine': system, 'local_evidence': evidence})
    import tempfile
    with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', suffix='.tmp', dir=catalog.data_dir, delete=False) as stream:
        temporary = Path(stream.name)
        json.dump(machine_report(catalog), stream, indent=2)
    try:
        temporary.replace(catalog.data_dir / 'machine-report.json')
    finally:
        temporary.unlink(missing_ok=True)
    return changes


def scan_machine(catalog, cancel=None, scanner=None, probe=None, desktop=None):
    if scanner is None:
        from .discovery import scan_apps
        scanner = scan_apps
    if cancel is not None and cancel.is_set():
        return {'status': 'cancelled', 'new': [], 'updated': [], 'removed': [], 'warnings': []}
    snapshot = scanner()
    try:
        if probe is None:
            from .windows_probe import probe_windows
            probe = probe_windows()
        result = onboard_snapshot(snapshot, catalog, probe, cancel)
        if desktop is not None and result.get('status') != 'cancelled':
            observe_running_interfaces(catalog, desktop, cancel)
        return result
    except (OSError, RuntimeError, ValueError) as error:
        # Discovery remains usable when system metadata is inaccessible; retain
        # the previous OS/evidence rather than falsely removing everything.
        if cancel is not None and cancel.is_set():
            return {'status': 'cancelled', 'new': [], 'updated': [], 'removed': [], 'warnings': []}
        snapshot['warnings'] = snapshot.get('warnings', []) + ['Machine inspection deferred: ' + str(error)[:300]]
        return catalog.sync(snapshot)


def research_context(catalog, app):
    evidence = catalog.local_evidence(app['id'], app['generation']) or {}
    context = {'installation': {k:evidence[k] for k in ('status', 'complete', 'warnings') if k in evidence},
               'binary_interfaces': [{'architecture': b.get('architecture'), 'imports': b.get('imports', [])[:20]} for b in evidence.get('binaries', [])[:8]],
               'automation_registrations': app.get('automation_registrations', [])[:30], 'file_types': app.get('file_types', [])[:30]}
    interface = catalog.interface(app['id'], app['generation'])
    if interface:
        context['observed_controls'] = [{'type': c.get('type'), 'actions': c.get('actions', [])} for c in interface.get('controls', [])[:100] if not c.get('password')]
    if app.get('role') == 'platform':
        model = catalog.setting('machine_model', {})
        context['windows'] = model.get('os', {})
        context['service_types'] = sorted({str(s.get('start_type', '')) for s in model.get('services', [])})
    # No installation paths, settings contents or arbitrary binary strings go to
    # the provider. Installed manuals are explicit untrusted source evidence.
    documents = [{'url': 'installation-manual:' + m['sha256'] + '/' + m['path'], 'text': m['text'],
                  'sha256': m['sha256'], 'retrieved_at': evidence.get('observed_at', ''), 'truncated': m['truncated']}
                 for m in evidence.get('manuals', [])]
    return context, documents


def machine_report(catalog):
    apps = catalog.apps()
    entries = []
    for app in apps:
        evidence = catalog.local_evidence(app['id'], app['generation'])
        coverage = catalog.coverage(app['id'], app['generation'])
        workflows = catalog.db.execute("SELECT COUNT(*) FROM workflows WHERE app_id=? AND generation=? AND outcome='result_observed'", (app['id'], app['generation'])).fetchone()[0]
        entries.append({'app_id': app['id'], 'name': app['name'], 'version': app.get('version', ''),
                        'generation': app['generation'], 'role': app.get('role', 'application'),
                        'launchable': bool(app.get('app_id') or app.get('launch_executable')),
                        'inspection': evidence.get('status') if evidence else 'system_metadata_observed' if app.get('role') == 'platform' else 'not_inspected',
                        'inspection_complete': evidence.get('complete', False) if evidence else False,
                        'local_manuals': len((evidence or {}).get('manuals', [])),
                        'automation_interfaces': [r['progid'] for r in app.get('automation_registrations', [])],
                        'file_types': app.get('file_types', []), 'knowledge': app['status'],
                        'observed_capabilities': sum(c['observed_runs'] > 0 for c in coverage), 'verified_workflows': workflows,
                        'warnings': (evidence or {}).get('warnings', [])})
    result = {'machine': catalog.setting('machine_model', {}), 'apps': entries,
              'summary': {'entries': len(entries), 'locally_inspected': sum(bool(catalog.local_evidence(a['id'], a['generation'])) for a in apps),
                          'documented': sum(bool(a['blueprint']) for a in apps),
                          'with_observed_capabilities': sum(e['observed_capabilities'] > 0 for e in entries),
                          'with_verified_workflows': sum(e['verified_workflows'] > 0 for e in entries)},
              'universal_mastery_verified': False}
    return result


def installed_research_options(catalog, app):
    if not catalog.local_evidence(app['id'], app['generation']) and app.get('role') != 'platform' and not app.get('automation_registrations'):
        return {}
    context, documents = research_context(catalog, app)
    options = {'focus': {'observed_installation': context,
                         'rule': 'Registrations/imports are interface candidates, not proof of supported or verified operations.'}}
    if documents:
        options['local_documents'] = documents
    return options


def observe_running_interfaces(catalog, desktop, cancel=None):
    """Read already open, uniquely matched windows; never launch/focus/type."""
    from .routing import window_matches
    saved = []
    try:
        windows = desktop.windows()
    except (RuntimeError, OSError):
        return saved
    for app in catalog.apps():
        if cancel is not None and cancel.is_set():
            break
        if app.get('role') == 'platform':
            continue
        matches = window_matches(app, windows)
        if len(matches) != 1:
            continue
        try:
            snapshot = desktop(matches[0][0]).observe()
            if not isinstance(snapshot, dict) or snapshot.get('window_handle') != matches[0][0] or type(snapshot.get('process_id')) is not int or snapshot['process_id'] <= 0:
                continue
            if catalog.get(app['id'])['generation'] != app['generation']:
                continue
            catalog.save_interface(app['id'], app['generation'], snapshot)
            saved.append(app['name'])
        except (RuntimeError, OSError, KeyError):
            continue
    return saved
