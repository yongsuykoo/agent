"""Headless interface integration; native Windows control is tested separately."""
import tempfile
import threading
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
    def test_startup_discovery_auto_route_research_and_memory(self):
        root = Root()
        def button(*args, **kwargs):
            root.buttons[kwargs["text"]] = kwargs["command"]
            return Widget(*args, **kwargs)
        cloud = Mock()
        cloud.request.return_value = {"output": [{"content": [{"type": "output_text", "text": '{"app_id":"start:calculator"}'}]}]}
        desktop = Mock()
        desktop.windows.return_value = [(10, "Calculator"), (20, "API keys - Google Chrome")]
        desktop.return_value.observe.return_value = {"window": "Calculator", "controls": []}
        runner = Mock()
        runner.return_value.run.return_value = {"task": "Calculate", "outcome": "result_observed", "actions_executed": 6, "history": [{"verification": {"window": "Calculator", "controls": []}}]}
        blueprint = {"name": "Calculator", "version": "1", "capabilities": [{"name": "Add"}]}
        with tempfile.TemporaryDirectory() as directory, patch.dict("os.environ", {"AGENT_API_KEY": "test-key"}), \
             patch.object(ui.tk, "Tk", return_value=root), patch.object(ui.tk, "StringVar", Variable), \
             patch.object(ui.tk, "BooleanVar", Variable), patch.object(ui.tk, "IntVar", Variable), patch.object(ui.tk, "Text", Widget), \
             patch.multiple(ui.ttk, Frame=Widget, Label=Widget, Entry=Widget, Combobox=Widget, Button=button, Checkbutton=Widget, Spinbox=Widget), \
             patch.object(ui, "AutomationWorker", ImmediateWorker), patch.object(ui, "WindowsDesktop", desktop), \
             patch.object(ui, "CloudResearcher", return_value=cloud), patch.object(ui, "TaskRunner", runner), \
             patch.object(ui, "scan_apps", return_value=snapshot([app()])), \
             patch.object(ui, "register_stop", return_value=threading.Event()), \
             patch.object(ui.messagebox, "askokcancel", return_value=True), \
             patch("app_agent.learning.research_app", return_value=blueprint):
            ui.launch(Path(directory))
            catalog = Catalog(directory)
            try:
                current = catalog.get(app()["id"])
                self.assertEqual(current["blueprint"], blueprint)
                self.assertEqual(len(catalog.workflows(current["id"], current["generation"])), 1)
                self.assertIsNotNone(catalog.interface(current["id"], current["generation"]))
            finally:
                catalog.close()
        desktop.assert_called_with(10)
        self.assertEqual(runner.return_value.run.call_count, 1)
