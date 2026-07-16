#!/usr/bin/env bash

set -euo pipefail

project_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
bin_dir="$HOME/.local/bin"
plugin_dir="$HOME/.local/share/nvim/site/pack/vim-dictator/start"
plugin_link="$plugin_dir/vim-dictator"

mkdir -p "$bin_dir" "$plugin_dir"
ln -sfn "$project_dir/bin/vim-dictator" "$bin_dir/vim-dictator"
ln -sfn "$project_dir" "$plugin_link"

printf 'Instalado:\n  %s\n  %s\n' "$bin_dir/vim-dictator" "$plugin_link"
printf 'Crie %s/.config/vim-dictator/env com OPENAI_API_KEY=... e permissao 600.\n' "$HOME"
