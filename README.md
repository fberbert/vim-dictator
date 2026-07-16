# Vim Dictator

Voice dictation for Neovim 0.9+ using PipeWire and the OpenAI transcription API.

The plugin never simulates X11 or Wayland keystrokes. It inserts the returned
transcription directly into the Neovim buffer at the cursor position where
recording started.

## Requirements

- Neovim 0.9+
- PipeWire with `pw-record`
- `curl` and `jq`
- An OpenAI API key

## Installation

```bash
cd ~/projetos/vim-dictator
chmod +x bin/vim-dictator install.sh tests/test_cli.sh
./install.sh

install -d -m 700 ~/.config/vim-dictator
printf '%s\n' 'OPENAI_API_KEY=your_api_key' > ~/.config/vim-dictator/env
chmod 600 ~/.config/vim-dictator/env
```

Restart Neovim after installation. The command reads the API key from the
environment or `~/.config/vim-dictator/env`; do not put the key in `init.lua`.

### NvChad / lazy.nvim

NvChad disables Neovim's native package loading. Add this entry to
`~/.config/nvim/lua/custom/plugins.lua` before `return plugins`:

```lua
{
  dir = vim.fn.expand "~/projetos/vim-dictator",
  name = "vim-dictator",
  lazy = false,
  init = function()
    vim.g.vim_dictator_disable = true
  end,
  config = function()
    require("vim_dictator").setup {
      command = vim.fn.expand "~/projetos/vim-dictator/bin/vim-dictator",
    }
  end,
},
```

## Usage

- `Ctrl-D`: start recording. Press it again to stop and insert the transcription.
- `Ctrl-D`, then `c`: cancel and discard the current recording.
- `:VimDictatorToggle`, `:VimDictatorCancel`, and `:VimDictatorStatus`: equivalent commands.

The plugin uses the current PipeWire default microphone. Because the cancel
shortcut begins with the toggle shortcut, press `c` immediately after `Ctrl-D`.

## Optional configuration

Before the plugin is loaded, you can set these values in `init.lua`:

```lua
vim.g.vim_dictator_command = "/path/to/vim-dictator"
vim.g.vim_dictator_disable = true -- disable automatic package loading
```

Set `VIM_DICTATOR_PROMPT` in the environment or your Neovim launcher to provide
domain vocabulary. The default model is `gpt-4o-transcribe`; override it with
`VIM_DICTATOR_MODEL`.

## Tests

```bash
bash tests/test_cli.sh
nvim --headless -u NONE -n -l tests/test_plugin.lua
```

In Neovim, verify the mappings and state with:

```vim
:verbose nmap <C-d>
:VimDictatorStatus
```
