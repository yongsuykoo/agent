"""Headless interface integration; native Windows control is tested separately."""
import tempfile
import threading
import queue
import unittest
from pathlib import Path
from unittest.mock import patch, Mock
from app_agent import ui
from app_agent.catalog import Catalog
from test_catalog import app, snapshot


class Variable:
    def __init__(self, value=None, **kwargs):
        self.value = value
    def get(self):
        return self.value
    def set(self, value):
        self.value = value


class Widget:
    def __init__(self, *args, **kwargs):
        self.text = ""
        self.options = kwargs
        self.index = -1
    def pack(self, **kwargs):
        pass
    def configure(self, **kwargs):
        self.options.update(kwargs)
    def insert(self, index, text):
        self.text += text
    def delete(self, *args):
        self.text = ""
    def see(self, *args):
        pass
    def current(self, index=None):
        if index is None:
            return self.index
        self.index = index
    def get(self, *args):
        values = self.options.get("values", [])
        return values[self.index] if values and self.index >= 0 else self.text
    def set(self, value):
        self.text = value
    def __setitem__(self, key, value):
        self.options[key] = value


class Root(Widget):
    def __init__(self):
        super().__init__()
        self.callbacks = []
        self.buttons = {}
    def after(self, delay, function):
        self.callbacks.append((delay, function))
        return len(self.callbacks)
    def after_cancel(self, identifier):
        pass
    def title(self, value):
        pass
    def geometry(self, value):
        pass
    def bind(self, *args):
        pass
    def protocol(self, name, function):
        self.close = function
    def destroy(self):
        pass
    def mainloop(self):
        maintenance = next(fn for delay, fn in self.callbacks if delay == 1000)
        maintenance()  # Startup discovers apps without a user Scan click.
        pump = next(fn for delay, fn in self.callbacks if delay == 100)
        pump()
        self.buttons["Run task"]()
        pump()
        self.close()


class ImmediateWorker:
    def __init__(self, run, on_error):
        self.run = run
    def submit(self, function):
        self.run(function)
    def close(self):
        pass


