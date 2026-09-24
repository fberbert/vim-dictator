#!/usr/bin/env python3

import contextlib
import importlib.util
import io
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "bin"))

from vim_dictator_cli import Dictator, DictatorError, runtime_directory

if importlib.util.find_spec("vim_dictator_desktop"):
    from vim_dictator_desktop import DesktopBackend, paste_shortcut
else:
    DesktopBackend = paste_shortcut = None


class DesktopBackendTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(DesktopBackend, "desktop backend must exist")

    def test_runtime_is_isolated_without_mutating_environment(self):
        for original in ({"XDG_RUNTIME_DIR": "/tmp/user"}, {"VIM_DICTATOR_RUNTIME_DIR": "/tmp/custom"}):
            with self.subTest(original=original):
                before = dict(original)
                backend = DesktopBackend(original)
                expected = runtime_directory(original, "linux") / "desktop"
                self.assertEqual(backend.env["VIM_DICTATOR_RUNTIME_DIR"], str(expected))
                self.assertEqual(backend.state_file, expected / "session.json")
                self.assertEqual(original, before)
                self.assertEqual(backend.env["VIM_DICTATOR_REQUEST_TIMEOUT"], "120")

    def test_default_environment_is_copied_and_timeout_override_preserved(self):
        with patch.dict("os.environ", {"VIM_DICTATOR_REQUEST_TIMEOUT": "35"}, clear=True):
            backend = DesktopBackend()
        self.assertEqual(backend.env["VIM_DICTATOR_REQUEST_TIMEOUT"], "35")

    def test_runs_each_supported_command_without_shell_or_python_timeout(self):
        backend = DesktopBackend({})
        for action, output in (("start", ""), ("stop", "  ditado\n"), ("cancel", ""), ("status", "idle\n")):
            with self.subTest(action=action), patch("vim_dictator_desktop.subprocess.run") as run:
                run.return_value = subprocess.CompletedProcess([], 0, output, "")
                self.assertEqual(backend.run(action), output.rstrip("\n"))
                args, kwargs = run.call_args
                self.assertEqual(args[0], [sys.executable, str(Path(__file__).resolve().parents[1] / "bin/vim_dictator_cli.py"), action])
                self.assertTrue(kwargs["capture_output"])
                self.assertTrue(kwargs["text"])
                self.assertEqual(kwargs["env"], backend.env)
                self.assertFalse(kwargs.get("shell", False))
                self.assertNotIn("timeout", kwargs)

    def test_rejects_unknown_action_before_starting_a_process(self):
        with patch("vim_dictator_desktop.subprocess.run") as run:
            with self.assertRaises(DictatorError):
                DesktopBackend({}).run("stop; echo secret")
            run.assert_not_called()

    def test_stop_preserves_newlines_in_transcription(self):
        response = subprocess.CompletedProcess([], 0, "linha\n\n\n", "")
        with patch("vim_dictator_desktop.subprocess.run", return_value=response):
            self.assertEqual(DesktopBackend({}).run("stop"), "linha\n\n")

    def test_errors_include_stderr_but_never_api_key_or_transcript(self):
        backend = DesktopBackend({"OPENAI_API_KEY": "fake-private-key"})
        stdout, stderr = io.StringIO(), io.StringIO()
        response = subprocess.CompletedProcess([], 1, "private transcription", "network unavailable fake-private-key")
        with patch("vim_dictator_desktop.subprocess.run", return_value=response):
            with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                with self.assertRaisesRegex(DictatorError, "network unavailable") as error:
                    backend.run("stop")
        self.assertNotIn("fake-private-key", str(error.exception))
        self.assertNotIn("private transcription", str(error.exception))
        self.assertEqual(stdout.getvalue() + stderr.getvalue(), "")

    def test_empty_cli_error_and_os_error_are_actionable(self):
        with patch("vim_dictator_desktop.subprocess.run", return_value=subprocess.CompletedProcess([], 3, "", "")):
            with self.assertRaisesRegex(DictatorError, "3"):
                DesktopBackend({}).run("start")
        with patch("vim_dictator_desktop.subprocess.run", side_effect=OSError("cannot execute")):
            with self.assertRaisesRegex(DictatorError, "cannot execute"):
                DesktopBackend({}).run("start")

    def test_has_session_detects_pending_state_even_if_not_recording(self):
        with tempfile.TemporaryDirectory() as directory:
            backend = DesktopBackend({"VIM_DICTATOR_RUNTIME_DIR": directory})
            self.assertFalse(backend.has_session())
            backend.state_file.parent.mkdir()
            backend.state_file.write_text("{}", encoding="utf-8")
            self.assertTrue(backend.has_session())

    def test_terminal_shortcut_is_case_insensitive(self):
        for window_class in ("Gnome-terminal", "Gnome-terminal-server", "Konsole", "kitty", "Alacritty", "Tilix", "Xfce4-terminal", "org.wezfurlong.wezterm", "XTerm"):
            with self.subTest(window_class=window_class):
                self.assertEqual(paste_shortcut(window_class), "ctrl+shift+v")
        for window_class in ("Firefox", "Code", "", "Chromium"):
            self.assertEqual(paste_shortcut(window_class), "ctrl+v")


class RequestTimeoutTests(unittest.TestCase):
    def transcribe(self, timeout=None):
        env = {"OPENAI_API_KEY": "fake-test-key"}
        if timeout is not None:
            env["VIM_DICTATOR_REQUEST_TIMEOUT"] = timeout
        with tempfile.TemporaryDirectory() as directory:
            audio = Path(directory) / "audio.wav"
            audio.write_bytes(b"fake audio")
            with patch.object(Dictator, "require_executable"), patch("vim_dictator_cli.subprocess.run") as run:
                run.return_value = subprocess.CompletedProcess([], 0, '{"text":"olá"}', "")
                result = Dictator(env, "linux").transcribe(audio)
                return result, run.call_args

    def test_default_cli_has_no_timeout(self):
        result, call = self.transcribe()
        self.assertEqual(result, "olá")
        self.assertNotIn("--max-time", call.args[0])

    def test_configured_timeout_is_passed_as_curl_argument(self):
        for timeout in ("120", "0.5", "3600"):
            result, call = self.transcribe(timeout)
            command = call.args[0]
            self.assertIn("--max-time", command)
            self.assertEqual(command[command.index("--max-time") + 1], timeout)
            self.assertNotIn("timeout", call.kwargs)
            self.assertEqual(result, "olá")

    def test_invalid_timeouts_are_rejected_before_network_request(self):
        for timeout in ("", "0", "-1", "nan", "inf", "3601", "abc", "1; echo bad"):
            with self.subTest(timeout=timeout):
                with self.assertRaisesRegex(DictatorError, "VIM_DICTATOR_REQUEST_TIMEOUT"):
                    self.transcribe(timeout)


if __name__ == "__main__":
    unittest.main(verbosity=2)
