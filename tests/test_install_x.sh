#!/usr/bin/env bash
set -euo pipefail

project_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
/usr/bin/python3 - "$project_dir" <<'PY'
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

from gi.repository import GLib

source = Path(sys.argv[1])
assert (source / "install-x.sh").is_file(), "desktop installer must exist"

with tempfile.TemporaryDirectory() as directory:
    root = Path(directory)
    fixture = root / 'project spaces "quotes" %f $dollar `backtick` \\slash'
    fixture.mkdir()
    shutil.copytree(source / "bin", fixture / "bin")
    shutil.copy2(source / "install-x.sh", fixture / "install-x.sh")
    home = root / 'home spaces "quotes" %f $dollar `backtick` \\slash'
    home.mkdir()
    config = home / ".config/vim-dictator/env"
    config.parent.mkdir(parents=True)
    config.write_text("personal configuration\n")
    config.chmod(0o600)
    unrelated = home / ".local/bin/other-command"
    unrelated.parent.mkdir(parents=True)
    unrelated.write_text("keep me")
    env = {**os.environ, "HOME": str(home), "XDG_DATA_HOME": str(root / "custom data")}

    def install(environment=env, success=True):
        result = subprocess.run(["bash", str(fixture / "install-x.sh")], env=environment, capture_output=True, text=True)
        assert (result.returncode == 0) == success, result.stdout + result.stderr

    install()
    command = home / ".local/bin/vim-dictator-x"
    launcher = Path(env["XDG_DATA_HOME"]) / "applications/vim-dictator-x.desktop"
    assert command.is_symlink() and command.resolve() == fixture / "bin/vim-dictator-x"
    result = subprocess.run([str(command), "--help"], env=env, capture_output=True, text=True)
    assert result.returncode == 0 and "--hotkey" in result.stdout, result.stderr
    keyfile = GLib.KeyFile()
    keyfile.load_from_file(str(launcher), GLib.KeyFileFlags.NONE)
    for key, expected in {"Type": "Application", "Name": "Vim Dictator", "Icon": "audio-input-microphone", "Terminal": "false", "Categories": "Utility;"}.items():
        assert keyfile.get_string("Desktop Entry", key) == expected
    assert "ditado" in keyfile.get_string("Desktop Entry", "Comment").lower()
    valid, argv = GLib.shell_parse_argv(keyfile.get_string("Desktop Entry", "Exec"))
    assert valid and len(argv) == 1 and argv[0].replace("%%", "%") == str(command), argv
    assert "%%f" in argv[0], "literal percent must not become a field code"
    before = launcher.read_bytes()
    install()
    assert launcher.read_bytes() == before
    assert config.read_text() == "personal configuration\n" and config.stat().st_mode & 0o777 == 0o600
    assert unrelated.read_text() == "keep me"
    assert not (home / ".config/autostart").exists()
    assert not (home / ".local/share/nvim").exists()

    default_home = root / "default-home"
    default_env = {key: value for key, value in os.environ.items() if key != "XDG_DATA_HOME"}
    install({**default_env, "HOME": str(default_home)})
    assert (default_home / ".local/share/applications/vim-dictator-x.desktop").is_file()

    command.unlink()
    command.write_text("unmanaged executable")
    install(success=False)
    assert command.read_text() == "unmanaged executable" and launcher.read_bytes() == before
    command.unlink()
    command.symlink_to(unrelated)
    install(success=False)
    assert command.resolve() == unrelated
    command.unlink()
    command.symlink_to(fixture / "bin/vim-dictator-x")
    launcher.write_text("[Desktop Entry]\nName=Personal launcher\n")
    install(success=False)
    assert launcher.read_text() == "[Desktop Entry]\nName=Personal launcher\n"

print("PASS: test_install_x")
PY
