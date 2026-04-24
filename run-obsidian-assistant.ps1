param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$Args
)

$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new()

$ScriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$PythonScript = Join-Path $ScriptRoot "obsidian_assistant.py"
python $PythonScript @Args
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}
