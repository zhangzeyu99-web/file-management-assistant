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
$LogPath = Join-Path $LogDir "$Stamp-obsidian.log"

function Write-RunLog {
    param([string]$Message)
    $line = "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') $Message"
    Add-Content -LiteralPath $LogPath -Value $line -Encoding utf8
    Write-Host $line
}

try {
    Write-RunLog "obsidian manager start mode=$Mode skipFeishu=$SkipFeishu"

    $PythonScript = Join-Path $ScriptRoot "obsidian_manager.py"
    $ConfigPath = Join-Path $ScriptRoot "config.json"
    $ManagerOutput = python $PythonScript --config $ConfigPath --mode $Mode
    if ($LASTEXITCODE -ne 0) {
        throw "Obsidian manager failed with exit code $LASTEXITCODE"
    }

    Write-RunLog "manager output: $ManagerOutput"
    $ManagerResult = $ManagerOutput | Select-Object -Last 1 | ConvertFrom-Json
    $SummaryJson = [string]$ManagerResult.summary_json
    $MarkdownReport = [string]$ManagerResult.markdown_report

    $FeishuResult = $null
    if (-not $SkipFeishu) {
        $NodeScript = Join-Path $ScriptRoot "send_obsidian_report_to_feishu.js"
        $FeishuOutput = node $NodeScript --summary-json $SummaryJson --markdown-file $MarkdownReport
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
        markdown_report = $MarkdownReport
        obsidian_note = [string]$ManagerResult.obsidian_note
        total_notes = [int]$ManagerResult.total_notes
        counts = $ManagerResult.counts
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
