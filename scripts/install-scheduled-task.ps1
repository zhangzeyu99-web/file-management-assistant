param(
    [string]$TaskName = "Codex File Management Assistant",
    [string]$At = "20:30"
)

$ErrorActionPreference = "Stop"

$RepoRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$Runner = Join-Path $RepoRoot "run-file-assistant.ps1"

if (-not (Test-Path -LiteralPath $Runner)) {
    throw "Runner not found: $Runner"
}

$Action = New-ScheduledTaskAction `
    -Execute "powershell.exe" `
    -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$Runner`""

$Trigger = New-ScheduledTaskTrigger -Daily -At $At
$Principal = New-ScheduledTaskPrincipal `
    -UserId $env:USERNAME `
    -LogonType Interactive `
    -RunLevel Limited

Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $Action `
    -Trigger $Trigger `
    -Principal $Principal `
    -Description "Daily file archive review reminder and Feishu report." `
    -Force | Out-Null

Get-ScheduledTask -TaskName $TaskName -TaskPath "\" |
    Select-Object TaskName,State,TaskPath
