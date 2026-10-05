<#
.SYNOPSIS
    Stops or removes the Job-AI Continuous 24-Hour Monitor Windows Scheduled Task.
.DESCRIPTION
    Stops running instances of "JobAICareerMonitor" and optionally unregisters it.
.PARAMETER Remove
    If specified, unregisters and deletes the task from Windows Task Scheduler.
#>

param(
    [switch]$Remove
)

$TaskName = "JobAICareerMonitor"

try {
    $Task = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
    if (-not $Task) {
        Write-Host "[INFO] Scheduled task '$TaskName' is not registered." -ForegroundColor Yellow
        exit 0
    }

    if ($Task.State -eq "Running") {
        Write-Host "[INFO] Stopping running task '$TaskName'..." -ForegroundColor Cyan
        Stop-ScheduledTask -TaskName $TaskName
        Start-Sleep -Seconds 2
        Write-Host "[OK] Task stopped." -ForegroundColor Green
    } else {
        Write-Host "[INFO] Task '$TaskName' is not currently running (State: $($Task.State))." -ForegroundColor Gray
    }

    if ($Remove) {
        Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
        Write-Host "[OK] Task '$TaskName' unregistered from Windows Task Scheduler." -ForegroundColor Green
    }
} catch {
    Write-Error "Failed to manage task '$TaskName': $_"
    exit 1
}
