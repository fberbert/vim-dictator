"""Run in an isolated X11 display; never use the personal desktop for these tests."""

import os
import sys
import time
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "bin"))

from vim_dictator_tray import TrayApp, copy_text, paste_into_focus


class TrayTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import gi
        gi.require_version("Gtk", "3.0")
        from gi.repository import Gtk, GLib
        cls.Gtk, cls.GLib = Gtk, GLib
        if not os.environ.get("VIM_DICTATOR_TEST_DISPLAY"):
            raise unittest.SkipTest("requires an isolated test display")
        if not Gtk.init_check()[0]:
            raise unittest.SkipTest("no GTK display")

    def setUp(self):
        self.backend = Mock()
        self.backend.has_session.return_value = False
        self.backend.run.return_value = ""
        self.paste = Mock()
        self.shutdown = Mock()
        self.app = TrayApp(self.backend, hotkey=None, paste=self.paste, on_quit=self.shutdown)

    def tearDown(self):
        self.app.close()

    def wait(self, phase):
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            while self.GLib.MainContext.default().pending():
                self.GLib.MainContext.default().iteration(False)
            if self.app.phase == phase:
                return
            time.sleep(0.01)
        self.fail(f"expected {phase}, got {self.app.phase}")

    def start(self):
        self.app.toggle()
        self.wait("recording")

    def test_record_transcribe_and_paste_without_blocking(self):
        self.start()
        self.backend.run.return_value = "Olá, ação!\nSegunda linha."
        self.app.toggle()
        self.wait("idle")
        self.paste.assert_called_once_with()
        self.assertEqual(self.app.last_text, "Olá, ação!\nSegunda linha.")
        self.assertEqual([call.args[0] for call in self.backend.run.call_args_list], ["start", "stop"])

    def test_paste_preserves_trailing_newlines(self):
        self.start()
        self.backend.run.return_value = "linha\n\n"
        self.app.toggle()
        self.wait("idle")
        self.paste.assert_called_once_with()
        self.assertEqual(self.app.last_text, "linha\n\n")

    def test_failure_keeps_retry_and_cancel_available(self):
        self.start()
        self.backend.run.side_effect = RuntimeError("API indisponível")
        self.app.toggle()
        self.wait("retry")
        self.paste.assert_not_called()
        self.assertIn("API indisponível", self.app.status_item.get_label())
        self.backend.run.side_effect = None
        self.app.cancel()
        self.wait("idle")

    def test_paste_failure_retains_text_for_copy(self):
        self.start()
        self.backend.run.return_value = "texto"
        self.paste.side_effect = RuntimeError("falha ao colar")
        self.app.toggle()
        self.wait("idle")
        self.assertEqual(self.app.last_text, "texto")
        self.assertTrue(self.app.copy_item.get_sensitive())
        self.assertIn("falha ao colar", self.app.status_item.get_label())

    def test_slow_paste_does_not_block_the_gtk_loop(self):
        import threading
        release = threading.Event()
        heartbeat = threading.Event()
        entered = threading.Event()

        def slow_paste():
            entered.set()
            release.wait(1.5)

        self.app.paste = slow_paste
        self.app.phase = "pasting"

        def tick():
            heartbeat.set()
            return False

        self.GLib.timeout_add(30, tick)
        self.GLib.idle_add(self.app._paste)
        started = time.monotonic()
        try:
            deadline = started + 0.4
            while time.monotonic() < deadline and not heartbeat.is_set():
                self.GLib.MainContext.default().iteration(False)
                time.sleep(0.001)
            self.assertTrue(heartbeat.is_set(), "GTK timer blocked by paste")
            self.assertLess(time.monotonic() - started, 0.4, "paste blocked the UI thread")
            self.assertTrue(entered.is_set())
            self.assertEqual(self.app.phase, "pasting")
        finally:
            release.set()
            self.wait("idle")

    def test_quit_waits_for_pending_paste_then_closes(self):
        import threading
        release, entered = threading.Event(), threading.Event()

        def paste():
            entered.set()
            release.wait(2)

        self.app.paste = paste
        self.app.phase = "pasting"
        self.app._paste()
        try:
            self.assertTrue(entered.wait(0.5))
            self.app.quit()
            self.shutdown.assert_not_called()
            self.assertEqual(self.app.phase, "pasting")
        finally:
            release.set()
            self.wait("closed")
        self.shutdown.assert_called_once()

    def test_quit_before_scheduled_paste_cancels_insertion(self):
        self.app._completed("stop", "texto", None)
        self.assertEqual(self.app.phase, "pasting")
        self.app.quit()
        self.wait("closed")
        self.paste.assert_not_called()
        self.shutdown.assert_called_once()

    def test_clipboard_failure_releases_session_and_retains_text(self):
        self.start()
        self.backend.run.return_value = "texto"
        with patch("vim_dictator_tray.copy_text", side_effect=RuntimeError("clipboard indisponível")):
            self.app.toggle()
            self.wait("idle")
        self.paste.assert_not_called()
        self.assertEqual(self.app.last_text, "texto")
        self.assertTrue(self.app.copy_item.get_sensitive())
        self.assertIn("clipboard indisponível", self.app.status_item.get_label())

    def test_start_failure_returns_idle(self):
        self.backend.run.side_effect = RuntimeError("microfone indisponível")
        self.app.toggle()
        self.wait("idle")
        self.assertFalse(self.app.cancel_item.get_sensitive())

    def test_empty_response_does_not_paste(self):
        self.start()
        self.app.toggle()
        self.wait("idle")
        self.paste.assert_not_called()

    def test_restore_pending_session(self):
        self.app.close()
        self.backend.has_session.return_value = True
        self.app = TrayApp(self.backend, hotkey=None, paste=self.paste, on_quit=self.shutdown)
        self.assertEqual(self.app.phase, "retry")
        self.app.cancel()
        self.wait("idle")

    def test_quit_discards_active_recording(self):
        self.start()
        self.app.quit()
        self.wait("closed")
        self.backend.run.assert_called_with("cancel")
        self.shutdown.assert_called_once()

    def test_busy_operations_are_not_duplicated(self):
        import threading
        release = threading.Event()
        self.backend.run.side_effect = lambda action: release.wait(2) and ""
        self.app.toggle()
        self.app.toggle()
        self.app.cancel()
        self.assertEqual(self.app.phase, "starting")
        release.set()
        self.wait("recording")
        self.backend.run.assert_called_once_with("start")

    def test_global_hotkey_calls_toggle(self):
        self.app.close()
        with patch("vim_dictator_tray.Keybinder.bind", return_value=True) as bind:
            self.app = TrayApp(self.backend, hotkey="<Ctrl><Alt>space", paste=self.paste)
            bind.call_args.args[1]()
            self.wait("recording")

    def test_busy_quit_waits_and_cleans_up(self):
        import threading
        release = threading.Event()
        self.backend.run.side_effect = lambda action: release.wait(2) and ""
        self.app.toggle()
        self.app.quit()
        self.assertEqual(self.app.phase, "starting")
        release.set()
        self.wait("closed")
        self.assertEqual([call.args[0] for call in self.backend.run.call_args_list], ["start", "cancel"])

    def test_copy_last_transcription(self):
        self.app.last_text = "ação"
        with patch("vim_dictator_tray.copy_text") as copy:
            self.app.copy_last()
        copy.assert_called_once_with("ação")

    def test_occupied_shortcut_leaves_menu_usable(self):
        self.app.close()
        with patch("vim_dictator_tray.Keybinder.bind", return_value=False):
            self.app = TrayApp(self.backend, hotkey="<Ctrl><Alt>space", paste=self.paste)
        self.assertTrue(self.app.toggle_item.get_sensitive())
        self.assertIn("Atalho ocupado", self.app.status_item.get_label())


