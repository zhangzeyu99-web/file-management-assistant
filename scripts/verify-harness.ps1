param(
    [switch]$AllowDirty,
    [switch]$SkipDryRun,
    [switch]$SkipRemoteSync
)

$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new()

$RepoRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$Result = [ordered]@{
    ok = $false
    repo = $RepoRoot
    checks = [ordered]@{}
}

function Set-Check {
    param(
        [string]$Name,
        [bool]$Ok,
        [object]$Data = $null
    )
    $Result.checks[$Name] = [ordered]@{
        ok = $Ok
        data = $Data
    }
}

function Invoke-Checked {
    param(
        [string]$Name,
        [scriptblock]$Block
    )
    try {
        $data = & $Block
        Set-Check -Name $Name -Ok $true -Data $data
    }
    catch {
        Set-Check -Name $Name -Ok $false -Data $_.Exception.Message
    }
}

Push-Location $RepoRoot
try {
    Invoke-Checked "git_status" {
        $status = git status --short
        if ($LASTEXITCODE -ne 0) { throw "git status failed" }
        if ($status -and -not $AllowDirty) { throw "working tree is dirty: $status" }
        if ($status) { return $status }
        return "clean"
    }

    Invoke-Checked "unit_tests" {
        $output = cmd.exe /d /c "python .\tests\test_config_loader.py -v 2>&1 && python .\tests\test_file_assistant.py -v 2>&1 && python .\tests\test_obsidian_assistant.py -v 2>&1 && python .\tests\test_obsidian_manager.py -v 2>&1 && python .\tests\test_scenario_playbook.py -v 2>&1 && python .\tests\test_gui_server.py -v 2>&1 && python .\tests\test_assistant_evolution.py -v 2>&1 && python .\tests\test_project_quality.py -v 2>&1"
        $exitCode = $LASTEXITCODE
        if ($exitCode -ne 0) { throw ($output -join "`n") }
        return ($output -join "`n")
    }

    Invoke-Checked "secret_scan" {
        $patterns = @("gho_", "tenant_access_token", "app_secret", "sec_[A-Za-z0-9]", "Bearer ")
        $hits = @()
        foreach ($pattern in $patterns) {
            $found = rg -n $pattern . --glob "!scripts/verify-harness.ps1" 2>$null
            if ($LASTEXITCODE -eq 0 -and $found) {
                $hits += $found
            }
        }
        if ($hits.Count -gt 0) { throw ($hits -join "`n") }
        return "no forbidden token-like patterns found"
    }

    Invoke-Checked "dry_run" {
        if ($SkipDryRun) { return "skipped" }
        $output = powershell -NoProfile -ExecutionPolicy Bypass -File .\run-file-assistant.ps1 -Mode Test -SkipFeishu 2>&1
        if ($LASTEXITCODE -ne 0) { throw ($output -join "`n") }
        $jsonLine = ($output | Where-Object { $_ -match '^\{"ok":' } | Select-Object -Last 1)
        if (-not $jsonLine) { throw "runner did not return JSON result" }
        $parsed = $jsonLine | ConvertFrom-Json
        if (-not $parsed.ok) { throw "runner returned ok=false" }
        if (-not (Test-Path -LiteralPath $parsed.html_report)) { throw "missing html report: $($parsed.html_report)" }
        if (-not (Test-Path -LiteralPath $parsed.markdown_report)) { throw "missing markdown report: $($parsed.markdown_report)" }
        if (-not (Test-Path -LiteralPath $parsed.summary_json)) { throw "missing summary json: $($parsed.summary_json)" }
        return [ordered]@{
            total_files = $parsed.total_files
            html_report = $parsed.html_report
            summary_json = $parsed.summary_json
            obsidian_note = $parsed.obsidian_note
        }
    }

    Invoke-Checked "obsidian_manager_dry_run" {
        if ($SkipDryRun) { return "skipped" }
        $output = powershell -NoProfile -ExecutionPolicy Bypass -File .\run-obsidian-manager.ps1 -Mode Test -SkipFeishu 2>&1
        if ($LASTEXITCODE -ne 0) { throw ($output -join "`n") }
        $jsonLine = ($output | Where-Object { $_ -match '^\{"ok":' } | Select-Object -Last 1)
        if (-not $jsonLine) { throw "obsidian manager did not return JSON result" }
        $parsed = $jsonLine | ConvertFrom-Json
        if (-not $parsed.ok) { throw "obsidian manager returned ok=false" }
        if (-not (Test-Path -LiteralPath $parsed.markdown_report)) { throw "missing obsidian markdown report: $($parsed.markdown_report)" }
        if (-not (Test-Path -LiteralPath $parsed.summary_json)) { throw "missing obsidian summary json: $($parsed.summary_json)" }
        if (-not (Test-Path -LiteralPath $parsed.obsidian_note)) { throw "missing obsidian note: $($parsed.obsidian_note)" }
        return [ordered]@{
            total_notes = $parsed.total_notes
            markdown_report = $parsed.markdown_report
            summary_json = $parsed.summary_json
            obsidian_note = $parsed.obsidian_note
        }
    }

    Invoke-Checked "scheduled_task" {
        $task = Get-ScheduledTask -TaskName "Codex File Management Assistant" -TaskPath "\"
        $action = $task.Actions | Select-Object -First 1
        if ($task.State -notin @("Ready", "Running")) { throw "unexpected task state: $($task.State)" }
        if ($action.Arguments -notlike "*D:\codex\file-management-assistant\run-file-assistant.ps1*") {
            throw "scheduled task points to unexpected runner: $($action.Arguments)"
        }
        $info = Get-ScheduledTaskInfo -TaskName "Codex File Management Assistant" -TaskPath "\"
        return [ordered]@{
            state = [string]$task.State
            arguments = [string]$action.Arguments
            last_task_result = [int]$info.LastTaskResult
            next_run_time = [string]$info.NextRunTime
        }
    }

    Invoke-Checked "remote" {
        if ($SkipRemoteSync) { return "skipped" }
        $remoteUrl = git remote get-url origin
        if ($LASTEXITCODE -ne 0) { throw "git remote get-url failed" }
        if ($remoteUrl -notlike "*github.com/zhangzeyu99-web/file-management-assistant*") {
            throw "unexpected remote: $remoteUrl"
        }
        $head = git rev-parse HEAD
        if ($LASTEXITCODE -ne 0) { throw "git rev-parse failed" }
        $token = gh auth token
        $url = "https://x-access-token:$token@github.com/zhangzeyu99-web/file-management-assistant.git"
        $remote = git ls-remote $url refs/heads/main
        if ($LASTEXITCODE -ne 0) { throw "git ls-remote failed" }
        $remoteSha = ($remote -split "\s+")[0]
        if ($head -ne $remoteSha) {
            throw "local HEAD $head does not match remote main $remoteSha"
        }
        return [ordered]@{
            origin = $remoteUrl
            local_head = $head
            remote_main = $remoteSha
            synced = $true
        }
    }

    $failed = @($Result.checks.GetEnumerator() | Where-Object { -not $_.Value.ok })
    $Result.ok = ($failed.Count -eq 0)
    $Result | ConvertTo-Json -Depth 8
    if (-not $Result.ok) { exit 1 }
}
finally {
    Pop-Location
}
