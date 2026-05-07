param(
    [string]$BaseUrl = "",
    [int]$Port = 8767,
    [switch]$Headed,
    [switch]$StrictUx,
    [switch]$ReadOnly,
    [switch]$IncludeOpeners
)

$ErrorActionPreference = "Stop"
$Repo = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$Stamp = "$(Get-Date -Format "yyyyMMdd-HHmmss-fff")-$([guid]::NewGuid().ToString("N").Substring(0,8))"
$RunDir = Join-Path $Repo "output\gui-e2e\$Stamp"
$ConfigPath = Join-Path $RunDir "config.gui-e2e.json"
$ServerProcess = $null
$Session = "gui-e2e-$Stamp"

function New-FixtureConfig {
    New-Item -ItemType Directory -Force -Path $RunDir | Out-Null
    $fixture = Join-Path $RunDir "fixture-files"
    $vault = Join-Path $RunDir "vault"
    $runtime = Join-Path $RunDir "runtime"
    $obsidianRun = Join-Path $vault "routine\knowledge-action-assistant"

    foreach ($path in @(
        $fixture,
        $runtime,
        (Join-Path $vault "inbox"),
        (Join-Path $vault "daily"),
        (Join-Path $vault "projects\knowledge-action-assistant\Card"),
        $obsidianRun
    )) {
        New-Item -ItemType Directory -Force -Path $path | Out-Null
    }

    Set-Content -Path (Join-Path $fixture "2026-05-07-gui-e2e-todo-report.md") -Value "# GUI E2E todo report`n`n- Check raw JSON output`n- Check file input area" -Encoding UTF8
    Set-Content -Path (Join-Path $fixture "notebooklm-obsidian-tutorial.txt") -Value "NotebookLM and Obsidian learning material for reusable notes." -Encoding UTF8
    Set-Content -Path (Join-Path $fixture "work-project-review.csv") -Value "task,status`nGUI E2E,done" -Encoding UTF8
    Set-Content -Path (Join-Path $vault "projects\knowledge-action-assistant\Card\gui-result-card.md") -Value "# GUI result card`n`nType: Card`nSource: E2E fixture`n`n## Key conclusion`n`nThe result area should show human-readable cards instead of default JSON." -Encoding UTF8

    $oldFile = Join-Path $fixture "old-installer.exe"
    Set-Content -Path $oldFile -Value "fake installer" -Encoding ASCII
    (Get-Item $oldFile).LastWriteTime = (Get-Date).AddDays(-45)

    $config = [ordered]@{
        runtime_root = $runtime
        obsidian_vault = $vault
        obsidian_run_dir = $obsidianRun
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
                name = "GuiE2EFixture"
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
        review_keywords = @("todo", "review", "report", "tutorial")
    }
    $config | ConvertTo-Json -Depth 8 | Set-Content -Path $ConfigPath -Encoding UTF8
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
    $deadline = (Get-Date).AddSeconds(20)
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

function Get-ResultPaths {
    param($Value)
    $paths = New-Object System.Collections.Generic.List[string]
    function Visit($node) {
        if ($null -eq $node) { return }
        if ($node -is [string]) {
            if ($node -match '^[A-Za-z]:\\') { $paths.Add($node) }
            return
        }
        if ($node -is [System.Collections.IDictionary]) {
            foreach ($key in $node.Keys) { Visit $node[$key] }
            return
        }
        if ($node -is [pscustomobject]) {
            foreach ($property in $node.PSObject.Properties) { Visit $property.Value }
            return
        }
        if ($node -is [System.Collections.IEnumerable] -and -not ($node -is [string])) {
            foreach ($item in $node) { Visit $item }
        }
    }
    Visit $Value
    return @($paths | Select-Object -Unique)
}

try {
    if (-not (Get-Command npx.cmd -ErrorAction SilentlyContinue)) {
        throw "npx.cmd is required. Install Node.js/npm first."
    }

    if (-not $BaseUrl) {
        New-FixtureConfig
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
        Wait-HttpOk -Url $BaseUrl
    } else {
        New-Item -ItemType Directory -Force -Path $RunDir | Out-Null
        Wait-HttpOk -Url $BaseUrl
    }

    $TestUrl = $BaseUrl
    if ($IncludeOpeners) {
        $separator = if ($TestUrl.Contains("?")) { "&" } else { "?" }
        $TestUrl = "$TestUrl${separator}includeOpeners=1"
    }
    if ($ReadOnly) {
        $separator = if ($TestUrl.Contains("?")) { "&" } else { "?" }
        $TestUrl = "$TestUrl${separator}readOnly=1"
    }

    $openArgs = @("--package", "@playwright/cli", "playwright-cli", "-s=$Session", "open", $TestUrl)
    if ($Headed) { $openArgs += "--headed" }
    & npx.cmd @openArgs | Out-Null

    & npx.cmd --package "@playwright/cli" playwright-cli "-s=$Session" resize 1680 950 | Out-Null
    $raw = & npx.cmd --package "@playwright/cli" playwright-cli "-s=$Session" --raw run-code --filename (Join-Path $Repo "scripts\gui-e2e-playwright.js")
    $rawText = ($raw -join "`n").Trim()
    $rawPath = Join-Path $RunDir "playwright-raw.txt"
    $rawText | Set-Content -Path $rawPath -Encoding UTF8
    $jsonStart = $rawText.IndexOf("{")
    $jsonEnd = $rawText.LastIndexOf("}")
    if ($jsonStart -lt 0 -or $jsonEnd -le $jsonStart) {
        throw "Playwright did not return JSON. Raw output saved to $rawPath"
    }
    $result = $rawText.Substring($jsonStart, $jsonEnd - $jsonStart + 1) | ConvertFrom-Json

    $screenshot = Join-Path $RunDir "final-page.png"
    & npx.cmd --package "@playwright/cli" playwright-cli "-s=$Session" screenshot --filename $screenshot | Out-Null
    & npx.cmd --package "@playwright/cli" playwright-cli "-s=$Session" close | Out-Null

    $result | Add-Member -NotePropertyName "base_url" -NotePropertyValue $BaseUrl -Force
    $result | Add-Member -NotePropertyName "run_dir" -NotePropertyValue $RunDir -Force
    $result | Add-Member -NotePropertyName "screenshot" -NotePropertyValue $screenshot -Force

    $pathChecks = @()
    foreach ($action in $result.actions) {
        foreach ($path in (Get-ResultPaths $action.response)) {
            $item = Get-Item -LiteralPath $path -ErrorAction SilentlyContinue
            $pathChecks += [ordered]@{
                action = $action.expected_action
                path = $path
                exists = [bool]$item
                last_write_time = if ($item) { $item.LastWriteTime.ToString("s") } else { $null }
            }
            if (-not $item) {
                $result.ok = $false
                $result.mechanics_failures += [pscustomobject]@{
                    message = "action returned a path that does not exist"
                    action = $action.expected_action
                    path = $path
                }
            }
        }
    }
    $result | Add-Member -NotePropertyName "path_checks" -NotePropertyValue $pathChecks -Force

    $jsonPath = Join-Path $RunDir "gui-e2e-result.json"
    $mdPath = Join-Path $RunDir "gui-e2e-summary.md"
    $result | ConvertTo-Json -Depth 20 | Set-Content -Path $jsonPath -Encoding UTF8

    $lines = @(
        "# GUI E2E Playwright Report",
        "",
        "- Base URL: $BaseUrl",
        "- Test URL: $TestUrl",
        "- Include external openers: $($result.include_openers)",
        "- Read-only smoke mode: $($result.read_only)",
        "- OK: $($result.ok)",
        "- Actions: $($result.actions.Count)",
        "- Mechanics failures: $($result.mechanics_failures.Count)",
        "- UX issues: $($result.ux_issues.Count)",
        "- Screenshot: $screenshot",
        "",
        "## Actions"
    )
    foreach ($action in $result.actions) {
        $lines += "- $($action.label) -> $($action.request_action) http=$($action.http_status) ok=$($action.ok) output_json=$($action.output_looks_like_json)"
    }
    $lines += ""
    $lines += "## Skipped"
    if ($result.skipped.Count -eq 0) {
        $lines += "- None"
    } else {
        foreach ($skip in $result.skipped) {
            $lines += "- $($skip.label) -> $($skip.action): $($skip.reason)"
        }
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
    $lines += "## Path Checks"
    foreach ($check in $pathChecks) {
        $lines += "- $($check.action): exists=$($check.exists) $($check.path)"
    }
    $lines | Set-Content -Path $mdPath -Encoding UTF8

    [ordered]@{
        ok = [bool]$result.ok
        strict_ok = [bool]($result.ok -and (-not $StrictUx -or $result.ux_issues.Count -eq 0))
        run_dir = $RunDir
        result_json = $jsonPath
        summary_md = $mdPath
        screenshot = $screenshot
        actions = $result.actions.Count
        mechanics_failures = $result.mechanics_failures.Count
        ux_issues = $result.ux_issues.Count
    } | ConvertTo-Json -Depth 4

    if (-not $result.ok) { exit 1 }
    if ($StrictUx -and $result.ux_issues.Count -gt 0) { exit 2 }
} finally {
    try {
        & npx.cmd --package "@playwright/cli" playwright-cli "-s=$Session" close | Out-Null
    } catch {}
    if ($ServerProcess) {
        Stop-Process -Id $ServerProcess.Id -Force -ErrorAction SilentlyContinue
    }
}
