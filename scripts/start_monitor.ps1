<#
.SYNOPSIS
    Starts the Job-AI Continuous 24-Hour Job Monitor on Windows.
.DESCRIPTION
    Locates the active Python virtual environment (.venv) or system Python,
    verifies no conflicting monitor instance is running, and starts the
    continuous background scanner daemon.
.PARAMETER Region
    Geographic focus: 'all' (default), 'india', or 'overseas'.
.PARAMETER Interval
    Scan interval in minutes (default: 60).
.PARAMETER Hours
    Freshness window in hours (default: 24.0).
.PARAMETER Once
    Run a single scan cycle and exit.
.PARAMETER Background
    Launch as detached background process logging to logs/monitor.log.
#>

param(
    [ValidateSet("all", "india", "overseas")]
    [string]$Region = "all",
    [int]$Interval = 60,
    [double]$Hours = 24.0,
    [switch]$Once,
    [switch]$Background
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
        Write-Error "Could not locate python.exe in .venv or system PATH. Please create a virtual environment first."
        exit 1
    }
}

# 2. Check for Existing Running Daemon PID from SQLite
try {
    $CheckCode = "from app.db.connection import get_connection; from app.db.repository import JobRepository; repo = JobRepository(get_connection()); s = repo.get_scheduler_status(); print(s.get('is_running', False), s.get('daemon_pid', ''))"
    $StatusOutput = & $PythonExe -c $CheckCode 2>$null
    if ($StatusOutput) {
        $Parts = $StatusOutput.Trim().Split(" ")
        $IsRunning = $Parts[0] -eq "True"
        $DaemonPid = if ($Parts.Length -gt 1) { $Parts[1] } else { "" }

        if ($IsRunning -and $DaemonPid -and (-not $Once)) {
            $Proc = Get-Process -Id $DaemonPid -ErrorAction SilentlyContinue
            if ($Proc) {
                Write-Warning "A Job-AI Monitor daemon is already active (PID: $DaemonPid). Aborting new instance to avoid conflicts."
                exit 0
            }
        }
    }
} catch {
    # Non-fatal DB inspection failure, proceed to launch with lock safety
}

# 3. Build Arguments
$Arguments = @("-m", "app.jobs.monitor", "--region", $Region, "--hours", $Hours)

if ($Once) {
    $Arguments += "--once"
} else {
    $Arguments += @("--interval", $Interval)
}

# 4. Execute Monitor
$LogsDir = Join-Path $ProjectRoot "logs"
if (-not (Test-Path $LogsDir)) {
    New-Item -ItemType Directory -Path $LogsDir | Out-Null
}

$LogFile = Join-Path $LogsDir "monitor.log"

if ($Background) {
    Write-Host "[INFO] Launching Job-AI Monitor in background..." -ForegroundColor Green
    Write-Host "[INFO] Logging stdout/stderr to: $LogFile" -ForegroundColor Gray
    
    $StartProcessArgs = @{
        FilePath = $PythonExe
        ArgumentList = $Arguments
        WorkingDirectory = $ProjectRoot
        RedirectStandardOutput = $LogFile
        RedirectStandardError = $LogFile
        WindowStyle = "Hidden"
        PassThru = $true
    }
    
    $Process = Start-Process @StartProcessArgs
    Write-Host "[OK] Monitor daemon launched with PID: $($Process.Id)" -ForegroundColor Green
} else {
    Write-Host "======================================================================" -ForegroundColor Cyan
    Write-Host "JOB-AI CAREER BUDDY  |  LAUNCHING CONTINUOUS MONITOR" -ForegroundColor Cyan
    Write-Host "Python : $PythonExe" -ForegroundColor Gray
    Write-Host "Region : $Region | Interval: ${Interval}m | Freshness: <=${Hours}h" -ForegroundColor Gray
    Write-Host "======================================================================" -ForegroundColor Cyan
    
    & $PythonExe $Arguments
}
