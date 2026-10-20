param(
    [string]$Config = "",
    [int]$ApiPort,
    [int]$WebPort,
    [switch]$NoBrowser
)

$ErrorActionPreference = "Stop"
$projectRoot = $PSScriptRoot
$launchLogs = Join-Path $projectRoot ".migration-staging\launcher"
New-Item -ItemType Directory -Path $launchLogs -Force | Out-Null
$log = Join-Path $launchLogs "launch.log"
try {
    $python = Get-Command py -ErrorAction SilentlyContinue
    $node = Get-Command node -ErrorAction SilentlyContinue
    if (-not $python -or -not $node) {
        throw "请先安装 Python 3.11 或更新版本（勾选 Python Launcher）和 Node.js 22.13 或更新版本，然后重新双击打开工作台。下载入口：https://www.python.org/downloads/windows/ 与 https://nodejs.org/"
    }
    & $python.Source -3 -c "import sys; raise SystemExit(0 if sys.version_info >= (3,11) else 1)"
    if ($LASTEXITCODE -ne 0) { throw "Python 版本过旧或不可用，请安装 Python 3.11 或更新版本后重试。" }
    & $node.Source -e "const [a,b]=process.versions.node.split('.').map(Number);process.exit(a>22||a===22&&b>=13?0:1)"
    if ($LASTEXITCODE -ne 0) { throw "Node.js 版本过旧，请安装 Node.js 22.13 或更新版本后重试。" }
    $environmentRoot = Join-Path $projectRoot ".venv"
    $environmentPython = Join-Path $environmentRoot "Scripts\python.exe"
    if (-not (Test-Path -LiteralPath $environmentPython)) {
        $create = Start-Process -FilePath $python.Source -WindowStyle Hidden -PassThru -Wait `
            -ArgumentList @("-3", "-m", "venv", ('"' + $environmentRoot + '"')) `
            -RedirectStandardOutput (Join-Path $launchLogs "python-environment.log") `
            -RedirectStandardError (Join-Path $launchLogs "python-environment-error.log")
        if ($create.ExitCode -ne 0) { throw "创建项目 Python 环境失败，请检查 Python 安装。日志：$launchLogs" }
    }
    & $environmentPython -c "import importlib.util; raise SystemExit(0 if all(importlib.util.find_spec(x) for x in ('pypdf','docx')) else 1)"
    if ($LASTEXITCODE -ne 0) {
        $install = Start-Process -FilePath $environmentPython -WindowStyle Hidden -PassThru -Wait `
            -ArgumentList @("-m", "pip", "install", "-r", ('"' + (Join-Path $projectRoot "requirements.txt") + '"')) `
            -RedirectStandardOutput (Join-Path $launchLogs "python-install.log") `
            -RedirectStandardError (Join-Path $launchLogs "python-install-error.log")
        if ($install.ExitCode -ne 0) { throw "Python 依赖安装失败，请检查网络后重试。安装日志：$launchLogs" }
    }
    $webRoot = Join-Path $projectRoot "web"
    if (-not (Test-Path -LiteralPath (Join-Path $webRoot "node_modules\vinext\dist\cli.js"))) {
        $npm = Get-Command npm.cmd -ErrorAction SilentlyContinue
        if (-not $npm) { throw "Node.js 未包含 npm，请重新安装完整的 Node.js。" }
        # The helper script contains only checked, fixed project paths.
        $installScript = Join-Path $launchLogs "install-web.ps1"
        $escapedNpm = $npm.Source.Replace("'", "''")
        $escapedWeb = $webRoot.Replace("'", "''")
        [IO.File]::WriteAllText($installScript,
            "Set-Location -LiteralPath '$escapedWeb'`n& '$escapedNpm' run install:ci`nexit `$LASTEXITCODE`n",
            [Text.UTF8Encoding]::new($true))
        $install = Start-Process -FilePath (Get-Process -Id $PID).Path -WindowStyle Hidden -PassThru -Wait `
            -ArgumentList @("-NoProfile", "-ExecutionPolicy", "Bypass", "-File", ('"' + $installScript + '"')) `
            -RedirectStandardOutput (Join-Path $launchLogs "web-install.log") `
            -RedirectStandardError (Join-Path $launchLogs "web-install-error.log")
        if ($install.ExitCode -ne 0) { throw "网页依赖安装失败，请检查网络后重试。安装日志：$launchLogs" }
    }
    $arguments = @{Bootstrap=$true}
    if ($Config) { $arguments.Config = $Config }
    if ($PSBoundParameters.ContainsKey("ApiPort")) { $arguments.ApiPort = $ApiPort }
    if ($PSBoundParameters.ContainsKey("WebPort")) { $arguments.WebPort = $WebPort }
    & (Join-Path $projectRoot "start.ps1") @arguments 2>&1 | Tee-Object -FilePath $log
    $summary = & (Join-Path $projectRoot "start.ps1") @arguments -Check | ConvertFrom-Json
    if (-not $NoBrowser) {
        $url = "http://127.0.0.1:$($summary.web_port)/"
        if ($summary.setup_required) { $url += "#migration" }
        # Opening the user's browser is the requested visible interactive result.
        Start-Process $url
    }
} catch {
    $_.Exception.Message | Out-File -LiteralPath $log -Encoding UTF8 -Append
    Add-Type -AssemblyName System.Windows.Forms
    [System.Windows.Forms.MessageBox]::Show($_.Exception.Message, "工作台未启动",
        [System.Windows.Forms.MessageBoxButtons]::OK, [System.Windows.Forms.MessageBoxIcon]::Error) | Out-Null
    exit 1
}
