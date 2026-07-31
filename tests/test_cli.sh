#!/usr/bin/env bash

set -euo pipefail

project_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
command_path="$project_dir/bin/vim-dictator"
tmp_dir=$(mktemp -d)

cleanup() {
  rm -rf "$tmp_dir"
}
trap cleanup EXIT

fail() {
  printf 'FAIL: %s\n' "$*" >&2
  exit 1
}

assert_equals() {
  local actual=$1
  local expected=$2
  local message=$3

  [ "$actual" = "$expected" ] || fail "$message (got: $actual; expected: $expected)"
}

fake_bin="$tmp_dir/bin"
runtime_dir="$tmp_dir/runtime"
log_dir="$tmp_dir/log"
mkdir -p "$fake_bin" "$log_dir"

cat > "$fake_bin/pw-record" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
printf '%s\n' "$*" > "$TEST_LOG_DIR/pw-record.args"
for output_file; do :; done
printf 'RIFF' > "$output_file"
trap 'exit 0' INT TERM
while :; do sleep 1; done
EOF

cat > "$fake_bin/curl" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
printf '%s\n' "$*" > "$TEST_LOG_DIR/curl.args"
printf '%s\n' '{"text":"texto transcrito"}'
EOF

chmod +x "$fake_bin/pw-record" "$fake_bin/curl"

run_command() {
  PATH="$fake_bin:$PATH" \
    TEST_LOG_DIR="$log_dir" \
    VIM_DICTATOR_RUNTIME_DIR="$runtime_dir" \
    OPENAI_API_KEY="test-key" \
    "$command_path" "$@"
}

run_command_for_model() {
  local model=$1
  shift

  PATH="$fake_bin:$PATH" \
    TEST_LOG_DIR="$log_dir" \
    VIM_DICTATOR_RUNTIME_DIR="$runtime_dir" \
    VIM_DICTATOR_MODEL="$model" \
    OPENAI_API_KEY="test-key" \
    "$command_path" "$@"
}

run_command start
assert_equals "$(run_command status)" "recording" "status deve informar gravacao ativa"

output=$(run_command stop)
assert_equals "$output" "texto transcrito" "stop deve imprimir apenas a transcricao"
assert_equals "$(run_command status)" "idle" "stop deve limpar o estado"

grep -q -- '--rate 16000' "$log_dir/pw-record.args" || fail "gravador deve usar 16 kHz"
grep -q -- '--channels 1' "$log_dir/pw-record.args" || fail "gravador deve usar um canal"
grep -q -- 'model=gpt-transcribe' "$log_dir/curl.args" || fail "transcricao deve usar gpt-transcribe"
grep -q -- 'languages\[\]=pt' "$log_dir/curl.args" || fail "transcricao deve solicitar portugues"
if grep -q -- 'language=pt' "$log_dir/curl.args"; then
  fail "gpt-transcribe nao deve receber o campo language legado"
fi

run_command_for_model whisper-1 start
run_command_for_model whisper-1 stop >/dev/null
grep -q -- 'model=whisper-1' "$log_dir/curl.args" || fail "override deve usar o modelo solicitado"
grep -q -- 'language=pt' "$log_dir/curl.args" || fail "modelos legados devem receber o campo language"
if grep -q -- 'languages\[\]=pt' "$log_dir/curl.args"; then
  fail "modelos legados nao devem receber languages"
fi

run_command start
run_command cancel
assert_equals "$(run_command status)" "idle" "cancel deve limpar o estado"

if PATH="$fake_bin:$PATH" VIM_DICTATOR_RUNTIME_DIR="$runtime_dir" "$command_path" start >/dev/null 2>&1; then
  fail "start sem OPENAI_API_KEY deveria falhar"
fi

printf 'PASS: test_cli\n'
