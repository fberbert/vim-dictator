"""Real terminal paste; requires a private X11 and D-Bus session."""

import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "bin"))


@unittest.skipUnless(os.environ.get("VIM_DICTATOR_TEST_DISPLAY") and shutil.which("gnome-terminal"), "requires an isolated display and GNOME Terminal")
class TerminalPasteTests(unittest.TestCase):
    def test_pastes_into_gnome_terminal(self):
        from vim_dictator_tray import Gtk, GLib, TrayApp
        Gtk.init_check()

        def wait(predicate):
            deadline = time.monotonic() + 10
            while time.monotonic() < deadline:
                while GLib.MainContext.default().pending():
                    GLib.MainContext.default().iteration(False)
                if predicate():
                    return
                time.sleep(0.01)
            self.fail("terminal operation timed out")

        with tempfile.TemporaryDirectory(prefix="dictator-terminal-") as directory:
            root = Path(directory)
            capture = root / "capture.py"
            capture.write_text("""import os, pathlib, select, sys, time, tty
root = pathlib.Path(sys.argv[1])
tty.setraw(0)
(root / 'ready').touch()
data = b''
deadline = time.monotonic() + 5
while time.monotonic() < deadline:
    if select.select([0], [], [], 0.1)[0]:
        data += os.read(0, 4096)
(root / 'received').write_bytes(data)
time.sleep(1)
""")
            process = subprocess.Popen(["gnome-terminal", "--wait", "--", sys.executable, str(capture), str(root)], stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
            backend = Mock()
            backend.has_session.return_value = False
            backend.run.side_effect = ["", "ação no terminal"]
            app = TrayApp(backend, hotkey=None, on_quit=lambda: None)
            try:
                wait(lambda: (root / "ready").exists())
                window = subprocess.run(["xdotool", "search", "--onlyvisible", "--class", "Gnome-terminal"], capture_output=True, text=True, check=True).stdout.splitlines()[-1]
                subprocess.run(["xdotool", "windowfocus", "--sync", window], check=True, timeout=5)
                app.toggle()
                wait(lambda: app.phase == "recording")
                app.toggle()
                wait(lambda: app.phase == "idle")
                wait(lambda: (root / "received").exists())
                self.assertEqual((root / "received").read_bytes(), "ação no terminal".encode())
            finally:
                app.close()
                process.terminate()
                process.communicate(timeout=5)


if __name__ == "__main__":
    unittest.main(verbosity=2)
