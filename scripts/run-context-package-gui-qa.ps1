param(
    [string]$BaseUrl = "",
    [string]$Config = "",
    [int]$Port = 8771,
    [ValidateSet("chromium", "chrome", "firefox", "webkit", "msedge")]
    [string]$Browser = "chromium",
    [switch]$Headed,
    [switch]$StrictUx
)

$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new()

$Repo = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$Stamp = "$(Get-Date -Format "yyyyMMdd-HHmmss-fff")-$([guid]::NewGuid().ToString("N").Substring(0,8))"
$RunDir = Join-Path $Repo "output\context-package-gui-qa\$Stamp"
$Session = "context-package-gui-qa-$Stamp"
$ServerProcess = $null
$StartedServer = $false

function Add-QueryParam {
    param([string]$Url, [string]$Name, [string]$Value)
    if ([string]::IsNullOrWhiteSpace($Value)) { return $Url }
    $separator = if ($Url.Contains("?")) { "&" } else { "?" }
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
    $vault = Join-Path $RunDir "demo-vault"
    $runtime = Join-Path $RunDir "demo-runtime"
    $knowledgeRoot = Join-Path $vault "04 例行工作\知识整理助手"
    $reviewDir = Join-Path $knowledgeRoot "回顾"
    $identityDir = Join-Path $knowledgeRoot "AI 身份文件"
    New-Item -ItemType Directory -Force -Path $reviewDir, $identityDir, $runtime | Out-Null

    $seedNoteContent = @(
        "# Obsidian 教程闭环证据",
        "",
        "类型：教程",
        "来源：context-package-gui-qa",
        "",
        "## 关键结论",
        "",
        "Obsidian 教程闭环证据：新手先掌握添加资料、搜索回顾、生成 AI 上下文包三件事。",
        "",
        "## 下一步",
        "",
        "继续用搜索结果加入上下文包，再确认生成可复制 prompt。"
    ) -join "`n"
    $seedNoteContent | Set-Content -Path (Join-Path $reviewDir "Obsidian 教程闭环证据.md") -Encoding UTF8

    $identityContent = @(
        "# AI 协作身份",
        "",
        "- 偏好：先给结论，再给依据。",
        "- 边界：只基于已整理来源，不编造当前状态。"
    ) -join "`n"
    $identityContent | Set-Content -Path (Join-Path $identityDir "AI_IDENTITY.md") -Encoding UTF8

    $configObject = [ordered]@{
        runtime_root = $runtime
        obsidian_vault = $vault
        obsidian_run_dir = $knowledgeRoot
        knowledge_root = $knowledgeRoot
        allowed_open_roots = @($vault, $runtime)
        obsidian_folders = [ordered]@{
            inbox = "00 收件箱"
            daily = "01 今日日志"
            projects = "02 项目"
            routine = "04 例行工作"
            templates = "90 模板"
            archive = "99 归档"
            codex_project = "Codex"
        }
        watch_roots = @(
            [ordered]@{
                name = "demo-vault-review"
                path = $reviewDir
                max_depth = 3
                max_files = 100
            }
        )
        exclude_dir_names = @(".git", "node_modules", "__pycache__")
    }
    $configObject | ConvertTo-Json -Depth 10 | Set-Content -Path $TargetConfig -Encoding UTF8
    return [ordered]@{
        demo_vault = $vault
        demo_runtime = $runtime
        seed_note = Join-Path $reviewDir "Obsidian 教程闭环证据.md"
    }
}

function Write-Summary {
    param($Result, [string]$Path)
    $lines = @(
        "# Context Package GUI QA",
        "",
        "- Runner: run-context-package-gui-qa.ps1",
        "- Base URL: $($Result.base_url)",
        "- Config: $($Result.config)",
        "- Demo vault: $($Result.demo_vault)",
        "- OK: $($Result.ok)",
        "- Generated markdown: ``$($Result.generated.generated_markdown)``",
        "- Generated Obsidian note: ``$($Result.generated.generated_obsidian_note)``",
        "- Screenshot: $($Result.screenshot)",
        "",
        "## Review",
        "",
        "- Top source: $($Result.review.top_source_title)",
        "- Source path: ``$($Result.review.top_source_path)``",
        "",
        "## Generated Prompt Preview",
        "",
        '```text',
        $Result.generated.generated_prompt,
        '```'
    )
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
        $Config = Join-Path $RunDir "config.context-package-gui-qa.json"
        $Demo = Initialize-DemoConfig -TargetConfig $Config
    } else {
        $Demo = [ordered]@{ demo_vault = ""; demo_runtime = ""; seed_note = "" }
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

    $TestUrl = Add-QueryParam -Url $BaseUrl -Name "contextPackageGuiQa" -Value "1"
    $rawPath = Join-Path $RunDir "playwright-raw.txt"
    $jsonPath = Join-Path $RunDir "gui-context-package-qa-result.json"
    $summaryPath = Join-Path $RunDir "gui-context-package-qa-summary.md"
    $screenshotPath = Join-Path $RunDir "final-page.png"

    $openArgs = @("--package", "@playwright/cli", "playwright-cli", "-s=$Session", "open", $TestUrl)
    if ($Browser -ne "chromium") { $openArgs += @("--browser", $Browser) }
    if ($Headed) { $openArgs += "--headed" }
    & npx.cmd @openArgs | Out-Null
    & npx.cmd --package "@playwright/cli" playwright-cli "-s=$Session" resize 1440 960 | Out-Null
    $raw = & npx.cmd --package "@playwright/cli" playwright-cli "-s=$Session" --raw run-code --filename (Join-Path $Repo "scripts\gui-context-package-qa.js")
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
    $result | Add-Member -NotePropertyName "demo_vault" -NotePropertyValue $Demo.demo_vault -Force
    $result | Add-Member -NotePropertyName "demo_runtime" -NotePropertyValue $Demo.demo_runtime -Force
    $result | Add-Member -NotePropertyName "seed_note" -NotePropertyValue $Demo.seed_note -Force
    $result | Add-Member -NotePropertyName "json" -NotePropertyValue $jsonPath -Force
    $result | Add-Member -NotePropertyName "markdown" -NotePropertyValue $summaryPath -Force
    $result | Add-Member -NotePropertyName "screenshot" -NotePropertyValue $screenshotPath -Force

    foreach ($requiredPath in @($result.generated.generated_markdown, $result.generated.generated_obsidian_note)) {
        if ([string]::IsNullOrWhiteSpace($requiredPath) -or -not (Test-Path -LiteralPath $requiredPath)) {
            throw "generated artifact missing: $requiredPath"
        }
    }
    if ($result.generated.generated_markdown -notlike "$($Demo.demo_runtime)*") {
        throw "generated_markdown is not under demo-runtime"
    }
    if ($result.generated.generated_obsidian_note -notlike "$($Demo.demo_vault)*") {
        throw "generated_obsidian_note is not under demo-vault"
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
        generated_prompt = [bool]$result.generated.generated_prompt
        generated_markdown = $result.generated.generated_markdown
        generated_obsidian_note = $result.generated.generated_obsidian_note
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

