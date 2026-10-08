"""Replay only verified accessible actions with live pre/postcondition checks."""
import json
import time


def guard(observation):
    return sorted([c.get('automation_id', ''), c['type'], c['name'], c.get('value', ''),
                   bool(c['enabled']), bool(c['visible']), bool(c.get('password')),
                   json.dumps(c.get('state', {}), sort_keys=True)]
                  for c in observation['controls'] if c['id'] != 0)


def compile_recipe(record, result_control_id=None):
    if record.get('outcome') != 'result_observed':
        return None
    executed = [entry for entry in record['history'] if entry.get('execution') == 'executed']
    proof = next((entry for entry in reversed(record['history']) if entry.get('matched') is True and 'verification' in entry), None)
    if not executed or len(executed) > 24 or not proof:
        return None
    steps = []
    for entry in executed:
        action = entry['executed_action']
        if action['kind'] == 'click_point' or entry.get('effect') != 'observed_change':
            return None
        target = next((c for c in entry['observation']['controls'] if c['id'] == entry['action'].get('target')), None)
        if not target or target.get('password') or not (target.get('automation_id') or target.get('name')):
            return None
        steps.append({'guard': guard(entry['observation']), 'action': {**action,
            'automation_id': target.get('automation_id'), 'target_name': target['name']}})
    recipe = {'task': record['task'], 'steps': steps, 'final_guard': guard(proof['verification']),
            'expected_text': proof['expected_text'], 'result_control_id': result_control_id}
    return recipe if len(json.dumps(recipe).encode()) <= 256_000 else None


def replay(task, workflows, desktop, approve, cancel, emit, required_result, result_control_id, max_steps, timeout):
    from .runner import validate_action, exact_text_goal, result_matches
    first = desktop.observe()
    signature = guard(first)
    recipe = next((w.get('recipe') for w in workflows if isinstance(w.get('recipe'), dict)
        and w['recipe'].get('task') == task and w['recipe'].get('steps')
        and len(w['recipe']['steps']) <= max_steps
        and w['recipe']['steps'][0].get('guard') == signature
        and w['recipe'].get('result_control_id') == result_control_id
        and (required_result is None or w['recipe'].get('expected_text') == required_result)), None)
    if recipe is None or not first.get('window_handle') or not first.get('process_id'):
        return None
    identity = (first['window_handle'], first['process_id'])
    history, count = [], 0
    emit('Using a verified local workflow; cloud planning is deferred unless a live check fails.')
    def same(snapshot, expected):
        return (snapshot.get('window_handle'), snapshot.get('process_id')) == identity and guard(snapshot) == expected
    def moved(snapshot):
        return (snapshot.get('window_handle'), snapshot.get('process_id')) != identity
    def blocked():
        history.append({'error': 'App window/process changed during local replay.', 'execution': 'local_replay_blocked'})
        return {'outcome': 'blocked', 'history': history, 'actions_executed': count}
    try:
        for index, step in enumerate(recipe['steps']):
            if cancel.is_set():return {'outcome': 'cancelled', 'history': history, 'actions_executed': count}
            before = desktop.observe()
            if moved(before):return blocked()
            if not same(before, step['guard']):break
            action = validate_action(step['action'], before, require_identity=True)
            if not approve(action, before) or cancel.is_set():
                return {'outcome': 'cancelled', 'history': history, 'actions_executed': count}
            latest = desktop.observe()
            if moved(latest):return blocked()
            if not same(latest, step['guard']):break
            entry = {'observation': before, 'action': action, 'execution': 'not_executed'}
            history.append(entry)
            desktop.act(action)
            entry.update(execution='executed', executed_action=action)
            count += 1
            expected = recipe['steps'][index+1]['guard'] if index+1 < len(recipe['steps']) else recipe['final_guard']
            deadline = time.monotonic()+timeout
            after = desktop.observe()
            if moved(after):return blocked()
            while not cancel.is_set() and not same(after, expected) and time.monotonic() < deadline:
                cancel.wait(.05);after = desktop.observe()
                if moved(after):return blocked()
            entry['effect'] = 'observed_change' if guard(after) != guard(before) else 'no_observable_change'
            if cancel.is_set():return {'outcome': 'cancelled', 'history': history, 'actions_executed': count}
            if not same(after, expected):break
        else:
            current = desktop.observe()
            if moved(current):return blocked()
            matched = same(current, recipe['final_guard']) and result_matches(current, recipe['expected_text'], exact_text_goal(task), result_control_id)
            history.append({'verification': current, 'expected_text': recipe['expected_text'], 'matched': matched})
            if matched:
                return {'outcome': 'result_observed', 'history': history, 'actions_executed': count}
    except Exception as error:
        history.append({'error': str(error), 'execution': 'local_replay_failed'})
    emit('Local workflow check failed; returning the actual current state to cloud planning.')
    return {'outcome': 'fallback', 'history': history, 'actions_executed': count}
