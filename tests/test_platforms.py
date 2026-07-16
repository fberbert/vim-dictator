#!/usr/bin/env python3

import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "bin"))

from vim_dictator_cli import RecorderConfigurationError, recorder_command


class RecorderCommandTests(unittest.TestCase):
    def test_linux_uses_pipewire(self):
        command = recorder_command("linux", Path("/tmp/recording.wav"), {})

        self.assertEqual(
            command,
            ["pw-record", "--rate", "16000", "--channels", "1", "--format", "s16", "/tmp/recording.wav"],
        )

    def test_macos_uses_avfoundation_default_microphone(self):
        command = recorder_command("darwin", Path("/tmp/recording.wav"), {})

        self.assertEqual(
            command,
            [
                "ffmpeg",
                "-nostdin",
                "-hide_banner",
                "-loglevel",
                "error",
                "-f",
                "avfoundation",
                "-i",
                ":default",
                "-ac",
                "1",
                "-ar",
                "16000",
                "-c:a",
                "pcm_s16le",
                "/tmp/recording.wav",
            ],
        )

    def test_macos_accepts_selected_audio_device(self):
        command = recorder_command(
            "darwin",
            Path("/tmp/recording.wav"),
            {"VIM_DICTATOR_AUDIO_DEVICE": "2"},
        )

        self.assertIn(":2", command)

    def test_windows_requires_explicit_microphone_name(self):
        with self.assertRaisesRegex(RecorderConfigurationError, "VIM_DICTATOR_AUDIO_DEVICE"):
            recorder_command("win32", Path("C:/temp/recording.wav"), {})

    def test_windows_uses_directshow_with_selected_microphone(self):
        command = recorder_command(
            "win32",
            Path("C:/temp/recording.wav"),
            {"VIM_DICTATOR_AUDIO_DEVICE": "Microphone (USB Audio Device)"},
        )

        self.assertEqual(command[0], "ffmpeg")
        self.assertIn("dshow", command)
        self.assertIn("audio=Microphone (USB Audio Device)", command)


if __name__ == "__main__":
    unittest.main(verbosity=2)
