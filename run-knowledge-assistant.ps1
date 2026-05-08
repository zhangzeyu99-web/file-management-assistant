param(
    [ValidateSet("organize", "review", "extract", "remind", "legacy-index")]
    [string]$Action = "remind",
    [string]$Text = "",
    [string]$Query = "",
    [string]$Request = "",
    [string]$Kind = "",
    [string[]]$LocalPath = @(),
    [string]$Config = ".\config.json"
)

$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new()

$RepoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Push-Location $RepoRoot
try {
    $args = @(".\knowledge_assistant.py", $Action, "--config", $Config)
    if (-not [string]::IsNullOrWhiteSpace($Text)) { $args += @("--text", $Text) }
    if (-not [string]::IsNullOrWhiteSpace($Query)) { $args += @("--query", $Query) }
    if (-not [string]::IsNullOrWhiteSpace($Request)) { $args += @("--request", $Request) }
    if (-not [string]::IsNullOrWhiteSpace($Kind)) { $args += @("--kind", $Kind) }
    foreach ($path in $LocalPath) {
        if (-not [string]::IsNullOrWhiteSpace($path)) { $args += @("--local-path", $path) }
    }
    & python @args
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}
finally {
    Pop-Location
}
