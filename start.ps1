param(
    [string]$Config = "",
    [int]$ApiPort,
    [int]$WebPort,
    [switch]$Check,
    [switch]$Bootstrap
)

$ErrorActionPreference = "Stop"
$projectRoot = $PSScriptRoot
$webRoot = Join-Path $projectRoot "web"
$pythonCommand = (Get-Command py -ErrorAction Stop).Source
$pythonPrefix = @("-3")
$environmentPython = Join-Path $projectRoot ".venv\Scripts\python.exe"
if (Test-Path -LiteralPath $environmentPython) {
    $pythonCommand = $environmentPython
    $pythonPrefix = @()
}
# Resolve configuration once through Python, preserving the caller's working
# directory for explicit/OW_CONFIG paths. Only a non-secret startup summary is returned.
$settingsArguments = $pythonPrefix + @("-X", "utf8", "-c",
    "import sys; sys.path.insert(0, sys.argv.pop(1)); from engine.settings import main; raise SystemExit(main())",
    $projectRoot, "--check-startup")
if ($Config) { $settingsArguments += @("--config", $Config) }
if ($Bootstrap) { $settingsArguments += "--allow-setup" }
if ($PSBoundParameters.ContainsKey("ApiPort")) { $settingsArguments += @("--api-port", "$ApiPort") }
if ($PSBoundParameters.ContainsKey("WebPort")) { $settingsArguments += @("--web-port", "$WebPort") }
$settingsJson = & $pythonCommand @settingsArguments
if ($LASTEXITCODE -ne 0) { throw "启动配置校验失败；未创建检查点或启动服务。" }
$settings = $settingsJson | ConvertFrom-Json
$dataRoot = $settings.data_root
$Config = $settings.config_path
$ApiPort = [int]$settings.port
$WebPort = [int]$settings.web_port
if ($Check) {
    $settings | ConvertTo-Json -Compress
    return
}
$nodeCommand = (Get-Command node -ErrorAction Stop).Source
if (-not (Test-Path -LiteralPath (Join-Path $webRoot "node_modules\vinext\dist\cli.js"))) {
    throw "缺少网页依赖。请先进入 web 运行 npm install，再启动。"
}
$logRoot = Join-Path $dataRoot "logs"
New-Item -ItemType Directory -Path $logRoot -Force | Out-Null

function Get-WorkspaceHealth([string]$Uri) {
    try {
        $health = Invoke-RestMethod -Uri $Uri -TimeoutSec 2
        if ($health.mode -eq "local" -and ($health.worker_running -eq $true -or $health.setup_required -eq $true)) {
            return $health
        }
    } catch {}
    return $null
}

function Wait-WorkspaceHealth([string]$Uri, $Process, [int]$Seconds = 45) {
    $deadline = (Get-Date).AddSeconds($Seconds)
    do {
        $health = Get-WorkspaceHealth $Uri
        if ($health) { return $health }
        $Process.Refresh()
        if ($Process.HasExited) { throw "启动进程已退出，请查看 $logRoot 中的日志。" }
        Start-Sleep -Milliseconds 300
    } while ((Get-Date) -lt $deadline)
    throw "服务未在预期时间响应，请查看 $logRoot 中的日志。"
}

function Assert-PortAvailable([int]$Port) {
    if (Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue) {
        throw "端口 $Port 已被其他服务使用；未停止或替换该服务。"
    }
}

$apiUri = "http://127.0.0.1:$ApiPort/api/workspace/health"
$webUri = "http://127.0.0.1:$WebPort/api/workspace/health"
$devVars = Join-Path $webRoot ".dev.vars"
$binding = 'OW_LOCAL_API="http://127.0.0.1:' + $ApiPort + '"'
$text = ""
$withBom = $false
if (Test-Path -LiteralPath $devVars) {
    $bytes = [IO.File]::ReadAllBytes($devVars)
    $withBom = $bytes.Length -ge 3 -and $bytes[0] -eq 239 -and $bytes[1] -eq 187 -and $bytes[2] -eq 191
    $text = [IO.File]::ReadAllText($devVars, [Text.Encoding]::UTF8)
}
$previousBinding = [regex]::Match($text, '(?m)^OW_LOCAL_API\s*=\s*["'']?([^"''\r\n]+)["'']?\s*$')
if ($previousBinding.Success -and $previousBinding.Groups[1].Value.Trim() -ne "http://127.0.0.1:$ApiPort") {
    throw "本源码目录已有其他 API 绑定，网页共享 .dev.vars，不能并发切换资料库或端口。请使用独立源码副本；或停止本目录所有旧实例后手动移除 OW_LOCAL_API 再启动。未修改绑定或启动 API。"
}
$apiHealth = Get-WorkspaceHealth $apiUri
$webHealth = Get-WorkspaceHealth $webUri
$apiProcess = $null
$webProcess = $null
$verifiedSameConfig = $apiHealth -and $Config -and $apiHealth.config_path -eq $Config -and
    $apiHealth.project_root -eq $projectRoot
