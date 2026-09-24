vim.opt.runtimepath:prepend(vim.fn.getcwd())
local temp_dir = vim.fn.tempname()
vim.fn.mkdir(temp_dir, "p")
local command = temp_dir .. "/dictator"
vim.fn.writefile({
  "#!/bin/sh",
  '[ "${VIM_DICTATOR_TEST_FAIL_COMMAND:-}" = "$1" ] && exit 1',
  'if [ "$1" = stop ]; then printf "ditado\\n"; fi',
  "exit 0",
}, command)
vim.fn.setfperm(command, "rwx------")
vim.env.VIM_DICTATOR_TEST_FAIL_COMMAND = nil

local messages = {}
vim.notify = function(message) table.insert(messages, message) end
local dictator = require("vim_dictator")
dictator.setup({ command = command, map_keys = false })

local function wait_for(phase)
  assert(vim.wait(2000, function() return dictator.status() == phase end), "expected phase " .. phase)
end

local function record(lines, cursor)
  messages = {}
  local buffer = vim.api.nvim_create_buf(false, true)
  vim.api.nvim_set_current_buf(buffer)
  vim.api.nvim_buf_set_lines(buffer, 0, -1, false, lines)
  vim.api.nvim_win_set_cursor(0, cursor)
  dictator.start()
  wait_for("recording")
  return buffer
end

local function finish(buffer, expected)
  dictator.stop()
  wait_for("idle")
  local actual = vim.api.nvim_buf_get_lines(buffer, 0, -1, false)
  assert(vim.deep_equal(actual, expected), "unexpected insertion: " .. vim.inspect(actual))
  assert(#vim.api.nvim_buf_get_extmarks(buffer, -1, 0, -1, {}) == 0, "finished session leaked a mark")
  vim.api.nvim_buf_delete(buffer, { force = true })
end

local ok, error_message = pcall(function()
  local buffer = record({ "primeira", "antes.depois" }, { 2, 6 })
  vim.api.nvim_buf_set_lines(buffer, 0, 0, false, { "nova" })
  finish(buffer, { "nova", "primeira", "antes.ditadodepois" })

  buffer = record({ "antes.depois" }, { 1, 6 })
  vim.api.nvim_buf_set_text(buffer, 0, 0, 0, 0, { "prefixo " })
  finish(buffer, { "prefixo antes.ditadodepois" })

  buffer = record({ "antes.depois" }, { 1, 6 })
  vim.api.nvim_buf_set_text(buffer, 0, 0, 0, 6, {})
  finish(buffer, { "ditadodepois" })

  buffer = record({ "primeira", "segunda" }, { 2, 3 })
  vim.api.nvim_buf_set_lines(buffer, 1, 2, false, {})
  finish(buffer, { "primeiraditado" })

  buffer = record({ "primeira", "segunda" }, { 2, 3 })
  vim.api.nvim_buf_set_lines(buffer, 0, -1, false, {})
  finish(buffer, { "ditado" })

  buffer = record({ "original" }, { 1, 0 })
  local other = vim.api.nvim_create_buf(false, true)
  vim.api.nvim_set_current_buf(other)
  finish(buffer, { "ditadooriginal" })
  assert(vim.api.nvim_buf_get_lines(other, 0, -1, false)[1] == "", "modified a different buffer")

  for _, action in ipairs({ "closed", "unloaded", "readonly" }) do
    buffer = record({ "original" }, { 1, 0 })
    if action == "readonly" then
      vim.bo[buffer].modifiable = false
    else
      vim.api.nvim_buf_delete(buffer, { force = true, unload = action == "unloaded" })
    end
    dictator.stop()
    wait_for("idle")
    assert(not vim.tbl_contains(messages, "transcricao inserida"), "reported success for " .. action)
    assert(messages[#messages]:find("descartada"), "missing discard notification for " .. action)
    if vim.api.nvim_buf_is_valid(buffer) then
      vim.api.nvim_buf_delete(buffer, { force = true })
    end
  end

  buffer = record({ "original" }, { 1, 0 })
  dictator.cancel()
  wait_for("idle")
  assert(#vim.api.nvim_buf_get_extmarks(buffer, -1, 0, -1, {}) == 0, "cancel leaked a mark")

  buffer = record({ "original" }, { 1, 0 })
  vim.env.VIM_DICTATOR_TEST_FAIL_COMMAND = "stop"
  dictator.stop()
  wait_for("recording")
  vim.env.VIM_DICTATOR_TEST_FAIL_COMMAND = nil
  vim.api.nvim_buf_set_lines(buffer, 0, 0, false, { "nova" })
  finish(buffer, { "nova", "ditadooriginal" })

  buffer = record({ "original" }, { 1, 0 })
  vim.api.nvim_buf_clear_namespace(buffer, vim.api.nvim_get_namespaces().vim_dictator, 0, -1)
  dictator.stop()
  wait_for("idle")
  assert(messages[#messages]:find("descartada"), "lost mark must be reported")

  buffer = record({ "original" }, { 1, 0 })
  local set_text = vim.api.nvim_buf_set_text
  vim.api.nvim_buf_set_text = function() error("simulated insertion failure") end
  dictator.stop()
  local released = vim.wait(2000, function() return dictator.status() == "idle" end)
  vim.api.nvim_buf_set_text = set_text
  assert(released, "insertion failure must release the session")
  assert(messages[#messages]:find("nao foi possivel inserir"), "missing insertion error")
  assert(#vim.api.nvim_buf_get_extmarks(buffer, -1, 0, -1, {}) == 0, "insertion error leaked a mark")

  vim.env.VIM_DICTATOR_TEST_FAIL_COMMAND = "start"
  dictator.start()
  wait_for("idle")
  vim.env.VIM_DICTATOR_TEST_FAIL_COMMAND = nil
  assert(#vim.api.nvim_buf_get_extmarks(buffer, -1, 0, -1, {}) == 0, "failed start leaked a mark")
end)

vim.fn.delete(temp_dir, "rf")
assert(ok, error_message)
print("PASS: test_buffer_edits")
