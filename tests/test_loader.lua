local root = vim.fn.getcwd()
vim.opt.runtimepath:prepend(root)
vim.notify = function() end

local launched
vim.fn.jobstart = function(command)
  launched = command[1]
  return 0 -- Only inspect command resolution; never start recording.
end

local function check(expected)
  dofile(root .. "/plugin/vim-dictator.lua")
  require("vim_dictator").start()
  assert(launched == expected, "expected " .. expected .. ", got " .. tostring(launched))
  assert(require("vim_dictator").status() == "idle", "failed launch must release the session")
  assert(#vim.api.nvim_buf_get_extmarks(0, -1, 0, -1, {}) == 0, "failed launch leaked a mark")
end

check(root .. "/bin/vim-dictator")
vim.g.vim_dictator_command = "/custom path/dictator"
check(vim.g.vim_dictator_command)
vim.g.vim_dictator_command = nil

package.loaded.vim_dictator = nil
vim.loop.os_uname = function() return { sysname = "Windows_NT" } end
check(root .. "/bin/vim-dictator.cmd")

vim.g.vim_dictator_disable = true
launched = nil
package.loaded.vim_dictator = { setup = function() error("disabled loader called setup") end }
dofile(root .. "/plugin/vim-dictator.lua")
assert(launched == nil, "disabled loader must not launch anything")
print("PASS: test_loader")
