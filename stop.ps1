param(
    [string]$Config = "",
    [int]$ApiPort
)

$ErrorActionPreference = "Stop"
$projectRoot = $PSScriptRoot
$pythonCommand = (Get-Command py -ErrorAction Stop).Source
$settingsArguments = @("-3", "-X", "utf8", "-c",
    "import sys; sys.path.insert(0, sys.argv.pop(1)); from engine.settings import main; raise SystemExit(main())",
    $projectRoot)
if ($Config) { $settingsArguments += @("--config", $Config) }
if ($PSBoundParameters.ContainsKey("ApiPort")) { $settingsArguments += @("--api-port", "$ApiPort") }
$settingsJson = & $pythonCommand @settingsArguments
if ($LASTEXITCODE -ne 0) { throw "停止配置校验失败；未停止任何进程。" }
$settings = $settingsJson | ConvertFrom-Json
$ApiPort = [int]$settings.port
$apiUri = "http://127.0.0.1:$ApiPort/api/workspace/health"

function Assert-Idle {
    try { $health = Invoke-RestMethod -Uri $apiUri -TimeoutSec 3 }
    catch { throw "API 状态无法确认；未停止进程。请检查端口 $ApiPort 的服务。" }
    if ($health.mode -ne "local" -or -not $health.PSObject.Properties["active_job"]) {
        throw "端口 $ApiPort 不是可核实的本机工作台；未停止进程。"
    }
    if ($health.active_job) {
        throw "任务 $($health.active_job) 正在执行；请等任务结束后再停止或迁移。"
    }
    return $health
}

function Get-ListeningProcess {
    $owners = @(Get-NetTCPConnection -State Listen -LocalPort $ApiPort -ErrorAction SilentlyContinue |
        Select-Object -ExpandProperty OwningProcess -Unique)
    if ($owners.Count -gt 1) { throw "端口 $ApiPort 对应多个进程；未停止进程。" }
    if ($owners.Count -eq 1) { return [int]$owners[0] }
    return $null
}

