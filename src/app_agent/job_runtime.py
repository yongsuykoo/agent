"""One Windows session executes a persistent queue, with fresh local permissions."""
import threading
from .catalog import Catalog
from .jobs import Jobs
from .desktop import WindowsDesktop
from .routing import identify_windows
from .task_director import TaskDirector, resolve_window
from .runner import TaskRunner


def run_next(directory, cloud, approve, emit, cancel=None, *, identity=None,
             credentials=False, shutdown=lambda:False, desktop=WindowsDesktop,
             resolve=resolve_window, director=TaskDirector, runner=TaskRunner,
             autonomous_only=False,execution_guard=None):
    jobs, catalog = Jobs(directory), None
    checkpoint = jobs.claim(identity, credentials=credentials,autonomous_only=autonomous_only)
    if checkpoint is None:
        jobs.close()
        return None
    try:
        checkpoint.guard=execution_guard
        checkpoint.touch()
        item = jobs.get(checkpoint.id)
        emit(f'Saved task {item["id"][:8]}: {item["task"]}')
        catalog = Catalog(directory)
        selected = None
        window = item['options']['window']
        if window:
            observation = desktop(window['handle']).observe()
            if (observation.get('window_handle'),observation.get('process_id')) != (window['handle'],window['process_id']):
                raise RuntimeError('Selected window/process changed; saved task will not select another document.')
            candidates = [app for app in catalog.apps() if identify_windows(app, [(window['handle'],observation['window'])],desktop)]
            if len(candidates) != 1:
                raise RuntimeError('Selected window does not identify one installed app; no arbitrary document chosen.')
            selected = candidates[0]
        def choose(app, event):
            if not window:
                return resolve(app,event)
            if app['id'] != selected['id']:
                raise RuntimeError('Saved selected-window task cannot operate a different app.')
            target = desktop(window['handle'])
            snapshot = target.observe()
            if snapshot.get('process_id') != window['process_id']:
                raise RuntimeError('Selected process changed; no action executed.')
            return target
        cancel = cancel or threading.Event()
        def permit(action, observation):
            checkpoint.touch()
            if cancel.is_set():
                return False
            return approve(action,observation,item['options']['autonomous'])
        result = director(catalog,cloud,permit,emit,directory,cancel,resolve=choose,
                          checkpoint=checkpoint,selected_app=selected,runner=runner).run(item['task'],use_vision=item['options']['use_vision'])
    except Exception as error:
        result = {'task':jobs.get(checkpoint.id)['task'], 'outcome':'error', 'error':str(error), 'steps':[]}
        emit('Saved task deferred: '+str(error))
    finally:
        if catalog is not None:
            catalog.close()
    try:
        state = jobs.settle(checkpoint,result,shutdown=shutdown())
        emit(f'Saved task {checkpoint.id[:8]}: {state["status"]}. {state["detail"]}')
        return state
    finally:
        jobs.close()
