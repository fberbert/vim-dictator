"""GTK-independent controller for a desktop dictation session."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Mapping

from vim_dictator_cli import DictatorError, runtime_directory


class DesktopBackend:
    def __init__(self, env: Mapping[str, str] | None = None):
        original = dict(os.environ if env is None else env)
        runtime_dir = runtime_directory(original, "linux") / "desktop"
        self.env = {
            **original,
            "VIM_DICTATOR_RUNTIME_DIR": str(runtime_dir),
            "VIM_DICTATOR_REQUEST_TIMEOUT": original.get("VIM_DICTATOR_REQUEST_TIMEOUT", "120"),
        }
        self.state_file = runtime_dir / "session.json"

    def has_session(self) -> bool:
        return self.state_file.is_file()

    def run(self, action: str) -> str:
        if action not in {"start", "stop", "cancel", "status"}:
            raise DictatorError("unsupported desktop action")
        command = [sys.executable, str(Path(__file__).resolve().with_name("vim_dictator_cli.py")), action]
        try:
            result = subprocess.run(command, env=self.env, capture_output=True, text=True, check=False)
        except OSError as error:
            raise DictatorError(self._safe_error(f"could not execute vim-dictator: {error}")) from None
        if result.returncode != 0:
            detail = result.stderr.strip() or f"vim-dictator exited with status {result.returncode}"
            raise DictatorError(self._safe_error(detail))
        return result.stdout.removesuffix("\n")

    def _safe_error(self, detail: str) -> str:
        key = self.env.get("OPENAI_API_KEY")
        return detail.replace(key, "[redacted]") if key else detail


def paste_shortcut(window_class: str) -> str:
    terminals = ("gnome-terminal", "konsole", "kitty", "alacritty", "tilix", "xfce4-terminal", "wezterm", "xterm")
    return "ctrl+shift+v" if any(terminal in window_class.lower() for terminal in terminals) else "ctrl+v"
