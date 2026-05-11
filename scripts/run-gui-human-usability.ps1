param(
    [string]$BaseUrl = "",
    [int]$Port = 8768,
    [ValidateSet("chromium", "chrome", "firefox", "webkit", "msedge")]
    [string]$Browser = "chromium",
    [switch]$Headed,
    [switch]$ReadOnly,
    [switch]$StrictUx
)

$ErrorActionPreference = "Stop"
$Repo = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$Stamp = "$(Get-Date -Format "yyyyMMdd-HHmmss-fff")-$([guid]::NewGuid().ToString("N").Substring(0,8))"
$RunDir = Join-Path $Repo "output\human-usability\$Stamp"
$ConfigPath = Join-Path $RunDir "config.human-usability.json"
$Session = "human-usability-$Stamp"
$ServerProcess = $null
$LocalPath = $Repo
$FixtureFile = Join-Path $Repo "README.md"

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
    $deadline = (Get-Date).AddSeconds(25)
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

function New-HumanFixtureConfig {
    New-Item -ItemType Directory -Force -Path $RunDir | Out-Null
    $fixture = Join-Path $RunDir "fixture-files"
    $vault = Join-Path $RunDir "vault"
    $runtime = Join-Path $RunDir "runtime"
    $obsidianRun = Join-Path $vault "routine\knowledge-assistant"
    foreach ($path in @(
        $fixture,
        $runtime,
        (Join-Path $vault "inbox"),
        (Join-Path $vault "daily"),
        (Join-Path $vault "projects\Codex"),
        (Join-Path $vault "projects\knowledge-assistant\Card"),
        $obsidianRun
    )) {
        New-Item -ItemType Directory -Force -Path $path | Out-Null
    }

    Set-Content -Path (Join-Path $fixture "human-test-obsidian-material.md") -Value "# Human test material`n`n- Obsidian organize`n- AI context package`n- Daily action suggestions" -Encoding UTF8
    Set-Content -Path (Join-Path $vault "projects\Codex\Obsidian beginner guide.md") -Value "# Obsidian beginner guide`n`nPut notes into inbox first, then review, extract context, and create light daily action suggestions." -Encoding UTF8
    Set-Content -Path (Join-Path $vault "projects\knowledge-assistant\Card\AI context package.md") -Value "# AI context package`n`nSource path, compressed summary, safety boundary, and next request should be packaged together for AI." -Encoding UTF8

    $config = [ordered]@{
        runtime_root = $runtime
        obsidian_vault = $vault
        obsidian_run_dir = $obsidianRun
        knowledge_root = $obsidianRun
        codex_executable = ""
        allowed_open_roots = @($runtime, $vault, $fixture)
        obsidian_folders = [ordered]@{
            inbox = "inbox"
            daily = "daily"
            projects = "projects"
            meetings = "meetings"
            routine = "routine"
            templates = "templates"
            archive = "archive"
            codex_project = "Codex"
        }
        watch_roots = @(
            [ordered]@{
                name = "HumanUsabilityFixture"
                path = $fixture
                max_depth = 3
                max_files = 100
            }
        )
        exclude_dir_names = @(".git", "__pycache__", ".venv", "venv", "node_modules", "tmp", "temp")
        recent_days = 7
        archive_after_days = 30
        installer_after_days = 14
        large_file_mb = 1
        hash_duplicate_min_mb = 1
        hash_duplicate_limit = 20
        top_limit = 10
        review_keywords = @("Obsidian", "AI", "daily action", "context")
    }
    $config | ConvertTo-Json -Depth 8 | Set-Content -Path $ConfigPath -Encoding UTF8
    $script:LocalPath = $fixture
    $script:FixtureFile = Join-Path $fixture "human-test-obsidian-material.md"
}

