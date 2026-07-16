local project_dir = vim.fn.getcwd()
vim.opt.runtimepath:prepend(project_dir)

local temp_dir = vim.fn.tempname()
vim.fn.mkdir(temp_dir, "p")
local fake_command = temp_dir .. "/vim-dictator"

local handle = assert(io.open(fake_command, "w"))
handle:write([[#!/usr/bin/env sh
case "$1" in
  start) exit 0 ;;
  stop)
    [ "${VIM_DICTATOR_TEST_FAIL_STOP:-}" = 1 ] && exit 1
    printf 'texto inserido\nsegunda linha\n'
    exit 0
    ;;
  cancel) exit 0 ;;
  status) printf 'idle\n' ; exit 0 ;;
esac
exit 64
]])
handle:close()
vim.fn.system({ "chmod", "+x", fake_command })

local dictator = require("vim_dictator")
dictator.setup({ command = fake_command, map_keys = false })

dictator.setup({ command = fake_command })
assert(vim.fn.maparg("<C-d>", "n") ~= "", "Control+D must toggle dictation")
assert(vim.fn.maparg("<C-d>c", "n") ~= "", "Control+D followed by c must cancel dictation")

vim.api.nvim_buf_set_lines(0, 0, -1, false, { "antes.depois" })
vim.api.nvim_win_set_cursor(0, { 1, 6 })
dictator.toggle()
assert(vim.wait(1000, function()
  return dictator.status() == "recording"
end), "plugin deve entrar no estado recording")

dictator.toggle()
assert(vim.wait(1000, function()
  return dictator.status() == "idle"
end), "plugin deve retornar ao estado idle")

local resulting_lines = vim.api.nvim_buf_get_lines(0, 0, -1, false)
assert(resulting_lines[1] == "antes.texto inserido", "plugin deve inserir o texto no buffer; obtido: " .. vim.inspect(resulting_lines))
assert(resulting_lines[2] == "segunda linhadepois", "plugin deve preservar quebras de linha; obtido: " .. vim.inspect(resulting_lines))

dictator.toggle()
assert(vim.wait(1000, function()
  return dictator.status() == "recording"
end), "segunda gravacao deve iniciar")
dictator.cancel()
assert(vim.wait(1000, function()
  return dictator.status() == "idle"
end), "cancel deve retornar ao estado idle")

vim.env.VIM_DICTATOR_TEST_FAIL_STOP = "1"
dictator.toggle()
assert(vim.wait(1000, function()
  return dictator.status() == "recording"
end), "gravacao para falha deve iniciar")
dictator.toggle()
assert(vim.wait(1000, function()
  return dictator.status() == "recording"
end), "falha de transcricao deve permitir nova tentativa ou cancelamento")
vim.env.VIM_DICTATOR_TEST_FAIL_STOP = nil
dictator.cancel()
assert(vim.wait(1000, function()
  return dictator.status() == "idle"
end), "cancel deve limpar sessao apos falha")

vim.fn.delete(temp_dir, "rf")
print("PASS: test_plugin")
