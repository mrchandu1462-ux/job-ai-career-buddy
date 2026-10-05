<#
.SYNOPSIS
    Registers the Job-AI Continuous 24-Hour Monitor as a Windows Scheduled Task.
.DESCRIPTION
    Creates or updates the "JobAICareerMonitor" scheduled task in Windows Task Scheduler.
    Configured to start at user logon, run in the background, restart on failure,
    and log stdout/stderr to logs/monitor.log.
.PARAMETER Interval
    Scan interval in minutes (default: 60).
.PARAMETER Region
    Geographic focus: 'all' (default), 'india', or 'overseas'.
.PARAMETER Hours
    Freshness window in hours (default: 24.0).
.PARAMETER StartNow
    If specified, immediately starts the scheduled task after registration.
#>

param(
    [int]$Interval = 60,
    [ValidateSet("all", "india", "overseas")]
    [string]$Region = "all",
    [double]$Hours = 24.0,
    [switch]$StartNow
)

$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Split-Path -Parent $ScriptDir
Set-Location -Path $ProjectRoot

# 1. Resolve Python Interpreter
$PythonExe = ""
$VenvPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"

if (Test-Path $VenvPython) {
    $PythonExe = $VenvPython
} else {
    $SystemPython = (Get-Command python.exe -ErrorAction SilentlyContinue)
    if ($SystemPython) {
        $PythonExe = $SystemPython.Source
    } else {
        Write-Error "Could not locate python.exe in .venv or system PATH."
        exit 1
    }
}

# 2. Ensure Logs Directory Exists
$LogDir = Join-Path $ProjectRoot "logs"
if (-not (Test-Path $LogDir)) {
    New-Item -ItemType Directory -Path $LogDir | Out-Null
}

$TaskName = "JobAICareerMonitor"

# 3. Create Scheduled Task Components
$Arguments = "-m app.jobs.monitor --region $Region --hours $Hours --interval $Interval"
$Action = New-ScheduledTaskAction -Execute $PythonExe -Argument $Arguments -WorkingDirectory $ProjectRoot
$Trigger = New-ScheduledTaskTrigger -AtLogOn

$Settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -ExecutionTimeLimit (New-TimeSpan -Days 365) `
    -MultipleInstances IgnoreNew `
    -RestartCount 3 `
    -RestartInterval (New-TimeSpan -Minutes 5)

# 4. Register Task
try {
    # Unregister existing task if present to avoid conflicts
    $Existing = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
    if ($Existing) {
        Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
    }

    Register-ScheduledTask `
        -TaskName $TaskName `
        -Action $Action `
        -Trigger $Trigger `
        -Settings $Settings `
        -Description "Job-AI Continuous 24-Hour Semiconductor Job Monitor Daemon" | Out-Null

    Write-Host "======================================================================" -ForegroundColor Green
    Write-Host "[OK] Task '$TaskName' successfully registered in Windows Task Scheduler!" -ForegroundColor Green
    Write-Host "Trigger       : At User Logon" -ForegroundColor Gray
    Write-Host "Command       : $PythonExe $Arguments" -ForegroundColor Gray
    Write-Host "Working Dir   : $ProjectRoot" -ForegroundColor Gray
    Write-Host "Auto-Restart  : 3 attempts every 5 minutes on unexpected failure" -ForegroundColor Gray
    Write-Host "======================================================================" -ForegroundColor Green

    if ($StartNow) {
        Start-ScheduledTask -TaskName $TaskName
        Write-Host "[OK] Task '$TaskName' started immediately." -ForegroundColor Cyan
    } else {
        Write-Host "To start immediately, run: Start-ScheduledTask -TaskName '$TaskName'" -ForegroundColor Yellow
        Write-Host "Or run with -StartNow parameter next time." -ForegroundColor Yellow
    }
} catch {
    Write-Error "Failed to register scheduled task: $_"
    exit 1
}
