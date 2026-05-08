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
$LogPath = Join-Path $LogDir "$Stamp.log"

function Write-RunLog {
    param([string]$Message)
    $line = "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') $Message"
    Add-Content -LiteralPath $LogPath -Value $line -Encoding utf8
    Write-Host $line
}

try {
    Write-RunLog "file assistant start mode=$Mode"

    $PythonScript = Join-Path $ScriptRoot "file_assistant.py"
    $ScannerOutput = python $PythonScript --config $ConfigPath --mode $Mode
    if ($LASTEXITCODE -ne 0) {
        throw "Python scanner failed with exit code $LASTEXITCODE"
    }

    Write-RunLog "scanner output: $ScannerOutput"
    $ScannerResult = $ScannerOutput | Select-Object -Last 1 | ConvertFrom-Json
    $SummaryJson = [string]$ScannerResult.summary_json
    $HtmlReport = [string]$ScannerResult.html_report

    $ObsidianManagerResult = $null
    $ObsidianManagerScript = Join-Path $ScriptRoot "obsidian_manager.py"
    if (Test-Path -LiteralPath $ObsidianManagerScript) {
        $ObsidianOutput = python $ObsidianManagerScript --config $ConfigPath --mode $Mode
        if ($LASTEXITCODE -ne 0) {
            throw "Obsidian manager failed with exit code $LASTEXITCODE"
        }
        Write-RunLog "obsidian manager output: $ObsidianOutput"
        $ObsidianManagerResult = $ObsidianOutput | Select-Object -Last 1 | ConvertFrom-Json
    }

    $Result = [ordered]@{
        ok = $true
        mode = $Mode
        summary_json = $SummaryJson
        html_report = $HtmlReport
        markdown_report = [string]$ScannerResult.markdown_report
        obsidian_note = [string]$ScannerResult.obsidian_note
        total_files = [int]$ScannerResult.total_files
        counts = $ScannerResult.counts
        obsidian_manager = $ObsidianManagerResult
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
