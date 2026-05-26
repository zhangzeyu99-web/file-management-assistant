param(
    [switch]$Force,
    [switch]$Demo
)

$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new()

$RepoRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)

function ConvertTo-PrettyJson {
    param([object]$Value)
    $Value | ConvertTo-Json -Depth 10
}

function New-DemoConfig {
    param([string]$Root)

    $demoRoot = Join-Path $Root "demo"
    $vault = Join-Path $demoRoot "vault"
    $files = Join-Path $demoRoot "files"
    $runtime = Join-Path $demoRoot "runtime"
    $knowledgeRoot = Join-Path $vault "routine\knowledge-organizer"
    foreach ($path in @(
        $vault,
        $files,
        $runtime,
        $knowledgeRoot,
        (Join-Path $vault "inbox"),
        (Join-Path $vault "projects\Codex")
    )) {
        New-Item -ItemType Directory -Force -Path $path | Out-Null
    }

    Set-Content -LiteralPath (Join-Path $files "notebooklm-obsidian-tutorial.txt") -Encoding UTF8 -Value @(
        "NotebookLM and Obsidian beginner material.",
        "Goal: organize this as learning material and extract it as AI context later."
    )
    Set-Content -LiteralPath (Join-Path $vault "projects\Codex\legacy-chat-summary.md") -Encoding UTF8 -Value @(
        "# Legacy Chat Summary",
        "",
        "This file demonstrates that legacy AI chat notes can be indexed without moving or overwriting them."
    )

    return [ordered]@{
        runtime_root = $runtime
        obsidian_vault = $vault
        obsidian_run_dir = $knowledgeRoot
        knowledge_root = $knowledgeRoot
        codex_executable = ""
        allowed_open_roots = @($runtime, $vault, $files)
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
                name = "DemoFiles"
                path = $files
                max_depth = 3
                max_files = 500
            }
        )
        exclude_dir_names = @(".git", "__pycache__", ".venv", "venv", "node_modules", "tmp", "temp")
        recent_days = 7
        archive_after_days = 30
        installer_after_days = 14
        large_file_mb = 50
        hash_duplicate_min_mb = 5
        hash_duplicate_limit = 20
        top_limit = 10
        review_keywords = @("todo", "review", "report", "tutorial", "Obsidian", "AI")
    }
}

Push-Location $RepoRoot
try {
    $result = [ordered]@{
        ok = $false
        repo = $RepoRoot
        mode = if ($Demo) { "demo" } else { "local" }
        actions = @()
    }

    if ($Demo) {
        $config = New-DemoConfig -Root $RepoRoot
        $demoConfigTarget = ".\config.local.json"
        if ((Test-Path -LiteralPath $demoConfigTarget) -and -not $Force) {
            $demoConfigTarget = ".\config.demo.json"
            $result.actions += "kept existing config.local.json; wrote demo config to config.demo.json"
        }
        else {
            $result.actions += "created demo vault, demo files, and config.local.json"
        }
        ConvertTo-PrettyJson $config | Set-Content -LiteralPath $demoConfigTarget -Encoding UTF8
        $result.demo_config = (Resolve-Path -LiteralPath $demoConfigTarget).Path
    }
    elseif (-not (Test-Path -LiteralPath ".\config.local.json")) {
        Copy-Item -LiteralPath ".\config.example.json" -Destination ".\config.local.json"
        $result.actions += "created config.local.json from config.example.json"
    }
    elseif ($Force) {
        Copy-Item -LiteralPath ".\config.example.json" -Destination ".\config.local.json" -Force
        $result.actions += "recreated config.local.json because -Force was set"
    }
    else {
        $result.actions += "kept existing config.local.json"
    }

    $result.actions += "core loop only: initialize config and demo assets; do not run deprecated reminder or legacy index actions"

    $result.next = @(
        "powershell -NoProfile -ExecutionPolicy Bypass -File .\start-assistant-gui.ps1",
        "Open http://127.0.0.1:8765/",
        "Start from the three entries: add material, search review, generate AI context pack"
    )
    $result.ok = $true
    $result | ConvertTo-Json -Depth 8
}
finally {
    Pop-Location
}