class PasteTests(unittest.TestCase):
    def test_copy_does_not_wait_for_clipboard_manager_persistence(self):
        clipboard = Mock()
        with patch("vim_dictator_tray.Gtk.Clipboard.get", return_value=clipboard):
            copy_text("texto")
        clipboard.set_text.assert_called_once_with("texto", -1)
        clipboard.store.assert_not_called()

    def test_missing_focus_keeps_copied_text_without_sending_keys(self):
        with patch("vim_dictator_tray.Gtk.Clipboard.get"), \
             patch("vim_dictator_tray.subprocess.run", return_value=Mock(returncode=1, stdout="")) as run:
            with self.assertRaisesRegex(RuntimeError, "foco"):
                paste_into_focus()
        self.assertEqual(run.call_count, 1)

    def test_failed_paste_is_reported(self):
        results = [Mock(returncode=0, stdout="123"), Mock(returncode=0, stdout='WM_CLASS = "Firefox"'), Mock(returncode=1)]
        with patch("vim_dictator_tray.Gtk.Clipboard.get"), patch("vim_dictator_tray.subprocess.run", side_effect=results):
            with self.assertRaisesRegex(RuntimeError, "colar"):
                paste_into_focus()

    def test_unicode_text_is_clipboard_data_not_shell_code(self):
        clipboard = Mock()
        results = [Mock(returncode=0, stdout="123\n"), Mock(returncode=0, stdout='WM_CLASS(STRING) = "Firefox"'), Mock(returncode=0)]
        with patch("vim_dictator_tray.Gtk.Clipboard.get", return_value=clipboard), \
             patch("vim_dictator_tray.subprocess.run", side_effect=results) as run:
            copy_text("Olá; $(echo nada)\nlinha 2")
            paste_into_focus()
        clipboard.set_text.assert_called_once_with("Olá; $(echo nada)\nlinha 2", -1)
        self.assertEqual(run.call_args.args[0], ["xdotool", "key", "--clearmodifiers", "ctrl+v"])
        self.assertNotIn("shell", run.call_args.kwargs)

    def test_terminal_paste_shortcut(self):
        results = [Mock(returncode=0, stdout="123\n"), Mock(returncode=0, stdout='WM_CLASS(STRING) = "Gnome-terminal"'), Mock(returncode=0)]
        with patch("vim_dictator_tray.Gtk.Clipboard.get"), \
             patch("vim_dictator_tray.subprocess.run", side_effect=results) as run:
            paste_into_focus()
        self.assertEqual(run.call_args.args[0][-1], "ctrl+shift+v")


