#!/usr/bin/env bash

set -euo pipefail

project_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
tmp_dir=$(mktemp -d)
trap 'rm -rf "$tmp_dir"' EXIT

fail() {
  printf 'FAIL: %s\n' "$*" >&2
  exit 1
}

fixture_dir="$tmp_dir/project with spaces"
test_home="$tmp_dir/home with spaces"
mkdir -p "$fixture_dir/bin" "$test_home"
cp "$project_dir/install.sh" "$fixture_dir/install.sh"
cp "$project_dir/bin/vim-dictator" "$project_dir/bin/vim_dictator_cli.py" "$fixture_dir/bin/"

env HOME="$test_home" bash "$fixture_dir/install.sh" > "$tmp_dir/install.log"
installed_command="$test_home/.local/bin/vim-dictator"
plugin_link="$test_home/.local/share/nvim/site/pack/vim-dictator/start/vim-dictator"
[ -L "$installed_command" ] || fail 'instalacao deve criar link do comando'
[ "$plugin_link" -ef "$fixture_dir" ] || fail 'instalacao deve criar link do plugin'

assert_help() {
  local command_path=$1
  local output
  output=$("$command_path" --help) || fail "--help deve funcionar via $command_path"
  [[ "$output" == *start*stop*cancel*status* ]] || fail '--help deve mostrar os comandos da CLI'
}

assert_help "$fixture_dir/bin/vim-dictator"
assert_help "$installed_command"

env HOME="$test_home" PATH="$test_home/.local/bin:$PATH" vim-dictator --help > "$tmp_dir/path-help"

mkdir -p "$tmp_dir/links with spaces"
ln -s '../project with spaces/bin/vim-dictator' "$tmp_dir/links with spaces/relative"
ln -s 'relative' "$tmp_dir/links with spaces/chained"
assert_help "$tmp_dir/links with spaces/relative"
assert_help "$tmp_dir/links with spaces/chained"

if env HOME="$test_home" VIM_DICTATOR_RUNTIME_DIR="$tmp_dir/runtime" \
  "$installed_command" 'invalid command with spaces' > "$tmp_dir/invalid.out" 2>&1; then
  fail 'wrapper deve propagar erro de argumento invalido'
else
  [ "$?" -eq 64 ] || fail 'wrapper deve preservar codigo de saida da CLI'
fi

printf 'PASS: test_install\n'