try {
    if (-not (Get-Command npx.cmd -ErrorAction SilentlyContinue)) {
        throw "npx.cmd is required. Install Node.js/npm first."
    }
    New-Item -ItemType Directory -Force -Path $RunDir | Out-Null

    if (-not $BaseUrl) {
        New-HumanFixtureConfig
        Stop-PortServer -TargetPort $Port
        $BaseUrl = "http://127.0.0.1:$Port/"
        $args = @(
            (Join-Path $Repo "gui_server.py"),
            "--host", "127.0.0.1",
            "--port", "$Port",
            "--config", $ConfigPath,
            "--no-browser"
        )
        $ServerProcess = Start-Process -FilePath python -ArgumentList $args -WorkingDirectory $Repo -WindowStyle Hidden -PassThru
    }

    Wait-HttpOk -Url $BaseUrl

    $TestUrl = Add-QueryParam -Url $BaseUrl -Name "humanLocalPath" -Value $LocalPath
    $TestUrl = Add-QueryParam -Url $TestUrl -Name "humanFile" -Value $FixtureFile
    if ($ReadOnly) {
        $TestUrl = Add-QueryParam -Url $TestUrl -Name "readOnly" -Value "1"
    }

    $videoPath = Join-Path $RunDir "human-usability.webm"
    $screenshotPath = Join-Path $RunDir "final-page.png"
    $rawPath = Join-Path $RunDir "playwright-raw.txt"
    $jsonPath = Join-Path $RunDir "human-usability-result.json"
    $summaryPath = Join-Path $RunDir "human-usability-summary.md"

    $openArgs = @("--package", "@playwright/cli", "playwright-cli", "-s=$Session", "open", $TestUrl)
    if ($Browser -ne "chromium") { $openArgs += @("--browser", $Browser) }
    if ($Headed) { $openArgs += "--headed" }
    & npx.cmd @openArgs | Out-Null
    & npx.cmd --package "@playwright/cli" playwright-cli "-s=$Session" resize 1440 900 | Out-Null
    & npx.cmd --package "@playwright/cli" playwright-cli "-s=$Session" video-start $videoPath --size "1440x900" | Out-Null
    $raw = & npx.cmd --package "@playwright/cli" playwright-cli "-s=$Session" --raw run-code --filename (Join-Path $Repo "scripts\gui-human-usability.js")
    & npx.cmd --package "@playwright/cli" playwright-cli "-s=$Session" video-stop | Out-Null
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
    $result | Add-Member -NotePropertyName "run_dir" -NotePropertyValue $RunDir -Force
    $result | Add-Member -NotePropertyName "video" -NotePropertyValue $videoPath -Force
    $result | Add-Member -NotePropertyName "screenshot" -NotePropertyValue $screenshotPath -Force
    $result | ConvertTo-Json -Depth 20 | Set-Content -Path $jsonPath -Encoding UTF8

    $lines = @(
        "# GUI Human Usability Recording",
        "",
        "- Base URL: $BaseUrl",
        "- Read-only: $($result.read_only)",
        "- OK: $($result.ok)",
        "- Actions: $($result.actions.Count)",
        "- Mechanics failures: $($result.mechanics_failures.Count)",
        "- UX issues: $($result.ux_issues.Count)",
        "- Console warnings/errors: $($result.console.Count)",
        "- Network events tracked: $($result.network.Count)",
        "- Video: $videoPath",
        "- Screenshot: $screenshotPath",
        "",
        "## Timeline"
    )
    foreach ($step in $result.timeline) {
        $lines += "- $($step.at) $($step.label)"
    }
    $lines += ""
    $lines += "## Actions"
    foreach ($action in $result.actions) {
        $lines += "- $($action.label) -> $($action.request_action) status=$($action.status) ok=$($action.ok)"
    }
    $lines += ""
    $lines += "## UX Issues"
    if ($result.ux_issues.Count -eq 0) {
        $lines += "- None"
    } else {
        foreach ($issue in $result.ux_issues) {
            $lines += "- $($issue.id): $($issue.message)"
        }
    }
    $lines += ""
    $lines += "## Mechanics Failures"
    if ($result.mechanics_failures.Count -eq 0) {
        $lines += "- None"
    } else {
        foreach ($failure in $result.mechanics_failures) {
            $lines += "- $($failure.message)"
        }
    }
    $lines | Set-Content -Path $summaryPath -Encoding UTF8

    [ordered]@{
        ok = [bool]$result.ok
        strict_ok = [bool]($result.ok -and (-not $StrictUx -or $result.ux_issues.Count -eq 0))
        run_dir = $RunDir
        result_json = $jsonPath
        summary_md = $summaryPath
        video = $videoPath
        screenshot = $screenshotPath
        actions = $result.actions.Count
        mechanics_failures = $result.mechanics_failures.Count
        ux_issues = $result.ux_issues.Count
        console = $result.console.Count
    } | ConvertTo-Json -Depth 4

    if (-not $result.ok) { exit 1 }
    if ($StrictUx -and $result.ux_issues.Count -gt 0) { exit 2 }
} finally {
    try { & npx.cmd --package "@playwright/cli" playwright-cli "-s=$Session" video-stop | Out-Null } catch {}
    try { & npx.cmd --package "@playwright/cli" playwright-cli "-s=$Session" close | Out-Null } catch {}
    if ($ServerProcess) {
        Stop-Process -Id $ServerProcess.Id -Force -ErrorAction SilentlyContinue
    }
}
