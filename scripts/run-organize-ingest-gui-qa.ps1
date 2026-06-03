param(
    [string]$BaseUrl = "",
    [string]$Config = "",
    [int]$Port = 8772,
    [ValidateSet("chromium", "chrome", "firefox", "webkit", "msedge")]
    [string]$Browser = "chromium",
    [switch]$Headed,
    [switch]$StrictUx
)

$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new()

$Repo = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$Stamp = "$(Get-Date -Format "yyyyMMdd-HHmmss-fff")-$([guid]::NewGuid().ToString("N").Substring(0,8))"
$RunDir = Join-Path $Repo "output\organize-ingest-gui-qa\$Stamp"
$Session = "organize-ingest-gui-qa-$Stamp"
$ServerProcess = $null
$StartedServer = $false

function Add-QueryParam {
    param([string]$Url, [string]$Name, [string]$Value)
    if ([string]::IsNullOrWhiteSpace($Value)) { return $Url }
    $separator = if ($Url.Contains("?")) { ";" } else { "?" }
    return "$Url$separator$Name=$([uri]::EscapeDataString($Value))"
}

function Stop-PortServer {
    param([int]$TargetPort)
    $connections = Get-NetTCPConnection -LocalPort $TargetPort -State Listen -ErrorAction SilentlyContinue
    foreach ($connection in $connections) {
        $process = Get-CimInstance Win32_Process -Filter "ProcessId=$($connection.OwningProcess)" -ErrorAction SilentlyContinue
        if ($process -and $process.CommandLine -like "*gui_server.py*") {
            Stop-Process -Id $connection.OwningProcess -Force -ErrorAction SilentlyContinue
        }
    }
}

function Wait-HttpOk {
    param([string]$Url)
    $deadline = (Get-Date).AddSeconds(30)
    do {
        try {
            $response = Invoke-WebRequest -UseBasicParsing -Uri $Url -TimeoutSec 2
            if ($response.StatusCode -eq 200) { return }
        } catch {
            Start-Sleep -Milliseconds 300
        }
    } while ((Get-Date) -lt $deadline)
    throw "GUI server did not become ready: $Url"
}

function Stop-PlaywrightSessionProcesses {
    param([string]$SessionName)
    if ([string]::IsNullOrWhiteSpace($SessionName)) { return }
    $escaped = [regex]::Escape($SessionName)
    Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
        Where-Object { $_.ProcessId -ne $PID -and $_.CommandLine -match $escaped } |
        ForEach-Object {
            Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
        }
}

function Initialize-DemoConfig {
    param([string]$TargetConfig)
    $source = Join-Path $RunDir "demo-source"
    $vault = Join-Path $RunDir "demo-vault"
    $runtime = Join-Path $RunDir "demo-runtime"
    $knowledgeRoot = Join-Path $vault "routine\knowledge-organizer"
    New-Item -ItemType Directory -Force -Path $source, $vault, $runtime, $knowledgeRoot | Out-Null

    $token = "GuiOrganizeIngestEvidence-20260602"
    $sourceA = @(
        "# GUI Organize Ingest Evidence",
        "",
        "${token}: alpha file proves the GUI can scan a real local directory.",
        "This file should become an independent file index note."
    ) -join "`n"
    $sourceB = @(
        "# GUI Organize Second Evidence",
        "",
        "${token}: beta file proves multiple readable files are indexed.",
        "Review should find this token after organize writes Obsidian file indexes."
    ) -join "`n"
    $sourceA | Set-Content -Path (Join-Path $source "alpha-ingest.md") -Encoding UTF8
    $sourceB | Set-Content -Path (Join-Path $source "beta-ingest.txt") -Encoding UTF8

    $configObject = [ordered]@{
        runtime_root = $runtime
        obsidian_vault = $vault
        obsidian_run_dir = $knowledgeRoot
        knowledge_root = $knowledgeRoot
        allowed_open_roots = @($vault, $runtime, $source)
        obsidian_folders = [ordered]@{
            inbox = "inbox"
            daily = "daily"
            projects = "projects"
            routine = "routine"
            templates = "templates"
            archive = "archive"
            codex_project = "Codex"
        }
        watch_roots = @(
            [ordered]@{
                name = "demo-source"
                path = $source
                max_depth = 3
                max_files = 100
            },
            [ordered]@{
                name = "demo-knowledge-root"
                path = $knowledgeRoot
                max_depth = 6
                max_files = 300
            }
        )
        exclude_dir_names = @(".git", "node_modules", "__pycache__")
    }
    $configObject | ConvertTo-Json -Depth 10 | Set-Content -Path $TargetConfig -Encoding UTF8
    return [ordered]@{
        demo_source = $source
        demo_vault = $vault
        demo_runtime = $runtime
        token = $token
    }
}

