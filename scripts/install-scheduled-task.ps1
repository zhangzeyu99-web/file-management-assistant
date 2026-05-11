param(
    [string]$TaskName = "Knowledge Organizer Assistant",
    [string]$At = "09:00",
    [switch]$KeepLegacyTask
)

$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new()

$RepoRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$Runner = Join-Path $RepoRoot "run-knowledge-assistant.ps1"

if (-not (Test-Path -LiteralPath $Runner)) {
    throw "Runner not found: $Runner"
}

if (-not $KeepLegacyTask) {
    $legacy = Get-ScheduledTask -TaskName "Codex File Management Assistant" -TaskPath "\" -ErrorAction SilentlyContinue
    if ($legacy) {
        Unregister-ScheduledTask -TaskName "Codex File Management Assistant" -TaskPath "\" -Confirm:$false
    }
}

$Action = New-ScheduledTaskAction `
    -Execute "powershell.exe" `
    -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$Runner`" -Action remind -Config `"$RepoRoot\config.json`""

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
    -Description "Generate up to 3 local daily action suggestions at 09:00. Writes new notes only; does not move source files." `
    -Force | Out-Null

Get-ScheduledTask -TaskName $TaskName -TaskPath "\" |
    Select-Object TaskName,State,TaskPath
