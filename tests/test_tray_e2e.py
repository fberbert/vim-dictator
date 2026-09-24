"""Real GTK/X11 input with fake audio and API, only inside a private X server."""

import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "bin"))


@unittest.skipUnless(os.environ.get("VIM_DICTATOR_TEST_DISPLAY"), "requires an isolated test display")
class TrayEndToEndTests(unittest.TestCase):
    def test_global_hotkey_records_and_pastes_unicode_in_focused_window(self):
        import gi
        gi.require_version("Gtk", "3.0")
        gi.require_version("GdkX11", "3.0")
        from gi.repository import Gtk, GLib, GdkX11
        from vim_dictator_desktop import DesktopBackend
        from vim_dictator_tray import TrayApp

        def wait(predicate):
            deadline = time.monotonic() + 12
            while time.monotonic() < deadline:
                while GLib.MainContext.default().pending():
                    GLib.MainContext.default().iteration(False)
                if predicate():
                    return
                time.sleep(0.01)
            self.fail("desktop operation did not complete: " + app.status_item.get_label())

        text = "Olá, ação e coração!\nPontuação: ç, á, ã; $(não executar)."
        with tempfile.TemporaryDirectory(prefix="dictator-e2e-") as directory:
            root = Path(directory)
            recorder = root / "recorder"
            recorder.write_text("#!/usr/bin/python3\nimport pathlib, sys, time\npathlib.Path(sys.argv[-1]).write_bytes(b'RIFF')\nwhile True: time.sleep(0.05)\n")
            curl = root / "curl"
            curl.write_text("#!/usr/bin/python3\nprint(" + repr(json.dumps({"text": text})) + ")\n")
            recorder.chmod(0o700)
            curl.chmod(0o700)
            environment = {k: v for k, v in os.environ.items() if not k.startswith("VIM_DICTATOR_") and k != "OPENAI_API_KEY"}
            environment.update({
                "OPENAI_API_KEY": "test-key", "VIM_DICTATOR_RUNTIME_DIR": str(root / "runtime"),
                "VIM_DICTATOR_RECORDER": str(recorder), "VIM_DICTATOR_CURL": str(curl),
            })
            backend = DesktopBackend(environment)
            app = TrayApp(backend, on_quit=lambda: None)
            self.assertTrue(app.bound, "global hotkey was not registered")
            window = Gtk.Window(title="Vim Dictator isolated test")
            window.set_wmclass("dictator-test", "Firefox")
            editor = Gtk.TextView()
            window.add(editor)
            window.show_all()
            editor.grab_focus()
            try:
                wait(lambda: window.get_window() is not None)
                xid = window.get_window().get_xid()
                subprocess.run(["xdotool", "windowfocus", "--sync", str(xid)], check=True, timeout=5)
                subprocess.run(["xdotool", "key", "--clearmodifiers", "ctrl+alt+space"], check=True, timeout=5)
                wait(lambda: app.phase == "recording")
                subprocess.run(["xdotool", "key", "--clearmodifiers", "ctrl+alt+space"], check=True, timeout=5)
                wait(lambda: app.phase == "idle")
                buffer = editor.get_buffer()
                wait(lambda: buffer.get_text(buffer.get_start_iter(), buffer.get_end_iter(), True) == text)
                self.assertFalse(backend.has_session(), "completed audio was not cleaned")
                self.assertFalse((root / "runtime" / "session.json").exists(), "Neovim state was touched")
            finally:
                if backend.has_session():
                    backend.run("cancel")
                app.close()
                window.destroy()


if __name__ == "__main__":
    unittest.main(verbosity=2)