@unittest.skipUnless(os.environ.get("VIM_DICTATOR_TEST_DISPLAY"), "requires an isolated test display")
class StartupTests(unittest.TestCase):
    def test_graphical_main_starts_and_releases_instance_lock(self):
        import tempfile
        from vim_dictator_tray import main
        with tempfile.TemporaryDirectory() as directory:
            environment = {"VIM_DICTATOR_RUNTIME_DIR": directory, "XDG_SESSION_TYPE": "x11"}
            with patch.dict(os.environ, environment), patch("vim_dictator_tray.Gtk.main") as loop:
                self.assertEqual(main(["--no-hotkey"]), 0)
                self.assertEqual(main(["--no-hotkey"]), 0)
            self.assertEqual(loop.call_count, 2)

    def test_wayland_is_rejected(self):
        from vim_dictator_tray import main
        with patch.dict(os.environ, {"XDG_SESSION_TYPE": "wayland"}), patch("sys.stderr"):
            with self.assertRaises(SystemExit) as error:
                main([])
        self.assertEqual(error.exception.code, 2)

    def test_duplicate_instance_is_rejected(self):
        import fcntl
        import tempfile
        from vim_dictator_tray import main
        with tempfile.TemporaryDirectory() as directory:
            runtime = Path(directory) / "desktop"
            runtime.mkdir()
            with (runtime / "tray.lock").open("w") as lock:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                with patch.dict(os.environ, {"VIM_DICTATOR_RUNTIME_DIR": directory}), patch("sys.stderr"):
                    self.assertEqual(main(["--no-hotkey"]), 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
