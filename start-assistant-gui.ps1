param(
    [int]$Port = 8765
)

$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new()

$ScriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$Server = Join-Path $ScriptRoot "gui_server.py"

python $Server --host 127.0.0.1 --port $Port
