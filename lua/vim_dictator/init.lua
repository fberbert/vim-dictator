local M = {}

local function bundled_command()
  local source = debug.getinfo(1, "S").source
  if source:sub(1, 1) == "@" then
    local root = vim.fn.fnamemodify(source:sub(2), ":h:h:h")
    local suffix = vim.loop.os_uname().sysname == "Windows_NT" and ".cmd" or ""
    local command = root .. "/bin/vim-dictator" .. suffix
    if vim.fn.filereadable(command) == 1 then
      return command
    end
  end
  return "vim-dictator"
end

local defaults = {
  command = bundled_command(),
  toggle_key = "<C-d>",
  cancel_key = "<C-d>c",
  map_keys = true,
}

local config = vim.deepcopy(defaults)
local session = nil
local commands_created = false
local namespace = vim.api.nvim_create_namespace("vim_dictator")

local function notify(message, level)
  vim.notify(message, level or vim.log.levels.INFO, { title = "Vim Dictator" })
end

local function append_output(output, chunks, data)
  for index, chunk in ipairs(data) do
    if index == 1 then
      chunk = output.partial .. chunk
    end

    if index == #data then
      output.partial = chunk
    else
      table.insert(chunks, chunk)
    end
  end
end

local function output_text(output, chunks)
  if output.partial ~= "" then
    table.insert(chunks, output.partial)
  end
  return table.concat(chunks, "\n")
end

local function start_job(args, on_exit)
  return vim.fn.jobstart(vim.list_extend({ config.command }, args), {
    stdout_buffered = false,
    on_exit = on_exit,
  })
end

local function clear_session(target)
  if target and vim.api.nvim_buf_is_valid(target.bufnr) and vim.api.nvim_buf_is_loaded(target.bufnr) then
    vim.api.nvim_buf_del_extmark(target.bufnr, namespace, target.mark_id)
  end
  session = nil
end

local function insert_transcription(target, text)
  if not vim.api.nvim_buf_is_valid(target.bufnr) or not vim.api.nvim_buf_is_loaded(target.bufnr) then
    notify("o buffer original foi fechado; transcricao descartada", vim.log.levels.WARN)
    return false
  end

  if not vim.bo[target.bufnr].modifiable then
    notify("o buffer original nao permite edicao; transcricao descartada", vim.log.levels.WARN)
    return false
  end

  local position = vim.api.nvim_buf_get_extmark_by_id(target.bufnr, namespace, target.mark_id, {})
  if #position == 0 then
    notify("a posicao original nao esta disponivel; transcricao descartada", vim.log.levels.WARN)
    return false
  end

  -- Deleting the last line can leave an extmark just past the end of the buffer.
  local last_row = vim.api.nvim_buf_line_count(target.bufnr) - 1
  local row = math.min(position[1], last_row)
  local line = vim.api.nvim_buf_get_lines(target.bufnr, row, row + 1, false)[1]
  local col = position[1] > last_row and #line or math.min(position[2], #line)
  local lines = vim.split(text, "\n", { plain = true })
  vim.api.nvim_buf_set_text(target.bufnr, row, col, row, col, lines)
  return true
end

function M.status()
  return session and session.phase or "idle"
end

function M.start()
  if session then
    notify("a gravacao ja esta em andamento", vim.log.levels.WARN)
    return
  end

  local cursor = vim.api.nvim_win_get_cursor(0)
  local bufnr = vim.api.nvim_get_current_buf()
  session = {
    bufnr = bufnr,
    mark_id = vim.api.nvim_buf_set_extmark(bufnr, namespace, cursor[1] - 1, cursor[2], { right_gravity = true }),
    phase = "starting",
  }

  local job_id = start_job({ "start" }, function(_, code)
    vim.schedule(function()
      if code ~= 0 then
        clear_session(session)
        notify("nao foi possivel iniciar a gravacao", vim.log.levels.ERROR)
        return
      end
      if session then
        session = vim.tbl_extend("force", {}, session, { phase = "recording" })
        notify("gravando... pressione " .. config.toggle_key .. " para transcrever")
      end
    end)
  end)

  if job_id <= 0 then
    clear_session(session)
    notify("nao foi possivel executar " .. config.command, vim.log.levels.ERROR)
  end
end

function M.stop()
  if not session or session.phase ~= "recording" then
    notify("nenhuma gravacao ativa", vim.log.levels.WARN)
    return
  end

  session = vim.tbl_extend("force", {}, session, { phase = "transcribing" })
  local target = vim.deepcopy(session)
  local output = { partial = "" }
  local chunks = {}

  local job_id = vim.fn.jobstart({ config.command, "stop" }, {
    stdout_buffered = false,
    on_stdout = function(_, data)
      append_output(output, chunks, data)
    end,
    on_exit = function(_, code)
      vim.schedule(function()
        if code == 0 then
          local text = output_text(output, chunks)
          local ok, inserted = true, false
          if text ~= "" then
            ok, inserted = pcall(insert_transcription, target, text)
          end
          clear_session(target)
          if not ok then
            notify("nao foi possivel inserir a transcricao: " .. tostring(inserted), vim.log.levels.ERROR)
          elseif inserted then
            notify("transcricao inserida")
          elseif text == "" then
            notify("a API nao retornou texto", vim.log.levels.WARN)
          end
        else
          if session then
            session = vim.tbl_extend("force", {}, session, { phase = "recording" })
          end
          notify("a transcricao falhou; a gravacao foi preservada para tentar novamente", vim.log.levels.ERROR)
          return
        end
      end)
    end,
  })

  if job_id <= 0 then
    session = vim.tbl_extend("force", {}, session, { phase = "recording" })
    notify("nao foi possivel executar " .. config.command, vim.log.levels.ERROR)
  end
end

function M.toggle()
  if not session then
    M.start()
  elseif session.phase == "recording" then
    M.stop()
  else
    notify("aguarde a operacao atual terminar", vim.log.levels.WARN)
  end
end

function M.cancel()
  if not session then
    notify("nenhuma gravacao ativa", vim.log.levels.WARN)
    return
  end

  local job_id = start_job({ "cancel" }, function(_, code)
    vim.schedule(function()
      if code == 0 then
        clear_session(session)
        notify("gravacao descartada")
      else
        notify("nao foi possivel descartar a gravacao", vim.log.levels.ERROR)
      end
    end)
  end)

  if job_id <= 0 then
    notify("nao foi possivel executar " .. config.command, vim.log.levels.ERROR)
  end
end

function M.setup(options)
  config = vim.tbl_deep_extend("force", vim.deepcopy(defaults), options or {})

  if config.map_keys then
    vim.keymap.set("n", config.toggle_key, M.toggle, { desc = "Iniciar/parar ditado" })
    vim.keymap.set("n", config.cancel_key, M.cancel, { desc = "Cancelar ditado" })
  end

  if not commands_created then
    vim.api.nvim_create_user_command("VimDictatorToggle", M.toggle, {})
    vim.api.nvim_create_user_command("VimDictatorCancel", M.cancel, {})
    vim.api.nvim_create_user_command("VimDictatorStatus", function()
      notify(M.status())
    end, {})
    commands_created = true
  end
end

return M
