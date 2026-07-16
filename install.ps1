$ErrorActionPreference = "Stop"

$projectDir = $PSScriptRoot
$dataDir = Join-Path $env:LOCALAPPDATA "nvim-data"
$pluginDir = Join-Path $dataDir "site\pack\vim-dictator\start\vim-dictator"

if (Test-Path $pluginDir) {
  Remove-Item -Recurse -Force $pluginDir
}

New-Item -ItemType Directory -Force $pluginDir | Out-Null
Copy-Item -Recurse "$projectDir\bin" $pluginDir
Copy-Item -Recurse "$projectDir\lua" $pluginDir
Copy-Item -Recurse "$projectDir\plugin" $pluginDir

Write-Output "Installed: $pluginDir"
Write-Output "Create $env:APPDATA\vim-dictator\env with OPENAI_API_KEY=..."
