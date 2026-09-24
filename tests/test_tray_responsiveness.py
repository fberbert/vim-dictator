"""Keyboard and mouse remain available during a pending transcription."""

import os
import subprocess
import sys
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "bin"))


@unittest.skipUnless(os.environ.get("VIM_DICTATOR_TEST_DISPLAY"), "requires a private X11 display")
class DesktopResponsivenessTests(unittest.TestCase):
    def test_keyboard_and_mouse_work_while_transcription_waits(self):
        self.assert_input_works("transcribing")

    def test_keyboard_and_mouse_work_while_paste_waits(self):
        self.assert_input_works("pasting")

    def assert_input_works(self, busy_phase):
        import gi
        gi.require_version("GdkX11", "3.0")
        from gi.repository import GdkX11
        from vim_dictator_tray import Gtk, GLib, TrayApp
        Gtk.init_check()
        release = threading.Event()
        paste_entered = threading.Event()
        backend = Mock()
        backend.has_session.return_value = False
        backend.run.side_effect = lambda action: ((release.wait(10) and "ditado") if busy_phase == "transcribing" else "ditado") if action == "stop" else ""

        def paste():
            paste_entered.set()
            if busy_phase == "pasting":
                release.wait(10)

        app = TrayApp(backend, paste=paste, on_quit=lambda: None)
        window = Gtk.Window()
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        editor, button = Gtk.Entry(), Gtk.Button(label="Clique durante a transcrição")
        clicked = []
        button.connect("clicked", lambda *_: clicked.append(True))
        box.pack_start(editor, True, True, 0)
        box.pack_start(button, True, True, 0)
        window.add(box)
        window.set_default_size(400, 160)
        window.show_all()
        editor.grab_focus()

        def wait(predicate):
            deadline = time.monotonic() + 2
            while time.monotonic() < deadline:
                while GLib.MainContext.default().pending():
                    GLib.MainContext.default().iteration(False)
                if predicate():
                    return
                time.sleep(0.005)
            self.fail("desktop stopped responding during " + app.phase)

        def xdo(*args):
            subprocess.run(["xdotool", *args], check=True, timeout=2)

        try:
            wait(lambda: window.get_window() is not None)
            xid = str(window.get_window().get_xid())
            xdo("windowfocus", "--sync", xid)
            xdo("key", "ctrl+alt+space")
            wait(lambda: app.phase == "recording")
            xdo("key", "ctrl+alt+space")
            wait(lambda: app.phase == busy_phase)
            if busy_phase == "pasting":
                wait(paste_entered.is_set)
            xdo("type", "livre")
            wait(lambda: editor.get_text() == "livre")
            allocation = button.get_allocation()
            xdo("mousemove", "--window", xid, str(allocation.x + 20), str(allocation.y + 20), "click", "1")
            wait(lambda: bool(clicked))
            self.assertFalse(release.is_set(), "transcription must still be pending")
        finally:
            release.set()
            wait(lambda: app.phase == "idle")
            app.close()
            window.destroy()


if __name__ == "__main__":
    unittest.main(verbosity=2)
