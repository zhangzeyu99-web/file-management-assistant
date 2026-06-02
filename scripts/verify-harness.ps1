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
        $output = cmd.exe /d /c "python .\tests\test_config_loader.py -v 2>&1 && python .\tests\test_file_assistant.py -v 2>&1 && python .\tests\test_obsidian_assistant.py -v 2>&1 && python .\tests\test_obsidian_manager.py -v 2>&1 && python .\tests\test_scenario_playbook.py -v 2>&1 && python .\tests\test_knowledge_assistant.py -v 2>&1 && python .\tests\test_gui_server.py -v 2>&1 && python .\tests\test_assistant_evolution.py -v 2>&1 && python .\tests\test_project_quality.py -v 2>&1"
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

    Invoke-Checked "feature_contracts" {
        $output = python -X utf8 .\scripts\audit-feature-contracts.py 2>&1
        if ($LASTEXITCODE -ne 0) { throw ($output -join "`n") }
        $parsed = $output -join "`n" | ConvertFrom-Json
        if (-not $parsed.ok) { throw "feature contract audit returned ok=false" }
        if (-not (Test-Path -LiteralPath $parsed.json)) { throw "missing feature contract json: $($parsed.json)" }
        if (-not (Test-Path -LiteralPath $parsed.markdown)) { throw "missing feature contract markdown: $($parsed.markdown)" }
        return $parsed
    }

    Invoke-Checked "real_query_qa" {
        if (-not (Test-Path -LiteralPath ".\config.local.json")) {
            return [ordered]@{
                status = "skipped"
                reason = "config.local.json not found; real local Obsidian query QA requires a configured local vault"
            }
        }
        $output = python -X utf8 .\scripts\run-real-query-qa.py 2>&1
        if ($LASTEXITCODE -ne 0) { throw ($output -join "`n") }
        $parsed = $output -join "`n" | ConvertFrom-Json
        if (-not $parsed.ok) { throw "real query QA returned ok=false" }
        if (-not (Test-Path -LiteralPath $parsed.json)) { throw "missing real query QA json: $($parsed.json)" }
        if (-not (Test-Path -LiteralPath $parsed.markdown)) { throw "missing real query QA markdown: $($parsed.markdown)" }
        return $parsed
    }

    Invoke-Checked "real_query_gui_qa" {
        if (-not (Test-Path -LiteralPath ".\config.local.json")) {
            return [ordered]@{
                status = "skipped"
                reason = "config.local.json not found; real local GUI query QA requires a configured local vault"
            }
        }
        $output = powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\run-real-query-gui-qa.ps1 -StrictUx 2>&1
        if ($LASTEXITCODE -ne 0) { throw ($output -join "`n") }
        $parsed = $output -join "`n" | ConvertFrom-Json
        if (-not $parsed.ok -or -not $parsed.strict_ok) { throw "real query GUI QA returned failing result" }
        if (-not (Test-Path -LiteralPath $parsed.json)) { throw "missing real query GUI QA json: $($parsed.json)" }
        if (-not (Test-Path -LiteralPath $parsed.markdown)) { throw "missing real query GUI QA markdown: $($parsed.markdown)" }
        if (-not (Test-Path -LiteralPath $parsed.screenshot)) { throw "missing real query GUI QA screenshot: $($parsed.screenshot)" }
        return $parsed
    }

    Invoke-Checked "core_loop_real" {
        if ($SkipDryRun) { return "skipped" }
        $python = @'
import json, shutil
from pathlib import Path
import knowledge_assistant

root = Path("output") / "harness-core-loop"
if root.exists():
    shutil.rmtree(root)
source = root / "source"
vault = root / "vault"
runtime = root / "runtime"
knowledge_root = vault / "routine" / "knowledge-organizer"
for path in (source, runtime, knowledge_root):
    path.mkdir(parents=True, exist_ok=True)
(source / "evidence.md").write_text("# Evidence\n\nHarnessCoreLoopEvidence: organize review extract.\n", encoding="utf-8")
config_path = root / "config.json"
config_path.write_text(json.dumps({
    "runtime_root": str(runtime),
    "obsidian_vault": str(vault),
    "obsidian_run_dir": str(knowledge_root),
    "knowledge_root": str(knowledge_root),
    "allowed_open_roots": [str(root)],
    "obsidian_folders": {"routine": "routine", "projects": "projects", "codex_project": "Codex"},
    "watch_roots": [{"name": "harness", "path": str(source), "max_depth": 2, "max_files": 100}],
}, ensure_ascii=False, indent=2), encoding="utf-8")

organize = knowledge_assistant.run_action("organize", {"local_paths": str(source), "text": "HarnessCoreLoopEvidence"}, config_path)
review = knowledge_assistant.run_action("review", {"query": "HarnessCoreLoopEvidence"}, config_path)
preview = knowledge_assistant.run_action("extract", {"query": "HarnessCoreLoopEvidence", "request": "Build context.", "mode": "preview"}, config_path)
generate = knowledge_assistant.run_action("extract", {
    "query": "HarnessCoreLoopEvidence",
    "request": "Build context.",
    "mode": "generate",
    "source_paths": [item["path"] for item in preview.get("sources", [])],
}, config_path)
prompt = next((item.get("content", "") for item in generate.get("artifacts", []) if item.get("type") == "prompt"), "")
result = {
    "ok": all([organize.get("ok"), review.get("ok"), preview.get("ok"), generate.get("ok")]) and "HarnessCoreLoopEvidence" in prompt and "\u5148\u5f15\u7528\u6765\u6e90\u8def\u5f84" in prompt,
    "ingested_files": organize.get("debug", {}).get("scan", {}).get("total_files"),
    "review_sources": len(review.get("sources", [])),
    "preview_sources": len(preview.get("sources", [])),
    "generated_artifacts": [item.get("type") for item in generate.get("artifacts", [])],
}
print(json.dumps(result, ensure_ascii=False, separators=(",", ":")))
if not result["ok"]:
    raise SystemExit(1)
'@
        $output = $python | python -X utf8 -
        if ($LASTEXITCODE -ne 0) { throw ($output -join "`n") }
        $parsed = ($output -join "`n") | ConvertFrom-Json
        if (-not $parsed.ok) { throw "core loop real test returned ok=false" }
        return $parsed
    }

    Invoke-Checked "scheduled_task_deprecated" {
        $output = powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\install-scheduled-task.ps1 2>&1
        if ($LASTEXITCODE -ne 0) { throw ($output -join "`n") }
        $jsonLine = ($output | Where-Object { $_ -match '^\{' } | Select-Object -Last 1)
        if (-not $jsonLine) { throw "deprecated scheduled task script did not return JSON" }
        $parsed = $jsonLine | ConvertFrom-Json
        if ($parsed.ok -or $parsed.status -ne "deprecated") { throw "scheduled task script should be deprecated" }
        return [ordered]@{
            status = [string]$parsed.status
            summary = [string]$parsed.summary
        }
    }

    Invoke-Checked "gui_e2e" {
        $output = powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\run-gui-e2e.ps1 -ReadOnly -StrictUx 2>&1
        if ($LASTEXITCODE -ne 0) { throw ($output -join "`n") }
        $jsonLine = ($output | Where-Object { $_ -match '^\{' } | Select-Object -Last 1)
        if (-not $jsonLine) { throw "GUI E2E did not return JSON result" }
        $parsed = $output -join "`n" | ConvertFrom-Json
        if (-not $parsed.ok -or -not $parsed.strict_ok) { throw "GUI E2E returned failing result" }
        return $parsed
    }

    Invoke-Checked "backup_manifest" {
        $output = powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\export-backup-manifest.ps1 2>&1
        if ($LASTEXITCODE -ne 0) { throw ($output -join "`n") }
        $parsed = $output -join "`n" | ConvertFrom-Json
        if (-not $parsed.ok) { throw "backup manifest returned ok=false" }
        if (-not (Test-Path -LiteralPath $parsed.output)) { throw "manifest output missing: $($parsed.output)" }
        if ($parsed.excluded_private_scope -notcontains "config.local.json") { throw "manifest does not document config.local.json exclusion" }
        return [ordered]@{
            commit = $parsed.commit
            origin = $parsed.origin
            output = $parsed.output
            restore_commands = $parsed.restore_commands
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