class InterfaceFlowTests(unittest.TestCase):
    def test_voice_submission_waits_for_transcription_worker_to_finish_without_a_run_click(self):
        class VoiceRoot(Root):
            voice_phase = False
            def mainloop(self):
                maintenance = next(fn for delay, fn in self.callbacks if delay == 1000)
                self.pump = next(fn for delay, fn in self.callbacks if delay == 100)
                maintenance();self.pump()
                self.buttons['Push-to-talk']()
                self.voice_phase = True
                self.buttons['Push-to-talk']()
                self.voice_phase = False
                self.pump()
                for delay, callback in list(self.callbacks):
                    if delay == 0:callback()
                self.pump();self.close()
        root=VoiceRoot()
        class DelayedCompletionQueue(queue.Queue):
            def put(self, item, *args, **kwargs):
                if item[0]=='done' and root.voice_phase:
                    # Tk sees the transcript before the worker's done event.
                    root.pump()
                    for delay, callback in list(root.callbacks):
                        if delay == 0:callback()
                return super().put(item,*args,**kwargs)
        recorder=Mock(stream=None);recorder.stop.return_value=b'voice-fixture'
        with patch.object(ui,'Recorder',return_value=recorder), \
             patch.object(ui,'transcribe',return_value='Calculate 23 plus 19 and verify the result.') as transcribe, \
             patch.object(ui.queue,'Queue',DelayedCompletionQueue):
            self.test_startup_discovery_auto_route_research_and_memory(root=root)
        recorder.start.assert_called_once();transcribe.assert_called_once_with(b'voice-fixture')

    def test_documentation_worker_runs_off_the_calling_thread(self):
        started, release, completed = threading.Event(), threading.Event(), threading.Event()
        identities = []
        def work():
            identities.append(threading.get_ident())
            started.set()
            release.wait(2)
            completed.set()
        thread = ui.launch_research(work)
        try:
            self.assertTrue(started.wait(1))
            self.assertNotEqual(identities[0], threading.get_ident())
            self.assertFalse(completed.is_set())
        finally:
            release.set()
            thread.join(2)
        self.assertFalse(thread.is_alive())

    def test_foreground_task_can_start_while_documentation_is_pending(self):
        class DeferredRoot(Root):
            def mainloop(self):
                maintenance = next(fn for delay, fn in self.callbacks if delay == 1000)
                pump = next(fn for delay, fn in self.callbacks if delay == 100)
                maintenance()
                pump()
                maintenance()  # Documentation is submitted but not completed.
                self.buttons["Run task"]()
                pump()
                self.close()
        pending = []
        self.test_startup_discovery_auto_route_research_and_memory(root=DeferredRoot(), background_launcher=pending.append)
        self.assertEqual(len(pending), 1)

    def test_learn_all_button_starts_persistent_campaign_without_task_commands(self):
        class CampaignRoot(Root):
            def mainloop(self):
                maintenance = next(fn for delay, fn in self.callbacks if delay == 1000)
                pump = next(fn for delay, fn in self.callbacks if delay == 100)
                maintenance()
                pump()
                self.buttons["Learn all apps"]()
                maintenance()
                pump()
                self.close()
        root = CampaignRoot()
        def button(*args, **kwargs):
            root.buttons[kwargs["text"]] = kwargs["command"]
            return Widget(*args, **kwargs)
        desktop = Mock()
        desktop.windows.return_value = []
        with tempfile.TemporaryDirectory() as directory, patch.dict("os.environ", {"AGENT_API_KEY": "test-key"}), \
             patch.object(ui.tk, "Tk", return_value=root), patch.object(ui.tk, "StringVar", Variable), \
             patch.object(ui.tk, "BooleanVar", Variable), patch.object(ui.tk, "IntVar", Variable), patch.object(ui.tk, "Text", Widget), \
             patch.multiple(ui.ttk, Frame=Widget, Label=Widget, Entry=Widget, Combobox=Widget, Button=button, Checkbutton=Widget, Spinbox=Widget), \
             patch.object(ui, "AutomationWorker", ImmediateWorker), patch.object(ui, "launch_research", side_effect=lambda fn: fn()), patch.object(ui, "WindowsDesktop", desktop), \
             patch.object(ui, "CloudResearcher", return_value=Mock()), \
             patch.object(ui, "scan_apps", return_value=snapshot([app()])), \
             patch.object(ui, "register_stop", return_value=threading.Event()), \
             patch.object(ui, "study_campaign", return_value={"status": "progress"}) as campaign:
            ui.launch(Path(directory))
            catalog = Catalog(directory)
            try:
                self.assertTrue(catalog.setting("study_campaign"))
                self.assertTrue(catalog.setting("auto_learn"))
                self.assertEqual(catalog.setting("daily_limit"), 0)
            finally:
                catalog.close()
        campaign.assert_called_once()
        self.assertEqual(campaign.call_args.kwargs["daily_limit"], 0)

    def test_manual_practice_claims_the_existing_background_experiment(self):
        class PracticeRoot(Root):
            def mainloop(self):
                maintenance = next(fn for delay, fn in self.callbacks if delay == 1000)
                pump = next(fn for delay, fn in self.callbacks if delay == 100)
                maintenance()
                pump()
                self.buttons["Practice app"]()
                pump()
                self.close()
        with patch.object(ui, "practice_task", side_effect=AssertionError("The queued experiment must be reused")):
            self.test_startup_discovery_auto_route_research_and_memory(root=PracticeRoot(), ready_practice=True)

    def test_startup_discovery_auto_route_research_and_memory(self, root=None, background_launcher=None, ready_practice=False):
        root = root or Root()
        def button(*args, **kwargs):
            root.buttons[kwargs["text"]] = kwargs["command"]
            return Widget(*args, **kwargs)
        cloud = Mock()
        def respond(**payload):
            text = ('{"steps":[{"app_id":"start:calculator","task":"Calculate 23 plus 19 and verify the result.","expected_result":"42"}]}'
                    if payload.get("text", {}).get("format", {}).get("name") == "personal_task_plan"
                    else '{"app_id":"start:calculator"}')
            return {"output": [{"content": [{"type": "output_text", "text": text}]}]}
        cloud.request.side_effect = respond
        desktop = Mock()
        desktop.windows.return_value = [(10, "Calculator"), (20, "API keys - Google Chrome")]
        desktop.return_value.observe.return_value = {"window": "Calculator", "window_handle": 10, "process_id": 81, "controls": []}
        runner = Mock()
        runner.return_value.run.return_value = {"task": "Calculate", "outcome": "result_observed", "actions_executed": 6, "history": [{"verification": {"window": "Calculator", "controls": []}}]}
        blueprint = {"name": "Calculator", "version": "1", "capabilities": [{"name": "Add"}]}
        with tempfile.TemporaryDirectory() as directory, patch.dict("os.environ", {"AGENT_API_KEY": "test-key"}), \
             patch.object(ui.tk, "Tk", return_value=root), patch.object(ui.tk, "StringVar", Variable), \
             patch.object(ui.tk, "BooleanVar", Variable), patch.object(ui.tk, "IntVar", Variable), patch.object(ui.tk, "Text", Widget), \
             patch.multiple(ui.ttk, Frame=Widget, Label=Widget, Entry=Widget, Combobox=Widget, Button=button, Checkbutton=Widget, Spinbox=Widget), \
             patch.object(ui, "AutomationWorker", ImmediateWorker), patch.object(ui, "launch_research", side_effect=background_launcher or (lambda fn: fn())), patch.object(ui, "WindowsDesktop", desktop), \
             patch.object(ui, "CloudResearcher", return_value=cloud), patch.object(ui, "TaskRunner", runner), \
             patch.object(ui, "scan_apps", return_value=snapshot([app()])), \
             patch.object(ui, "register_stop", return_value=threading.Event()), \
             patch.object(ui.messagebox, "askokcancel", return_value=True), \
             patch("app_agent.learning.research_app", return_value=blueprint):
            if ready_practice:
                catalog = Catalog(directory)
                try:
                    catalog.sync(snapshot([app()]))
                    catalog.save_blueprint(app()["id"], 1, blueprint)
                    catalog.save_practice_plan(app()["id"], 1, {"capability_name": "Add", "risk": "disposable",
                                                               "task": "Calculate and verify 42", "expected_result": "42"})
                finally:
                    catalog.close()
            ui.launch(Path(directory))
            catalog = Catalog(directory)
            try:
                current = catalog.get(app()["id"])
                self.assertEqual(current["blueprint"], blueprint)
                self.assertEqual(len(catalog.workflows(current["id"], current["generation"])), 1)
                self.assertIsNotNone(catalog.interface(current["id"], current["generation"]))
                if ready_practice:
                    saved = catalog.practice_plan(current["id"], current["generation"], "Add")
                    self.assertEqual(saved["status"], "tested")
                    self.assertEqual(saved["attempts"], 1)
                    self.assertEqual(runner.return_value.run.call_args.kwargs["required_result_text"], "42")
            finally:
                catalog.close()
        desktop.assert_called_with(10)
        self.assertEqual(runner.return_value.run.call_count, 1)