function Write-Summary {
    param($Result, [string]$Path)
    $lines = @(
        "# Organize Ingest GUI QA",
        "",
        "- Runner: run-organize-ingest-gui-qa.ps1",
        "- Base URL: $($Result.base_url)",
        "- Config: $($Result.config)",
        "- Demo source: $($Result.demo_source)",
        "- Demo vault: $($Result.demo_vault)",
        "- OK: $($Result.ok)",
        "- Scanned files: $($Result.organize.total_files)",
        "- Generated file index notes: $($Result.organize.generated_file_index_notes.Count)",
        "- Review top source path: ``$($Result.review.review_top_source_path)``",
        "- Screenshot: $($Result.screenshot)",
        "",
        "## Generated File Index Notes"
    )
    foreach ($item in $Result.organize.generated_file_index_notes) {
        $lines += "- ``$item``"
    }
    if ($Result.mechanics_failures.Count -gt 0) {
        $lines += ""
        $lines += "## Issues"
        foreach ($item in $Result.mechanics_failures) {
            $lines += "- $($item.message)"
        }
    }
    $lines | Set-Content -Path $Path -Encoding UTF8
}

try {
    if (-not (Get-Command npx.cmd -ErrorAction SilentlyContinue)) {
        throw "npx.cmd is required. Install Node.js/npm first."
    }
    New-Item -ItemType Directory -Force -Path $RunDir | Out-Null
    if (-not $Config) {
        $Config = Join-Path $RunDir "config.organize-ingest-gui-qa.json"
        $Demo = Initialize-DemoConfig -TargetConfig $Config
    } else {
        $Demo = [ordered]@{ demo_source = ""; demo_vault = ""; demo_runtime = ""; token = "GuiOrganizeIngestEvidence-20260602" }
    }

    if (-not $BaseUrl) {
        Stop-PortServer -TargetPort $Port
        $BaseUrl = "http://127.0.0.1:$Port/"
        $args = @(
            (Join-Path $Repo "gui_server.py"),
            "--host", "127.0.0.1",
            "--port", "$Port",
            "--config", $Config,
            "--no-browser"
        )
        $ServerProcess = Start-Process -FilePath python -ArgumentList $args -WorkingDirectory $Repo -WindowStyle Hidden -PassThru
        $StartedServer = $true
    }

    Wait-HttpOk -Url $BaseUrl

    $TestUrl = Add-QueryParam -Url $BaseUrl -Name "organizeIngestGuiQa" -Value "1"
    $TestUrl = Add-QueryParam -Url $TestUrl -Name "sourcePath" -Value $Demo.demo_source
    $rawPath = Join-Path $RunDir "playwright-raw.txt"
    $jsonPath = Join-Path $RunDir "gui-organize-ingest-qa-result.json"
    $summaryPath = Join-Path $RunDir "gui-organize-ingest-qa-summary.md"
    $screenshotPath = Join-Path $RunDir "final-page.png"

    $openArgs = @("--package", "@playwright/cli", "playwright-cli", "-s=$Session", "open", $TestUrl)
    if ($Browser -ne "chromium") { $openArgs += @("--browser", $Browser) }
    if ($Headed) { $openArgs += "--headed" }
    & npx.cmd @openArgs | Out-Null
    & npx.cmd --package "@playwright/cli" playwright-cli "-s=$Session" resize 1440 960 | Out-Null
    $raw = & npx.cmd --package "@playwright/cli" playwright-cli "-s=$Session" --raw run-code --filename (Join-Path $Repo "scripts\gui-organize-ingest-qa.js")
    & npx.cmd --package "@playwright/cli" playwright-cli "-s=$Session" screenshot --filename $screenshotPath | Out-Null
    & npx.cmd --package "@playwright/cli" playwright-cli "-s=$Session" close | Out-Null

    $rawText = ($raw -join "`n").Trim()
    $rawText | Set-Content -Path $rawPath -Encoding UTF8
    $jsonStart = $rawText.IndexOf("{")
    $jsonEnd = $rawText.LastIndexOf("}")
    if ($jsonStart -lt 0 -or $jsonEnd -le $jsonStart) {
        throw "Playwright did not return JSON. Raw output saved to $rawPath"
    }
    $result = $rawText.Substring($jsonStart, $jsonEnd - $jsonStart + 1) | ConvertFrom-Json
    $result | Add-Member -NotePropertyName "base_url" -NotePropertyValue $BaseUrl -Force
    $result | Add-Member -NotePropertyName "test_url" -NotePropertyValue $TestUrl -Force
    $result | Add-Member -NotePropertyName "config" -NotePropertyValue $Config -Force
    $result | Add-Member -NotePropertyName "run_dir" -NotePropertyValue $RunDir -Force
    $result | Add-Member -NotePropertyName "demo_source" -NotePropertyValue $Demo.demo_source -Force
    $result | Add-Member -NotePropertyName "demo_vault" -NotePropertyValue $Demo.demo_vault -Force
    $result | Add-Member -NotePropertyName "demo_runtime" -NotePropertyValue $Demo.demo_runtime -Force
    $result | Add-Member -NotePropertyName "json" -NotePropertyValue $jsonPath -Force
    $result | Add-Member -NotePropertyName "markdown" -NotePropertyValue $summaryPath -Force
    $result | Add-Member -NotePropertyName "screenshot" -NotePropertyValue $screenshotPath -Force

    foreach ($requiredPath in $result.organize.generated_file_index_notes) {
        if ([string]::IsNullOrWhiteSpace($requiredPath) -or -not (Test-Path -LiteralPath $requiredPath)) {
            throw "generated file index note missing: $requiredPath"
        }
        if ($requiredPath -notlike "$($Demo.demo_vault)*") {
            throw "generated file index note is not under demo-vault: $requiredPath"
        }
    }
    if ([string]::IsNullOrWhiteSpace($result.review.review_top_source_path) -or -not (Test-Path -LiteralPath $result.review.review_top_source_path)) {
        throw "review top source path missing or not found"
    }

    $result | ConvertTo-Json -Depth 20 | Set-Content -Path $jsonPath -Encoding UTF8
    Write-Summary -Result $result -Path $summaryPath

    [ordered]@{
        ok = [bool]$result.ok
        strict_ok = [bool]($result.ok -and (-not $StrictUx -or $result.ux_issues.Count -eq 0))
        status = "completed"
        run_dir = $RunDir
        json = $jsonPath
        markdown = $summaryPath
        screenshot = $screenshotPath
        demo_source = $Demo.demo_source
        demo_vault = $Demo.demo_vault
        demo_runtime = $Demo.demo_runtime
        scanned_files = $result.organize.total_files
        generated_file_index_notes = $result.organize.generated_file_index_notes
        review_top_source_path = $result.review.review_top_source_path
        ux_issues = $result.ux_issues.Count
        mechanics_failures = $result.mechanics_failures.Count
        console = $result.console_events.Count
    } | ConvertTo-Json -Depth 8

    if (-not $result.ok) { exit 1 }
    if ($StrictUx -and $result.ux_issues.Count -gt 0) { exit 2 }
}
finally {
    try { & npx.cmd --package "@playwright/cli" playwright-cli "-s=$Session" close | Out-Null } catch {}
    Stop-PlaywrightSessionProcesses -SessionName $Session
    if ($ServerProcess) {
        Stop-Process -Id $ServerProcess.Id -Force -ErrorAction SilentlyContinue
    }
    if ($StartedServer) {
        Stop-PortServer -TargetPort $Port
    }
}