function Argument-Pattern([string]$Value) {
    $escaped = [regex]::Escape($Value)
    return '(?:"' + $escaped + '"|''' + $escaped + '''|' + $escaped + ')(?=\s|$)'
}

function Save-VerifiedWebOwner($ApiHealth) {
    $recordPath = Join-Path $settings.data_root "logs\last-start.json"
    $record = [pscustomobject]@{}
    if (Test-Path -LiteralPath $recordPath) {
        try { $record = Get-Content -LiteralPath $recordPath -Raw -Encoding UTF8 | ConvertFrom-Json }
        catch { throw "启动记录无法读取；未停止 API。请检查 $recordPath。" }
    }
    $webPort = [int]$settings.web_port
    if ($record.api_port -eq $ApiPort -and $record.web_port -ge 1 -and $record.web_port -le 65535) {
        $webPort = [int]$record.web_port
    }
    $webOwners = @(Get-NetTCPConnection -State Listen -LocalPort $webPort -ErrorAction SilentlyContinue |
        Select-Object -ExpandProperty OwningProcess -Unique)
    if ($webOwners.Count -eq 0) { return }
    $unverified = "网页归属未核实，已保留网页；下次启动不能自动复用缺失归属的旧网页，请先正常关闭该网页服务。"
    if (-not $ApiHealth.runtime_id) {
        Write-Warning "当前 API 尚未提供运行实例标识。$unverified"
        return
    }
    $node = if ($webOwners.Count -eq 1) {
        Get-CimInstance Win32_Process -Filter "ProcessId=$($webOwners[0])"
    } else { $null }
    $devVars = Join-Path $projectRoot "web\.dev.vars"
    $binding = if (Test-Path -LiteralPath $devVars) {
        [regex]::Match([IO.File]::ReadAllText($devVars, [Text.Encoding]::UTF8),
            '(?m)^OW_LOCAL_API\s*=\s*["'']?([^"''\r\n]+)["'']?\s*$')
    } else { $null }
    if (-not $node -or $node.Name -ne "node.exe" -or
        $node.CommandLine -notmatch '(?:^|\s)scripts[/\\]run-framework\.mjs(?:\s|$)' -or
        $node.CommandLine -notmatch ('(?:^|\s)--port(?:\s+|=)' + $webPort + '(?=\s|$)') -or
        -not $binding -or -not $binding.Success -or
        $binding.Groups[1].Value.Trim() -ne "http://127.0.0.1:$ApiPort" -or
        ($record.project_root -and $record.project_root -ne $projectRoot)) {
        Write-Warning $unverified
        return
    }
    try { $webHealth = Invoke-RestMethod -Uri "http://127.0.0.1:$webPort/api/workspace/health" -TimeoutSec 3 }
    catch { Write-Warning $unverified; return }
    $after = Assert-Idle
    $currentOwners = @(Get-NetTCPConnection -State Listen -LocalPort $webPort -ErrorAction SilentlyContinue |
        Select-Object -ExpandProperty OwningProcess -Unique)
    if ($webHealth.mode -ne "local" -or $webHealth.runtime_id -ne $ApiHealth.runtime_id -or
        $after.runtime_id -ne $ApiHealth.runtime_id -or $currentOwners.Count -ne 1 -or
        $currentOwners[0] -ne $node.ProcessId) {
        Write-Warning $unverified
        return
    }
    # Upgrade old records whose reused webpage had web_pid=null. The PID is
    # recorded only after both routes identify the same still-running API.
    $values = @{
        web_pid = [int]$node.ProcessId; project_root = $projectRoot
        api_port = $ApiPort; web_port = $webPort; data_root = $settings.data_root
        config_path = $settings.config_path; config_source = $settings.config_source
        web_verified_at = (Get-Date).ToString("o")
    }
    foreach ($key in $values.Keys) { $record | Add-Member -NotePropertyName $key -NotePropertyValue $values[$key] -Force }
    New-Item -ItemType Directory -Path (Split-Path -Parent $recordPath) -Force | Out-Null
    $record | ConvertTo-Json -Depth 10 | Set-Content -LiteralPath $recordPath -Encoding UTF8
}

$listener = Get-ListeningProcess
if ($listener) {
    $apiHealth = Assert-Idle
    $process = Get-CimInstance Win32_Process -Filter "ProcessId=$listener"
    $server = Join-Path $projectRoot "server.py"
    $serverPattern = '(?:^|\s)' + (Argument-Pattern $server)
    if (-not $process -or $process.Name -notmatch '^python(?:\d+(?:\.\d+)?)?w?\.exe$' -or
        $process.CommandLine -notmatch $serverPattern) {
        throw "端口 $ApiPort 的进程身份不匹配本项目 server.py；未停止进程。"
    }
    if ($settings.config_path) {
        $configPattern = '(?:^|\s)--config(?:\s+|=)' + (Argument-Pattern $settings.config_path)
        $selectedRuntime = $apiHealth.config_path -eq $settings.config_path -and
            $apiHealth.project_root -eq $projectRoot
        if ($process.CommandLine -notmatch $configPattern -and -not $selectedRuntime) {
            throw "运行进程使用其他配置；未停止进程。请传入启动时使用的 -Config。"
        }
    } elseif ($process.CommandLine -match '(?:^|\s)--config(?:\s|=)') {
        throw "运行进程使用显式配置；未停止进程。请传入启动时使用的 -Config。"
    }
    Save-VerifiedWebOwner $apiHealth
    # Recheck immediately before termination; never trust last-start's py launcher PID.
    $null = Assert-Idle
    if ((Get-ListeningProcess) -ne $listener) { throw "监听进程已变化；未停止进程。" }
    Stop-Process -Id $listener -ErrorAction Stop
    Wait-Process -Id $listener -Timeout 10 -ErrorAction SilentlyContinue
    $deadline = (Get-Date).AddSeconds(5)
    while ((Get-ListeningProcess) -and (Get-Date) -lt $deadline) { Start-Sleep -Milliseconds 200 }
    if (Get-ListeningProcess) { throw "API 端口仍被占用；未清理运行锁。" }
}

# The existing lock implementation only recovers a dead owner and acquires its
# OS guard first. It refuses live, malformed or concurrently changing markers.
$recoverCode = @'
import sys
from pathlib import Path
sys.path.insert(0, sys.argv[1])
from engine.incremental import writer_lock
for target in (Path(sys.argv[2]) / "executor.lock", Path(sys.argv[3]).with_suffix(".lock")):
    if target.exists():
        with writer_lock(target):
            pass
'@
& $pythonCommand -3 -X utf8 -c $recoverCode $projectRoot $settings.data_root $settings.state_path
if ($LASTEXITCODE -ne 0) {
    throw "执行器已停止或未监听，但运行锁仍活动或无法确认；未删除该锁，请检查其他写入者。"
}
Write-Output "本配置执行器已停止，可导出迁移包。网页进程保持原状；其他执行器请分别停止。"