if ($apiHealth -and $Config -and -not $verifiedSameConfig) {
    throw "端口 $ApiPort 已有工作台运行，配置不能热切换。请正常停止后使用此配置重启；并发使用其他配置须使用独立源码副本。未停止现有服务。"
}
if ($apiHealth) {
    $owners = @(Get-NetTCPConnection -State Listen -LocalPort $ApiPort |
        Select-Object -ExpandProperty OwningProcess -Unique)
    $process = if ($owners.Count -eq 1) { Get-CimInstance Win32_Process -Filter "ProcessId=$($owners[0])" } else { $null }
    $serverPattern = '(?:^|\s)"?' + [regex]::Escape((Join-Path $projectRoot "server.py")) + '"?(?=\s|$)'
    if (-not $process -or $process.Name -notmatch '^python(?:\d+(?:\.\d+)?)?w?\.exe$' -or
        $process.CommandLine -notmatch $serverPattern -or
        (-not $verifiedSameConfig -and $process.CommandLine -match '(?:^|\s)--config(?:\s|=)')) {
        throw "API 端口对应其他项目或配置，不能复用；未启动服务。"
    }
} else {
    Assert-PortAvailable $ApiPort
}
$lastStart = Join-Path $logRoot "last-start.json"
$previous = $null
if (Test-Path -LiteralPath $lastStart) {
    try { $previous = Get-Content -LiteralPath $lastStart -Raw -Encoding UTF8 | ConvertFrom-Json }
    catch { throw "启动记录无法读取，请核实 $lastStart；未启动服务。" }
}
if ($previous -and $previous.web_port -ne $WebPort -and
    (Get-NetTCPConnection -State Listen -LocalPort $previous.web_port -ErrorAction SilentlyContinue)) {
    throw "本配置的旧网页仍在端口 $($previous.web_port) 运行。并发实例须使用独立源码副本；未启动服务。"
}
if (-not $webHealth) {
    $webOwners = @(Get-NetTCPConnection -State Listen -LocalPort $WebPort -ErrorAction SilentlyContinue |
        Select-Object -ExpandProperty OwningProcess -Unique)
    if ($webOwners.Count -gt 0) {
        # stop.ps1 deliberately leaves the webpage running. Its exact recorded
        # node process can be reused after the API has restarted.
        $knownWeb = if ($previous -and $webOwners.Count -eq 1 -and $previous.web_pid -eq $webOwners[0]) {
            Get-CimInstance Win32_Process -Filter "ProcessId=$($webOwners[0])"
        } else { $null }
        if (-not $knownWeb -or $knownWeb.Name -ne "node.exe" -or
            $knownWeb.CommandLine -notmatch '(?:^|\s)scripts[/\\]run-framework\.mjs(?:\s|$)' -or
            ($previous.project_root -and $previous.project_root -ne $projectRoot)) {
            throw "网页端口 $WebPort 已被其他进程使用；未启动 API。"
        }
        $webProcess = Get-Process -Id $knownWeb.ProcessId
    }
}

if (-not $apiHealth) {
    $arguments = $pythonPrefix + @("-X", "utf8", ('"' + (Join-Path $projectRoot "server.py") + '"'),
        "--port", "$ApiPort", "--web-port", "$WebPort")
    if ($Config) { $arguments += @("--config", ('"' + $Config + '"')) }
    if ($Bootstrap) { $arguments += "--allow-setup" }
    # Preserve the official desktop bridge's current native tool context.
    $apiProcess = Start-Process -FilePath $pythonCommand -ArgumentList $arguments `
        -WorkingDirectory $projectRoot -WindowStyle Hidden -PassThru `
        -RedirectStandardOutput (Join-Path $logRoot "api.stdout.log") `
        -RedirectStandardError (Join-Path $logRoot "api.stderr.log")
    $apiHealth = Wait-WorkspaceHealth $apiUri $apiProcess
}
if ($text -match '(?m)^OW_LOCAL_API\s*=') {
    $text = [regex]::Replace($text, '(?m)^OW_LOCAL_API\s*=[^\r\n]*', $binding)
} else {
    $newline = if ($text.Contains("`r`n")) { "`r`n" } else { "`n" }
    if ($text -and -not $text.EndsWith("`n")) { $text += $newline }
    $text += $binding + $newline
}
[IO.File]::WriteAllText($devVars, $text, [Text.UTF8Encoding]::new($withBom))

if (-not $webHealth -and -not $webProcess) {
    $webProcess = Start-Process -FilePath $nodeCommand `
        -ArgumentList @("scripts/run-framework.mjs", "dev", "--port", "$WebPort", "--hostname", "127.0.0.1") `
        -WorkingDirectory $webRoot -WindowStyle Hidden -PassThru `
        -RedirectStandardOutput (Join-Path $logRoot "web.stdout.log") `
        -RedirectStandardError (Join-Path $logRoot "web.stderr.log")
}
if (-not $webHealth) { $webHealth = Wait-WorkspaceHealth $webUri $webProcess }

$record = @{
    started_at = (Get-Date).ToString("o")
    api_port = $ApiPort
    web_port = $WebPort
    config_path = $Config
    config_source = $settings.config_source
    data_root = $dataRoot
    project_root = $projectRoot
    api_pid = if ($apiProcess) { $apiProcess.Id } else { $null }
    web_pid = if ($webProcess) { $webProcess.Id } elseif ($previous) { $previous.web_pid } else { $null }
    native_context_available = [bool]$apiHealth.native_context
}
$record | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $logRoot "last-start.json") -Encoding UTF8
Write-Output "个人知识工作台：http://127.0.0.1:$WebPort/"
Write-Output "日志目录：$logRoot"
if (-not $apiHealth.native_context) {
    Write-Output "当前进程没有原生对话上下文；网页阅读和已接通的模型仍可用，Codex 对话更新会显示未检查。"
}
