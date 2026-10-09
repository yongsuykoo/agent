"""Parallel network reading, with database commits on the owning thread only."""
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from . import learning


def study_batch(catalog, cloud, emit, limit, max_apps, workers, cancel):
    results, started, status = [], 0, 'progress'
    def read(app, options,capture,excluded):
        if cancel is not None and cancel.is_set():
            return None
        emit(f"Parallel study: {app['name']}")
        blueprint = learning.research_app(app['name'], app.get('version', ''), cloud,public_capture=capture,exclude_urls=excluded or None, **options)
        if options:
            blueprint['installed_evidence'] = options['focus']['observed_installation']
        return blueprint
    with ThreadPoolExecutor(max_workers=workers, thread_name_prefix='app-study') as pool:
        while started < max_apps:
            pending = {}
            for _ in range(min(workers, max_apps-started)):
                if cancel is not None and cancel.is_set():
                    status = 'cancelled';break
                app = catalog.next_research()
                if app is None:
                    status = 'queue_empty';break
                budget = catalog.consume_budget('research_budget', limit)
                if budget is None:
                    status = 'daily_limit';break
                if not catalog.claim_research(app['id'], app['generation']):
                    continue
                from .machine import installed_research_options
                from .public_manuals import PublicCapture,exhausted_urls
                options = installed_research_options(catalog, app)
                capture=PublicCapture(app)
                pending[pool.submit(read, app, options,capture,exhausted_urls(catalog,app))] = (app,capture)
                started += 1
            if not pending:
                break
            blocked = False
            for future in as_completed(pending):
                app,capture = pending[future]
                try:
                    try:blueprint = future.result()
                    finally:registered=capture.register(catalog,cancel)
                    if blueprint is None or (cancel is not None and cancel.is_set()):
                        catalog.fail_research(app['id'], app['generation'], 'Research cancelled')
                        result = {'status': 'cancelled', 'app': app['name']}
                    elif blueprint.get('public_pdf_pending'):
                        result={'status':'manual_sources_discovered' if registered else 'app_changed','app':app['name'],'public_pdf_sources':registered}
                    elif catalog.save_blueprint(app['id'], app['generation'], blueprint):
                        catalog.set_setting(f"documentation:{app['id']}:{app['generation']}",
                            {'rounds': 1, 'retry_at': (datetime.now(timezone.utc)+timedelta(days=1)).isoformat()})
                        result = {'status': 'documented', 'app': app['name'], 'capabilities': len(blueprint['capabilities'])}
                    else:
                        result = {'status': 'app_changed', 'app': app['name']}
                except Exception as error:
                    from .campaign import cloud_blocked
                    catalog.fail_research(app['id'], app['generation'], error)
                    blocked = blocked or cloud_blocked(error)
                    result = {'status': 'research_failed', 'app': app['name'], 'error': str(error)}
                results.append(result)
            if cancel is not None and cancel.is_set():
                status = 'cancelled';break
            if blocked:
                status = 'cloud_blocked';break
            if status in ('daily_limit', 'queue_empty'):
                break
    return results, status
