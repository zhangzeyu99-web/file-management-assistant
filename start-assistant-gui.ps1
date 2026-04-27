param(
    [int]$Port = 8765,
    [string]$HostName = "127.0.0.1",
    [string]$ConfigPath = ""
)

$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new()

$ScriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$Server = Join-Path $ScriptRoot "gui_server.py"
if (-not $ConfigPath) {
    $ConfigPath = Join-Path $ScriptRoot "config.json"
}

python $Server --host $HostName --port $Port --config $ConfigPath
