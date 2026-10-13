$ErrorActionPreference = "Stop"
$agentScript = Join-Path $PSScriptRoot "agent.py"
$python = (Get-Command python.exe -ErrorAction Stop).Source
$pythonw = Join-Path (Split-Path -Parent $python) "pythonw.exe"
if (-not (Test-Path -LiteralPath $pythonw)) {
    throw "pythonw.exe not found next to Python: $python"
}
$runKey = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Run"
New-Item -Path $runKey -Force | Out-Null
$command = '"' + $pythonw + '" "' + $agentScript + '"'
Set-ItemProperty -Path $runKey -Name "DynamicIslandDiscordAgent" -Value $command -Type String
Write-Host "Automatic startup configured for the current Windows user."
Write-Host "Command: $command"
Write-Host "Run it now, or restart Windows to see the Discord card."
