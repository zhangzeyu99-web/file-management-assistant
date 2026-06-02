param(
    [string]$BaseUrl = "",
    [string]$Config = "",
    [int]$Port = 8769,
    [ValidateSet("chromium", "chrome", "firefox", "webkit", "msedge")]
    [string]$Browser = "chromium",
    [switch]$Headed,
    [switch]$StrictUx
)

$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new()

$Repo = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$Stamp = "$(Get-Date -Format "yyyyMMdd-HHmmss-fff")-$([guid]::NewGuid().ToString("N").Substring(0,8))"
$RunDir = Join-Path $Repo "output\real-query-gui-qa\$Stamp"
$Session = "real-query-gui-qa-$Stamp"
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

function Write-Summary {
    param($Result, [string]$Path)
    $lines = @(
        "# Real Query GUI QA",
        "",
        "- Base URL: $($Result.base_url)",
        "- Config: $($Result.config)",
        "- Mode: review + extract preview only",
        "- OK: $($Result.ok)",
        "- Cases: $($Result.summary.passed)/$($Result.summary.total) passed",
        "- Screenshot: $($Result.screenshot)",
        "",
        "| Query | Pass | Top source | Matched terms | Extract candidates |",
        "| --- | --- | --- | --- | --- |"
    )
    foreach ($case in $Result.cases) {
        $top = $case.review.top_source
        $terms = if ($top.matched_terms) { ($top.matched_terms -join ", ") } else { "-" }
        $lines += "| $($case.query) | $($case.passed) | $($top.title) | $terms | $($case.extract.source_count) |"
    }
    $lines += ""
    foreach ($case in $Result.cases) {
        $lines += "## $($case.query)"
        $lines += ""
        $lines += "- Pass: $($case.passed)"
        $lines += "- Review top source: $($case.review.top_source.title)"
        $lines += "- Source path: ``$($case.review.top_source.path)``"
        $lines += "- Evidence: $($case.review.top_source.evidence_excerpt)"
        if ($case.reasons.Count -gt 0) {
            $lines += "- Issues:"
            foreach ($reason in $case.reasons) {
                $lines += "  - $($reason.message)"
            }
        } else {
            $lines += "- Issues: none"
        }
        $lines += ""
    }
    $lines | Set-Content -Path $Path -Encoding UTF8
}

try {
    if (-not (Get-Command npx.cmd -ErrorAction SilentlyContinue)) {
        throw "npx.cmd is required. Install Node.js/npm first."
    }

    New-Item -ItemType Directory -Force -Path $RunDir | Out-Null
    if (-not $Config) {
        $Config = Join-Path $Repo "config.local.json"
    }
    if (-not $BaseUrl -and -not (Test-Path -LiteralPath $Config)) {
        $jsonPath = Join-Path $RunDir "gui-real-query-qa-result.json"
        $summaryPath = Join-Path $RunDir "gui-real-query-qa-summary.md"
        $result = [ordered]@{
            ok = $true
            status = "skipped"
            reason = "config.local.json not found; real local GUI query QA requires a configured local vault"
            run_dir = $RunDir
            json = $jsonPath
            markdown = $summaryPath
        }
        $result | ConvertTo-Json -Depth 8 | Set-Content -Path $jsonPath -Encoding UTF8
        @(
            "# Real Query GUI QA",
            "",
            "Skipped: config.local.json not found.",
            "",
            "Mode: review + extract preview only."
        ) | Set-Content -Path $summaryPath -Encoding UTF8
        $result | ConvertTo-Json -Depth 8
        return
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

    $TestUrl = Add-QueryParam -Url $BaseUrl -Name "realQueryGuiQa" -Value "1"
    $rawPath = Join-Path $RunDir "playwright-raw.txt"
    $jsonPath = Join-Path $RunDir "gui-real-query-qa-result.json"
    $summaryPath = Join-Path $RunDir "gui-real-query-qa-summary.md"
    $screenshotPath = Join-Path $RunDir "final-page.png"

    $openArgs = @("--package", "@playwright/cli", "playwright-cli", "-s=$Session", "open", $TestUrl)
    if ($Browser -ne "chromium") { $openArgs += @("--browser", $Browser) }
    if ($Headed) { $openArgs += "--headed" }
    & npx.cmd @openArgs | Out-Null
    & npx.cmd --package "@playwright/cli" playwright-cli "-s=$Session" resize 1440 960 | Out-Null
    $raw = & npx.cmd --package "@playwright/cli" playwright-cli "-s=$Session" --raw run-code --filename (Join-Path $Repo "scripts\gui-real-query-qa.js")
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
    $result | Add-Member -NotePropertyName "json" -NotePropertyValue $jsonPath -Force
    $result | Add-Member -NotePropertyName "markdown" -NotePropertyValue $summaryPath -Force
    $result | Add-Member -NotePropertyName "screenshot" -NotePropertyValue $screenshotPath -Force
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
        cases = $result.cases.Count
        passed = $result.summary.passed
        failed = $result.summary.failed
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
