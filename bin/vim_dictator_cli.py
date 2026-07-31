#!/usr/bin/env python3

"""Record microphone audio and transcribe it through the OpenAI API."""

from __future__ import annotations

import json
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterator, Mapping, Sequence


class DictatorError(Exception):
    """A user-actionable command error."""


class RecorderConfigurationError(DictatorError):
    """The selected platform has no usable microphone configuration."""


@dataclass(frozen=True)
class Session:
    pid: int
    audio_file: str
    platform: str


def normalize_platform(value: str | None = None) -> str:
    value = (value or sys.platform).lower()
    if value.startswith("linux"):
        return "linux"
    if value.startswith("darwin"):
        return "darwin"
    if value.startswith(("win", "cygwin", "msys")):
        return "win32"
    raise RecorderConfigurationError(f"unsupported operating system: {value}")


def configured_path(value: str | None, fallback: Path) -> Path:
    return Path(value).expanduser() if value else fallback


def runtime_directory(env: Mapping[str, str], platform_name: str) -> Path:
    override = env.get("VIM_DICTATOR_RUNTIME_DIR")
    if override:
        return Path(override).expanduser()

    if platform_name == "win32":
        base = Path(env.get("LOCALAPPDATA", tempfile.gettempdir()))
        return base / "vim-dictator" / "runtime"

    base = Path(env.get("XDG_RUNTIME_DIR", tempfile.gettempdir()))
    return base / f"vim-dictator-{os.getuid()}"


