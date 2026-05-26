param(
    [string]$TaskName = "Knowledge Organizer Assistant",
    [string]$At = "09:00"
)

$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new()

[ordered]@{
    ok = $false
    status = "deprecated"
    task_name = $TaskName
    requested_at = $At
    summary = "scheduled task reminder is deprecated; core loop only keeps organize, review, extract"
    next_actions = @("organize", "review", "extract")
} | ConvertTo-Json -Depth 4 -Compress
