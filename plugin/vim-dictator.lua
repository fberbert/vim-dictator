if vim.g.vim_dictator_disable then
  return
end

require("vim_dictator").setup({
  command = vim.g.vim_dictator_command,
})
