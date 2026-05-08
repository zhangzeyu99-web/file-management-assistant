param(
    [ValidateSet("Run", "Test")]
    [string]$Mode = "Run"
)

$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new()

$ScriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$ConfigPath = Join-Path $ScriptRoot "config.json"
$RuntimeRoot = python -c "import pathlib, sys; sys.path.insert(0, r'$ScriptRoot'); from config_loader import load_config; print(load_config(pathlib.Path(r'$ConfigPath')).get('runtime_root') or '')"
if (-not $RuntimeRoot) {
    $RuntimeRoot = Join-Path $ScriptRoot ".runtime"
}
$LogDir = Join-Path $RuntimeRoot "logs"
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null

$Stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$LogPath = Join-Path $LogDir "$Stamp-obsidian.log"

function Write-RunLog {
    param([string]$Message)
    $line = "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') $Message"
    Add-Content -LiteralPath $LogPath -Value $line -Encoding utf8
    Write-Host $line
}

try {
    Write-RunLog "obsidian manager start mode=$Mode"

    $PythonScript = Join-Path $ScriptRoot "obsidian_manager.py"
    $ManagerOutput = python $PythonScript --config $ConfigPath --mode $Mode
    if ($LASTEXITCODE -ne 0) {
        throw "Obsidian manager failed with exit code $LASTEXITCODE"
    }

    Write-RunLog "manager output: $ManagerOutput"
    $ManagerResult = $ManagerOutput | Select-Object -Last 1 | ConvertFrom-Json
    $SummaryJson = [string]$ManagerResult.summary_json
    $MarkdownReport = [string]$ManagerResult.markdown_report

    $Result = [ordered]@{
        ok = $true
        mode = $Mode
        summary_json = $SummaryJson
        markdown_report = $MarkdownReport
        obsidian_note = [string]$ManagerResult.obsidian_note
        total_notes = [int]$ManagerResult.total_notes
        counts = $ManagerResult.counts
        log = $LogPath
    }
    $Result | ConvertTo-Json -Depth 8 -Compress
}
catch {
    Write-RunLog "ERROR: $($_.Exception.Message)"
    $Failure = [ordered]@{
        ok = $false
        mode = $Mode
        error = $_.Exception.Message
        log = $LogPath
    }
    $Failure | ConvertTo-Json -Depth 4 -Compress
    exit 1
}
