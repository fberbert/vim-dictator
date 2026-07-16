# Vim Dictator

Ditado por voz para Neovim 0.9+ usando PipeWire e a API de transcricao da OpenAI.

O plugin nunca simula teclas no X11/Wayland. Ele insere a transcricao diretamente
no buffer do Neovim, na posicao onde a gravacao comecou.

## Dependencias

- Neovim 0.9+
- PipeWire com `pw-record`
- `curl` e `jq`
- Uma chave de API OpenAI

## Instalacao

```bash
cd ~/projetos/vim-dictator
chmod +x bin/vim-dictator install.sh tests/test_cli.sh
./install.sh

install -d -m 700 ~/.config/vim-dictator
printf '%s\n' 'OPENAI_API_KEY=sua_chave_aqui' > ~/.config/vim-dictator/env
chmod 600 ~/.config/vim-dictator/env
```

Reabra o Neovim depois da instalacao. O comando le a chave do ambiente ou de
`~/.config/vim-dictator/env`; nao coloque a chave em `init.lua`.

### NvChad / lazy.nvim

NvChad desabilita o carregamento de pacotes nativos do Neovim. Adicione este
bloco a `~/.config/nvim/lua/custom/plugins.lua` antes do `return plugins`:

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

## Uso

- `\\d`: inicia a gravacao; pressione novamente para parar e inserir a transcricao.
- `\\dc`: cancela e descarta a gravacao.
- `:VimDictatorToggle`, `:VimDictatorCancel` e `:VimDictatorStatus`: comandos equivalentes.

O microfone padrao atual do PipeWire e usado.

## Configuracao opcional

No `init.lua`, antes do carregamento do plugin, voce pode definir:

```lua
vim.g.vim_dictator_command = "/caminho/para/vim-dictator"
vim.g.vim_dictator_disable = true -- desabilita o carregamento automatico
```

Para termos tecnicos, defina `VIM_DICTATOR_PROMPT` no ambiente ou no seu launcher
do Neovim. O modelo padrao e `gpt-4o-transcribe`; para alterar, use
`VIM_DICTATOR_MODEL`.

## Testes

```bash
bash tests/test_cli.sh
nvim --headless -u NONE -n -l tests/test_plugin.lua
```

No Neovim em execucao, confirme a integracao com:

```vim
:verbose nmap \d
:VimDictatorStatus
```
