param(
    [switch]$Force,
    [switch]$SkipGuide,
    [switch]$SkipScenario
)

$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new()

$RepoRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Push-Location $RepoRoot
try {
    $result = [ordered]@{
        ok = $false
        repo = $RepoRoot
        actions = @()
    }

    if (-not (Test-Path -LiteralPath ".\config.local.json")) {
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

    if (-not $SkipGuide) {
        $guide = python .\obsidian_assistant.py --config .\config.json guide | ConvertFrom-Json
        if (-not $guide.ok) { throw "guide generation failed" }
        $result.guide = $guide.guide
        $result.actions += "generated Obsidian guide"
    }

    if (-not $SkipScenario) {
        $scenario = python .\scenario_playbook.py demo --config .\config.json | ConvertFrom-Json
        if (-not $scenario.ok) { throw "scenario demo failed" }
        $result.scenario_report = $scenario.markdown_report
        $result.scenario_note = $scenario.obsidian_note
        $result.actions += "generated scenario demo"
    }

    $evolution = python .\assistant_evolution.py report --config .\config.json | ConvertFrom-Json
    if (-not $evolution.ok) { throw "self-evolution report failed" }
    $result.evolution_report = $evolution.markdown_report
    $result.evolution_note = $evolution.obsidian_note
    $result.actions += "generated self-evolution report"

    $result.next = @(
        "Run .\start-assistant-gui.ps1",
        "Click 今天先干什么",
        "Use docs\guidebook\knowledge-action-assistant-tutorial.pdf as the first tutorial"
    )
    $result.ok = $true
    $result | ConvertTo-Json -Depth 6
}
finally {
    Pop-Location
}
