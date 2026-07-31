# Vim Dictator

Voice dictation for Neovim 0.9+ using the OpenAI transcription API.

The plugin inserts the returned text directly into the Neovim buffer. It never
simulates X11, Wayland, macOS, or Windows keyboard input.

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

## Optional configuration

Set `VIM_DICTATOR_PROMPT` to provide domain vocabulary. The default model is
`gpt-transcribe`; override it with `VIM_DICTATOR_MODEL`.

## Tests

```bash
python3 -m unittest tests/test_platforms.py -v
bash tests/test_cli.sh
nvim --headless -u NONE -n -l tests/test_plugin.lua
```
