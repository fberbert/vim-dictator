local M = {}

local defaults = {
  command = "vim-dictator",
  toggle_key = "<leader>d",
  cancel_key = "<leader>dc",
  map_keys = true,
}

local config = vim.deepcopy(defaults)
local session = nil
local commands_created = false

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

local function insert_transcription(target, text)
  if not vim.api.nvim_buf_is_valid(target.bufnr) then
    notify("o buffer original foi fechado; transcricao descartada", vim.log.levels.WARN)
    return
  end

  if not vim.bo[target.bufnr].modifiable then
    notify("o buffer original nao permite edicao; transcricao descartada", vim.log.levels.WARN)
    return
  end

  local lines = vim.split(text, "\n", { plain = true })
  vim.api.nvim_buf_set_text(target.bufnr, target.row - 1, target.col, target.row - 1, target.col, lines)
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
  session = {
    bufnr = vim.api.nvim_get_current_buf(),
    row = cursor[1],
    col = cursor[2],
    phase = "starting",
  }

  local job_id = start_job({ "start" }, function(_, code)
    vim.schedule(function()
      if code ~= 0 then
        session = nil
        notify("nao foi possivel iniciar a gravacao", vim.log.levels.ERROR)
        return
      end
      if session then
        session.phase = "recording"
        notify("gravando... pressione " .. config.toggle_key .. " para transcrever")
      end
    end)
  end)

  if job_id <= 0 then
    session = nil
    notify("nao foi possivel executar " .. config.command, vim.log.levels.ERROR)
  end
end

function M.stop()
  if not session or session.phase ~= "recording" then
    notify("nenhuma gravacao ativa", vim.log.levels.WARN)
    return
  end

  session.phase = "transcribing"
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
          if text ~= "" then
            insert_transcription(target, text)
            notify("transcricao inserida")
          else
            notify("a API nao retornou texto", vim.log.levels.WARN)
          end
        else
          if session then
            session.phase = "recording"
          end
          notify("a transcricao falhou; a gravacao foi preservada para tentar novamente", vim.log.levels.ERROR)
          return
        end
        session = nil
      end)
    end,
  })

  if job_id <= 0 then
    session.phase = "recording"
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
        session = nil
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
