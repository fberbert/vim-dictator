# Vim Dictator

Voice dictation for Neovim 0.9+ using the OpenAI transcription API.

The Neovim plugin inserts the returned text directly into the buffer. It never
simulates X11, Wayland, macOS, or Windows keyboard input.

There is also an optional Ubuntu X11 tray application, `vim-dictator-x`, which
transcribes and pastes into the application currently in focus.

## Platform support

| Platform | Recorder | Microphone selection |
| --- | --- | --- |
| Linux | PipeWire `pw-record` | Default source, or `VIM_DICTATOR_AUDIO_TARGET` |
| macOS | FFmpeg AVFoundation | Default microphone, or `VIM_DICTATOR_AUDIO_DEVICE` |
| Windows | FFmpeg DirectShow | `VIM_DICTATOR_AUDIO_DEVICE` is required |

All platforms require Python 3.10+, `curl`, and an OpenAI API key. macOS and
Windows also require FFmpeg with the AVFoundation or DirectShow input device.

## Installation

### Linux and macOS

```bash
git clone https://github.com/fberbert/vim-dictator.git
cd vim-dictator
./install.sh
```

Create the API-key file:

```bash
install -d -m 700 ~/.config/vim-dictator
printf '%s\n' 'OPENAI_API_KEY=your_api_key' > ~/.config/vim-dictator/env
chmod 600 ~/.config/vim-dictator/env
```

### Windows

In PowerShell:

```powershell
git clone https://github.com/fberbert/vim-dictator.git
cd vim-dictator
Set-ExecutionPolicy -Scope Process Bypass
.\install.ps1

New-Item -ItemType Directory -Force "$env:APPDATA\vim-dictator"
Set-Content "$env:APPDATA\vim-dictator\env" 'OPENAI_API_KEY=your_api_key'
```

The Windows installer copies the plugin into Neovim's standard data directory,
so run `git pull` followed by `.\install.ps1` when updating it.

### NvChad / lazy.nvim

NvChad disables Neovim's native package loading. Add this entry to
`~/.config/nvim/lua/custom/plugins.lua` before `return plugins`:

```lua
{
  dir = vim.fn.stdpath("data") .. "/site/pack/vim-dictator/start/vim-dictator",
  name = "vim-dictator",
  lazy = false,
  init = function()
    vim.g.vim_dictator_disable = true
  end,
  config = function()
    require("vim_dictator").setup()
  end,
},
```

Restart Neovim after installation. The plugin locates its installed command
automatically; do not put API keys in `init.lua`.

## Usage

- `Ctrl-D`: start recording. Press it again to stop and insert the transcription.
- `Ctrl-D`, then `c`: cancel and discard the current recording.
- `:VimDictatorToggle`, `:VimDictatorCancel`, and `:VimDictatorStatus`: equivalent commands.

Because the cancel shortcut begins with the toggle shortcut, press `c`
immediately after `Ctrl-D`.

The insertion point follows edits in the original buffer while recording or
transcribing. If you delete that position, text is inserted at the remaining
position (at the end of the buffer when its last line was removed). Closing or
unloading the original buffer, or making it non-modifiable, discards the result
with a warning and releases the session.

## Audio devices

```bash
vim-dictator devices
```

On macOS, set `VIM_DICTATOR_AUDIO_DEVICE` to the AVFoundation device name or
index reported by this command. On Windows, set it to the exact DirectShow
microphone name before starting Neovim. For example, in PowerShell:

```powershell
setx VIM_DICTATOR_AUDIO_DEVICE 'Microphone (USB Audio Device)'
```

## Ubuntu tray application

This separate executable uses the same microphone backend, API key and model
configuration as the Neovim plugin. Its recording state is isolated, so the
two interfaces do not stop or discard each other's recordings.

Install the Ubuntu dependencies and the desktop launcher:

```bash
sudo apt install python3-gi gir1.2-gtk-3.0 gir1.2-ayatanaappindicator3-0.1 \
  gir1.2-keybinder-3.0 xdotool x11-utils pipewire-bin curl
./install-x.sh
```

Open **Vim Dictator** from the applications menu, or run:

```bash
./bin/vim-dictator-x
```

- **Ctrl+Alt+Space** starts recording. Press it again to stop, transcribe and paste.
- The tray menu also provides start/stop, cancel, copy the last transcription and exit.
- The icon shows **Gravando** while the microphone is recording.
- Paste goes to the field focused **when transcription finishes**. Keep the intended
  field focused while waiting. Text replaces the clipboard contents; common terminals
  receive `Ctrl+Shift+V`, and other applications receive `Ctrl+V`.
- If transcription fails, retry or cancel through the menu. If automatic paste fails,
  use **Copiar última transcrição** and paste manually.
- Exiting discards an active recording. If an operation is running, exit waits for it
  to finish before cleaning up; the tray remains responsive. The desktop API request
  timeout defaults to 120 seconds (`VIM_DICTATOR_REQUEST_TIMEOUT`, >0 and <=3600).
  Exiting before automatic paste starts cancels that insertion; an already running
  paste is allowed to finish.

To choose a different global shortcut, use GTK accelerator notation:

```bash
vim-dictator-x --hotkey '<Super><Shift>d'
vim-dictator-x --no-hotkey
```

If another application owns the shortcut, the tray reports it and its menu remains
usable. Only one tray instance can run for the same runtime directory. The installer
adds a launcher; it does not enable automatic startup or change GNOME keybindings.

Automatic insertion currently requires **Ubuntu on Xorg (X11)**. Wayland sessions
are rejected with an explanation. Custom paste bindings, terminal applications such
as Vim, and embedded terminals may require manual paste or their own configuration.
The tray uses Ubuntu's `/usr/bin/python3` to access the system GTK packages.

## Optional configuration

Set `VIM_DICTATOR_PROMPT` to provide domain vocabulary. The default model is
`gpt-transcribe`; override it with `VIM_DICTATOR_MODEL`.

Native package loading uses the bundled command automatically. To override it,
set `vim.g.vim_dictator_command` before the plugin loads. When calling
`require("vim_dictator").setup()` yourself, pass `{ command = "/path/to/command" }`.

## Tests

```bash
python3 -m unittest tests/test_platforms.py -v
bash tests/test_cli.sh
bash tests/test_install.sh
nvim --headless -u NONE -n -l tests/test_plugin.lua
nvim --headless -u NONE -n -l tests/test_loader.lua
nvim --headless -u NONE -n -l tests/test_buffer_edits.lua
python3 -m unittest tests/test_desktop.py -v
bash tests/test_install_x.sh
```

GUI tests must run in a private display and D-Bus session so that they do not
alter your desktop focus or clipboard. With `xvfb` installed:

```bash
xvfb-run -a dbus-run-session -- env VIM_DICTATOR_TEST_DISPLAY=1 \
  XDG_SESSION_TYPE=x11 /usr/bin/python3 -m unittest \
  tests/test_tray.py tests/test_tray_e2e.py tests/test_terminal_paste.py \
  tests/test_tray_responsiveness.py -v
```

The end-to-end test uses real GTK widgets, the global hotkey and X11 paste, with
fake microphone and API commands. It does not record audio or send API requests.
When GNOME Terminal is installed, the terminal test also verifies that its real
`Ctrl+Shift+V` action receives the clipboard text in a terminal child process.
The responsiveness tests use keyboard and mouse events while transcription and
paste operations are deliberately delayed.
