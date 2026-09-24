#!/usr/bin/env bash

set -euo pipefail

project_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
python3 - "$project_dir" <<'PY'
import os
from pathlib import Path
import sys
import tempfile

project = Path(sys.argv[1])
home = Path.home()
command = home / ".local/bin/vim-dictator-x"
target = project / "bin/vim-dictator-x"
data_home = Path(os.environ.get("XDG_DATA_HOME") or home / ".local/share")
launcher = data_home / "applications/vim-dictator-x.desktop"
marker = "X-Vim-Dictator-Managed=true"

if not target.is_file():
    sys.exit(f"Missing desktop command: {target}")
if command.is_symlink():
    if command.resolve() != target.resolve():
        sys.exit(f"Refusing to replace an unrelated symlink: {command}")
elif command.exists():
    sys.exit(f"Refusing to replace an existing file: {command}")
if launcher.is_symlink() or (launcher.exists() and (
    not launcher.is_file() or marker not in launcher.read_text(encoding="utf-8").splitlines()
)):
    sys.exit(f"Refusing to replace an unmanaged launcher: {launcher}")

# Exec quoting is applied before the Desktop Entry string escaping layer.
# Percent is a field-code escape, independent of shell-style quoting.
quoted = str(command).replace("%", "%%")
quoted = "".join("\\" + char if char in '\\"`$' else char for char in quoted)
exec_value = ('"' + quoted + '"').replace("\\", "\\\\")
exec_value = exec_value.replace("\n", "\\n").replace("\r", "\\r").replace("\t", "\\t")
content = "\n".join([
    "[Desktop Entry]",
    "Type=Application",
    "Name=Vim Dictator",
    "Comment=Ditado por voz na bandeja",
    f"Exec={exec_value}",
    "Icon=audio-input-microphone",
    "Terminal=false",
    "Categories=Utility;",
    marker,
    "",
])
command.parent.mkdir(parents=True, exist_ok=True)
launcher.parent.mkdir(parents=True, exist_ok=True)
if not command.is_symlink():
    command.symlink_to(target)
with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=launcher.parent, delete=False) as file:
    file.write(content)
    temporary = Path(file.name)
try:
    temporary.chmod(0o644)
    temporary.replace(launcher)
finally:
    temporary.unlink(missing_ok=True)
print(f"Installed:\n  {command}\n  {launcher}")
PY