def configuration_file(env: Mapping[str, str], platform_name: str) -> Path:
    override = env.get("VIM_DICTATOR_ENV_FILE")
    if override:
        return Path(override).expanduser()

    if platform_name == "win32":
        return Path(env.get("APPDATA", Path.home() / "AppData" / "Roaming")) / "vim-dictator" / "env"

    config_home = Path(env.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    return config_home / "vim-dictator" / "env"


def recorder_command(platform_name: str, audio_file: Path, env: Mapping[str, str]) -> list[str]:
    if platform_name == "linux":
        command = [env.get("VIM_DICTATOR_RECORDER", "pw-record")]
        if target := env.get("VIM_DICTATOR_AUDIO_TARGET"):
            command.extend(["--target", target])
        return command + ["--rate", "16000", "--channels", "1", "--format", "s16", str(audio_file)]

    ffmpeg = env.get("VIM_DICTATOR_FFMPEG", "ffmpeg")
    if platform_name == "darwin":
        device = env.get("VIM_DICTATOR_AUDIO_DEVICE", "default")
        audio_input = device if device.startswith(":") else f":{device}"
        return [
            ffmpeg,
            "-nostdin",
            "-hide_banner",
            "-loglevel",
            "error",
            "-f",
            "avfoundation",
            "-i",
            audio_input,
            "-ac",
            "1",
            "-ar",
            "16000",
            "-c:a",
            "pcm_s16le",
            str(audio_file),
        ]

    if platform_name == "win32":
        device = env.get("VIM_DICTATOR_AUDIO_DEVICE")
        if not device:
            raise RecorderConfigurationError(
                "Windows requires VIM_DICTATOR_AUDIO_DEVICE. Run 'vim-dictator devices' to list microphones."
            )
        return [
            ffmpeg,
            "-nostdin",
            "-hide_banner",
            "-loglevel",
            "error",
            "-f",
            "dshow",
            "-i",
            f"audio={device}",
            "-ac",
            "1",
            "-ar",
            "16000",
            "-c:a",
            "pcm_s16le",
            str(audio_file),
        ]

    raise RecorderConfigurationError(f"unsupported operating system: {platform_name}")


class Dictator:
    def __init__(self, env: Mapping[str, str] | None = None, platform_value: str | None = None):
        self.env = dict(os.environ if env is None else env)
        self.platform = normalize_platform(platform_value or self.env.get("VIM_DICTATOR_PLATFORM_OVERRIDE"))
        self.runtime_dir = runtime_directory(self.env, self.platform)
        self.state_file = self.runtime_dir / "session.json"
        self.lock_dir = self.runtime_dir / ".lock"
        self.env_file = configuration_file(self.env, self.platform)

    def ensure_runtime_dir(self) -> None:
        self.runtime_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
        if self.platform != "win32":
            self.runtime_dir.chmod(0o700)

    @contextmanager
    def lock(self) -> Iterator[None]:
        self.ensure_runtime_dir()
        deadline = time.monotonic() + 5
        while True:
            try:
                self.lock_dir.mkdir()
                break
            except FileExistsError:
                if time.monotonic() >= deadline:
                    raise DictatorError("another vim-dictator operation is in progress")
                time.sleep(0.1)

        try:
            yield
        finally:
            self.lock_dir.rmdir() if self.lock_dir.exists() else None

    def api_key(self) -> str:
        if key := self.env.get("OPENAI_API_KEY"):
            return key

        try:
            with self.env_file.open(encoding="utf-8") as file:
                for line in file:
                    if line.startswith("OPENAI_API_KEY="):
                        key = line.partition("=")[2].strip()
                        if key:
                            return key
        except FileNotFoundError:
            pass

        raise DictatorError(f"OPENAI_API_KEY is not set. Use the environment or {self.env_file}.")

    def require_executable(self, command: str) -> None:
        if Path(command).is_file() or shutil.which(command):
            return
        raise DictatorError(f"required command not found: {command}")

    def load_session(self) -> Session | None:
        try:
            payload = json.loads(self.state_file.read_text(encoding="utf-8"))
            return Session(**payload)
        except FileNotFoundError:
            return None
        except (json.JSONDecodeError, TypeError, ValueError) as error:
            raise DictatorError(f"invalid recording state: {self.state_file}") from error

    def save_session(self, session: Session) -> None:
        self.ensure_runtime_dir()
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=self.runtime_dir, delete=False) as file:
            json.dump(asdict(session), file)
            temporary_path = Path(file.name)
        temporary_path.replace(self.state_file)

    def clear_session(self) -> None:
        self.state_file.unlink(missing_ok=True)

    @staticmethod
    def process_is_running(pid: int) -> bool:
        try:
            os.kill(pid, 0)
        except OSError:
            return False
        return True

    def stop_process(self, session: Session) -> None:
        if not self.process_is_running(session.pid):
            return

        try:
            if self.platform == "win32" and hasattr(signal, "CTRL_BREAK_EVENT"):
                os.kill(session.pid, signal.CTRL_BREAK_EVENT)
            else:
                os.kill(session.pid, signal.SIGTERM)
        except OSError as error:
            raise DictatorError("could not stop the recorder") from error

        deadline = time.monotonic() + 5
        used_fallback = False
        while self.process_is_running(session.pid):
            if time.monotonic() >= deadline:
                if used_fallback:
                    raise DictatorError("the recorder did not exit in time")
                try:
                    os.kill(session.pid, signal.SIGTERM)
                except OSError:
                    return
                used_fallback = True
                deadline = time.monotonic() + 1
            time.sleep(0.05)

    def start(self) -> None:
        self.api_key()
        existing = self.load_session()
        if existing:
            if self.process_is_running(existing.pid):
                raise DictatorError("a recording is already in progress")
            Path(existing.audio_file).unlink(missing_ok=True)
            self.clear_session()

        self.ensure_runtime_dir()
        audio_file = self.runtime_dir / f"recording-{time.time_ns()}-{os.getpid()}.wav"
        command = recorder_command(self.platform, audio_file, self.env)
        self.require_executable(command[0])

        popen_options: dict[str, object] = {
            "stdin": subprocess.DEVNULL,
            "stdout": subprocess.DEVNULL,
            "stderr": subprocess.DEVNULL,
        }
        if self.platform == "win32":
            popen_options["creationflags"] = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        else:
            popen_options["start_new_session"] = True

        process = subprocess.Popen(command, **popen_options)
        time.sleep(0.1)
        if process.poll() is not None:
            audio_file.unlink(missing_ok=True)
            raise DictatorError("the recorder exited immediately")

        self.save_session(Session(pid=process.pid, audio_file=str(audio_file), platform=self.platform))

    def transcribe(self, audio_file: Path) -> str:
        if not audio_file.is_file() or audio_file.stat().st_size == 0:
            raise DictatorError(f"audio file is missing or empty: {audio_file}")

        curl = self.env.get("VIM_DICTATOR_CURL", "curl")
        self.require_executable(curl)
        model = self.env.get("VIM_DICTATOR_MODEL", "gpt-transcribe")
        command = [
            curl,
            "--fail",
            "--silent",
            "--show-error",
            "--request",
            "POST",
            "--url",
            "https://api.openai.com/v1/audio/transcriptions",
            "--header",
            f"Authorization: Bearer {self.api_key()}",
            "--form",
            f"file=@{audio_file}",
            "--form",
            f"model={model}",
            "--form",
            "response_format=json",
            "--form",
            "languages[]=pt" if model == "gpt-transcribe" else "language=pt",
        ]
        if prompt := self.env.get("VIM_DICTATOR_PROMPT"):
            command.extend(["--form", f"prompt={prompt}"])

        response = subprocess.run(command, text=True, capture_output=True, check=False)
        if response.returncode != 0:
            detail = response.stderr.strip() or "unknown curl error"
            raise DictatorError(f"OpenAI transcription failed: {detail}")

        try:
            payload = json.loads(response.stdout)
            text = payload.get("text")
        except (json.JSONDecodeError, AttributeError) as error:
            raise DictatorError("invalid transcription response") from error
        if not isinstance(text, str):
            raise DictatorError("transcription response did not contain text")
        return text

    def stop(self) -> str:
        session = self.load_session()
        if not session:
            raise DictatorError("no recording is active")
        self.stop_process(session)
        text = self.transcribe(Path(session.audio_file))
        Path(session.audio_file).unlink(missing_ok=True)
        self.clear_session()
        return text

    def cancel(self) -> None:
        session = self.load_session()
        if not session:
            return
        self.stop_process(session)
        Path(session.audio_file).unlink(missing_ok=True)
        self.clear_session()

    def status(self) -> str:
        session = self.load_session()
        return "recording" if session and self.process_is_running(session.pid) else "idle"

    def devices(self) -> int:
        if self.platform == "linux":
            command: Sequence[str] = [self.env.get("VIM_DICTATOR_PACTL", "pactl"), "list", "short", "sources"]
        elif self.platform == "darwin":
            command = [self.env.get("VIM_DICTATOR_FFMPEG", "ffmpeg"), "-f", "avfoundation", "-list_devices", "true", "-i", ""]
        else:
            command = [self.env.get("VIM_DICTATOR_FFMPEG", "ffmpeg"), "-list_devices", "true", "-f", "dshow", "-i", "dummy"]
        self.require_executable(command[0])
        return subprocess.run(command, check=False).returncode


USAGE = """Usage: vim-dictator <start|stop|cancel|status|devices>

start    Record from the platform microphone backend.
stop     Stop, transcribe with OpenAI, and print the text.
cancel   Stop and discard the current recording.
status   Print recording or idle.
devices  List available audio input devices.
"""


def main(arguments: Sequence[str] | None = None) -> int:
    arguments = list(sys.argv[1:] if arguments is None else arguments)
    if len(arguments) != 1 or arguments[0] in {"-h", "--help", "help"}:
        print(USAGE, end="" if arguments else "", file=sys.stdout if arguments else sys.stderr)
        return 0 if arguments else 64

    try:
        dictator = Dictator()
        command = arguments[0]
        if command == "start":
            with dictator.lock():
                dictator.start()
        elif command == "stop":
            with dictator.lock():
                print(dictator.stop())
        elif command == "cancel":
            with dictator.lock():
                dictator.cancel()
        elif command == "status":
            print(dictator.status())
        elif command == "devices":
            return dictator.devices()
        else:
            print(USAGE, end="", file=sys.stderr)
            return 64
        return 0
    except DictatorError as error:
        print(f"vim-dictator: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
