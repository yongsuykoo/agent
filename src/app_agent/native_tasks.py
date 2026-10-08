"""Native creative tasks share chat permission, cancellation and version evidence."""
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import uuid
from .design_artifacts import verify_exports
from .logo_design import plan_logo, validate_design
from .photoshop import Photoshop, select_photoshop, photoshop_app


def run_logo(director, task, adapter=Photoshop):
    result = {'task': task, 'outcome': 'error', 'steps': [], 'verified_results': [],
              'time': datetime.now(timezone.utc).isoformat(),
              'scope': 'Native Photoshop logo structure and exports; visual quality and arbitrary app mastery are not certified.'}
    native = None
    try:
        if re.search(r'\band\s+(?:then\s+)?(?:email|send|upload|publish|print|delete|copy|paste|insert|attach)\b|\b(?:edit|modify|replace|update)\s+(?:the\s+)?(?:existing\s+)?(?:logo|document)\b', task, re.I):
            raise RuntimeError('This adapter creates a fresh logo; additional delivery or existing-document operations need a separate workflow.')
        if re.search(r'\b(?:save|export)\s+(?:it\s+)?(?:to|in|as)\s+["\']?(?:[A-Za-z]:[\\/]|\\\\|(?:my\s+|the\s+)?Desktop\b)', task, re.I):
            raise RuntimeError('This adapter exports only to a new App Agent task folder; the requested other destination is unsupported.')
        apps = director.catalog.apps()
        for other in apps:
            if not photoshop_app(other) and any(re.search(r'\b(?:in|using|with)\s+(?:the\s+)?' + re.escape(name) + r'\b', task, re.I)
                    for name in other.get('aliases', [other.get('name', '')]) if name):
                raise RuntimeError('This native logo adapter supports Photoshop; the requested different app must use its own workflow.')
        app = select_photoshop(apps)
        checkpoint = getattr(director, 'checkpoint', None)
        if checkpoint:
            saved = checkpoint.jobs.get(checkpoint.id)
            if saved['verified']:
                # A crash after durable export verification must not render again.
                records = checkpoint.records()
                last = records[-1]
                proof = verify_exports(Path(last['directory']),last['design'],last['observation'])
                if proof['files'] != saved['verified'][0]:
                    raise RuntimeError('Saved verified exports changed; no automatic re-render.')
                result.update(outcome='artifacts_verified',verified_results=proof['files'],steps=records)
                return _save(director,result)
            plan = {'steps':[{'app_id':app['id'],'task':task,'expected_result':'Verified PSD/PNG exports'}],
                    'os_build':director.catalog.setting('machine_model',{}).get('os',{}).get('build'),
                    'generations':{app['id']:app['generation']}}
            if saved['plan'] and saved['plan'] != plan:
                raise RuntimeError('Installed app changed during the saved logo goal; stale plan not replayed.')
            checkpoint.save_plan(plan)
        def current():
            latest = director.catalog.get(app['id'])
            if director.cancel.is_set() or not latest or not latest.get('present', True) or latest['generation'] != app['generation']:
                raise RuntimeError('Task cancelled or installed app changed; native task discarded.')
        current()
        desktop = director.resolve(app, director.cancel)
        observed = desktop.observe()
        identity = (observed.get('window_handle'), observed.get('process_id'))
        action = {'kind': 'create_artifact', 'target': 0, 'text': 'Fresh Photoshop logo document and PSD/PNG exports in a new App Agent task folder.',
                  'reason': 'Create only the requested logo using the documented Adobe automation interface.'}
        if not director.approve(action, observed):
            result['outcome'] = 'cancelled' if director.cancel.is_set() else 'blocked'
            return _save(director, result)
        current()
        native = adapter(app, observed)
        director.emit('Photoshop ' + str(native.info['version']) + ': planning a fresh layered logo using installed fonts.')
        cached = director.catalog.artifact_recipe(app['id'], app['generation'], task)
        design = None
        if cached and cached.get('native_identity') == {k: native.info[k] for k in ('name', 'version', 'path')}:
            try:
                design = validate_design(cached['design'], task, native.info['fonts'])
                director.emit('Reusing a previously verified logo recipe; new exports will be checked again.')
            except ValueError:
                pass
        for attempt in range(2):
            current()
            if design is None:
                design = plan_logo(task, director.cloud, native.info['fonts'],
                    feedback=result['steps'][-1].get('error') if result['steps'] else None, cancel=director.cancel)
            current()
            latest_observation = desktop.observe()
            if identity != tuple(latest_observation.get(k) for k in ('window_handle', 'process_id')):
                raise RuntimeError('Selected Photoshop window/process changed.')
            directory = Path(director.directory)/'outputs'/('logo-' + uuid.uuid4().hex)
            # Reject links/junctions before Photoshop writes, as well as during verification.
            if any(p.is_symlink() or (hasattr(p, 'is_junction') and p.is_junction()) for p in [directory, *directory.parents]):
                raise ValueError('Task output folder cannot traverse a link or junction.')
            directory.mkdir(parents=True, exist_ok=False)
            record = {'task': task, 'attempt': attempt+1, 'design': design, 'directory': str(directory),
                      'native_identity': {k: native.info[k] for k in ('name', 'version', 'path')}}
            result['steps'].append(record)
            try:
                director.emit('Creating logo layers and exporting PSD/PNG; checking file contents next.')
                effect = checkpoint.begin_effect({'kind':'create_artifact','directory':str(directory),'app_id':app['id']}) if checkpoint else None
                record['observation'] = native.render(design, directory, directory.name, director.cancel)
                if checkpoint:
                    checkpoint.applied(effect)
                current()
                latest_observation = desktop.observe()
                if identity != tuple(latest_observation.get(k) for k in ('window_handle', 'process_id')):
                    raise RuntimeError('Photoshop window/process changed before export verification.')
                record['verification'] = verify_exports(directory, design, record['observation'])
                current()
                record['outcome'] = 'artifact_verified'
                if not director.catalog.save_artifact_workflow(app['id'], app['generation'], record):
                    raise RuntimeError('App generation changed; verified recipe was not retained.')
                result['outcome'] = 'artifacts_verified'
                result['verified_results'] = record['verification']['files']
                if checkpoint:
                    checkpoint.verified(result['verified_results'],record)
                for item in result['verified_results']:
                    director.emit('Verified export: ' + item['path'])
                break
            except Exception as error:
                record['outcome'] = 'verification_failed'; record['error'] = str(error)[:1500]
                if director.cancel.is_set():
                    raise
                if checkpoint and checkpoint.pending_actions():
                    director.emit('Unverified native exports retained; automatic render retry stopped.')
                    result['outcome'] = 'verification_failed'
                    break
                if attempt:
                    result['outcome'] = 'verification_failed'
                    break
                director.emit('Logo output failed verification; repairing the composition once: ' + str(error)[:300])
                design = None
    except Exception as error:
        result['error'] = str(error)[:1500]
        result['outcome'] = 'cancelled' if director.cancel.is_set() else 'blocked'
        director.emit('Logo task blocked: ' + str(error)[:500])
    finally:
        if native is not None:
            try:
                native.close()
            except Exception as error:
                result['cleanup_warning'] = str(error)[:500]
                director.emit('Native interface cleanup warning: ' + str(error)[:300])
    return _save(director, result)


def _save(director, result):
    directory = Path(director.directory)
    directory.mkdir(parents=True, exist_ok=True)
    with (directory/'objective-sessions.jsonl').open('a', encoding='utf-8') as stream:
        stream.write(json.dumps(result)+'\n')
    director.emit('Task outcome: ' + result['outcome'])
    return result
