param(
    [ValidateSet("Run", "Test")]
    [string]$Mode = "Run",
    [switch]$SkipFeishu
)

$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new()

$ScriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$RuntimeRoot = "D:\codex\file-assistant"
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
    Write-RunLog "file assistant start mode=$Mode skipFeishu=$SkipFeishu"

    $PythonScript = Join-Path $ScriptRoot "file_assistant.py"
    $ConfigPath = Join-Path $ScriptRoot "config.json"
    $ScannerOutput = python $PythonScript --config $ConfigPath --mode $Mode
    if ($LASTEXITCODE -ne 0) {
        throw "Python scanner failed with exit code $LASTEXITCODE"
    }

    Write-RunLog "scanner output: $ScannerOutput"
    $ScannerResult = $ScannerOutput | Select-Object -Last 1 | ConvertFrom-Json
    $SummaryJson = [string]$ScannerResult.summary_json
    $HtmlReport = [string]$ScannerResult.html_report

    $FeishuResult = $null
    if (-not $SkipFeishu) {
        $NodeScript = Join-Path $ScriptRoot "send_report_to_feishu.js"
        $FeishuOutput = node $NodeScript --summary-json $SummaryJson --html-file $HtmlReport
        if ($LASTEXITCODE -ne 0) {
            throw "Feishu sender failed with exit code $LASTEXITCODE"
        }
        Write-RunLog "feishu output: $FeishuOutput"
        $FeishuResult = $FeishuOutput | Select-Object -Last 1 | ConvertFrom-Json
    }
    else {
        Write-RunLog "feishu skipped by switch"
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
        feishu = $FeishuResult
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
