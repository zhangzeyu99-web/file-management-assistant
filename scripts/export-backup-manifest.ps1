param(
    [string]$Output = ""
)

$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new()

$RepoRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Push-Location $RepoRoot
try {
    $head = (git rev-parse HEAD).Trim()
    if ($LASTEXITCODE -ne 0) { throw "git rev-parse HEAD failed" }
    $branch = (git branch --show-current).Trim()
    if ($LASTEXITCODE -ne 0) { throw "git branch --show-current failed" }
    $origin = (git remote get-url origin).Trim()
    if ($LASTEXITCODE -ne 0) { throw "git remote get-url origin failed" }
    $status = git status --short

    $manifest = [ordered]@{
        ok = $true
        generated_at = (Get-Date).ToString("s")
        repository = $RepoRoot
        branch = $branch
        commit = $head
        origin = $origin
        cloud_backup_scope = @(
            "code",
            "docs",
            "templates",
            "tests",
            "config.example.json",
            "scripts"
        )
        excluded_private_scope = @(
            "config.local.json",
            "output/",
            "runtime/",
            "personal Obsidian content is not committed to the public repository"
        )
        restore_commands = @(
            "git clone $origin",
            "cd file-management-assistant",
            "powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\init-assistant.ps1 -Demo",
            "powershell -NoProfile -ExecutionPolicy Bypass -File .\start-assistant-gui.ps1"
        )
        dirty_files = @($status)
    }

    if ([string]::IsNullOrWhiteSpace($Output)) {
        $Output = Join-Path $RepoRoot "output\backup-manifest.json"
    }
    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $Output) | Out-Null
    $manifest | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $Output -Encoding UTF8
    $manifest.output = $Output
    $manifest | ConvertTo-Json -Depth 8
}
finally {
    Pop-Location
}
