# Windows Continuous Monitor Setup Guide

This guide details how to set up the **Job-AI Career Buddy Continuous 24-Hour Job Monitor** on Windows using PowerShell and Windows Task Scheduler for reliable, unattended background execution.

---

## 1. Overview & Operational Principles

The Job-AI monitor daemon (`app.jobs.monitor` / `app.jobs.scheduler`) runs continuously, executing a scan cycle every **60 minutes** (configurable) targeting fresh semiconductor jobs published within the last **24 hours**.

### Safety Invariants
- **Local-First**: Operates strictly on the local machine with local SQLite WAL persistence.
- **Strict Human Approval Gate**: All discovered opportunities and notification proposals remain in the `PROPOSED` state. The daemon **never** autonomously submits job applications, uploads resumes, or contacts recruiters.
- **Zero Hallucination / Freshness Integrity**: Never treats relative markers ("Today", "Active") as fresh $\le 24$h; only verified UTC timestamps are prioritized.
- **Process & Concurrency Protection**: Multi-process lock (`scanner_locks` table) prevents parallel scanning conflicts and corruption.

---

## 2. Quick Start: Manual PowerShell Launch

You can launch the monitor interactively or in the background using PowerShell:

```powershell
# From the repository root:
.\scripts\start_monitor.ps1
```

Or invoke the module directly with your virtual environment's Python:

```powershell
# Continuous monitoring (all regions, 24h freshness, 60-minute interval)
.\.venv\Scripts\python.exe -m app.jobs.monitor --region all --hours 24 --interval 60

# Single-shot verification scan
.\.venv\Scripts\python.exe -m app.jobs.monitor --once --region all --hours 24
```

To stop an interactive session, press `Ctrl + C` for graceful shutdown.

---

## 3. Automated Setup: Windows Task Scheduler

To ensure the monitor runs automatically at user login, restarts upon unexpected system reboots, and logs output without keeping a terminal window open:

### Method A: Automated PowerShell Task Registration

Open **PowerShell** (no Administrator rights required for `AtLogOn` task for current user):

```powershell
$ProjectDir = (Get-Location).Path
$VenvPython = Join-Path $ProjectDir ".venv\Scripts\python.exe"
$LogDir = Join-Path $ProjectDir "logs"

# Ensure logs directory exists
if (-not (Test-Path $LogDir)) { New-Item -ItemType Directory -Path $LogDir | Out-Null }

# Define Action
$Action = New-ScheduledTaskAction `
    -Execute $VenvPython `
    -Argument "-m app.jobs.monitor --region all --hours 24 --interval 60" `
    -WorkingDirectory $ProjectDir

# Define Trigger (Runs at User Logon)
$Trigger = New-ScheduledTaskTrigger -AtLogOn

# Define Settings (Restart on failure, allow on demand, do not start multiple instances)
$Settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -ExecutionTimeLimit (New-TimeSpan -Days 365) `
    -MultipleInstances IgnoreNew `
    -RestartCount 3 `
    -RestartInterval (New-TimeSpan -Minutes 5)

# Register the Scheduled Task
Register-ScheduledTask `
    -TaskName "JobAICareerMonitor" `
    -Action $Action `
    -Trigger $Trigger `
    -Settings $Settings `
    -Description "Job-AI Continuous 24-Hour Semiconductor Job Monitor Daemon"
```

---

### Method B: Manual GUI Setup via Task Scheduler (`taskschd.msc`)

1. Press `Win + R`, type `taskschd.msc`, and press Enter.
2. Click **Create Task...** in the right-hand panel.
3. **General Tab**:
   - **Name**: `JobAICareerMonitor`
   - **Description**: `Job-AI Continuous 24-Hour Semiconductor Job Monitor Daemon`
   - Select **Run only when user is logged on**.
4. **Triggers Tab**:
   - Click **New...** $\rightarrow$ Begin the task: **At log on** $\rightarrow$ Specific user $\rightarrow$ Click **OK**.
5. **Actions Tab**:
   - Click **New...** $\rightarrow$ Action: **Start a program**.
   - **Program/script**: `C:\path\to\job-ai\.venv\Scripts\python.exe` (or `powershell.exe`)
   - **Add arguments**: `-m app.jobs.monitor --region all --hours 24 --interval 60`
   - **Start in**: `C:\path\to\job-ai` (absolute workspace root)
6. **Conditions Tab**:
   - Uncheck **Stop if the computer switches to battery power**.
7. **Settings Tab**:
   - Check **Allow task to be run on demand**.
   - Check **If the task fails, restart every**: `5 minutes`, attempt up to `3 times`.
   - If the task is already running, then the following rule applies: **Do not start a new instance**.
8. Click **OK** to save the task.

---

## 4. Monitoring State & Health Verification

The monitor persists status on every cycle to the SQLite `monitor_state` table:

```powershell
# Query current monitor daemon status via CLI
python -c "from app.db.connection import get_connection; from app.db.repository import JobRepository; repo = JobRepository(get_connection()); print(repo.get_scheduler_status())"
```

### Dashboard View
Launch the Streamlit dashboard to inspect live health:
```powershell
streamlit run app/dashboard.py
```
Navigate to **Tab 6: Monitor Daemon** to see:
- 🟢 `MONITOR ACTIVE` or 🔴 `MONITOR STOPPED`
- Last scan timestamp & next scheduled cycle
- Discovered fresh $\le 24$h jobs, India vs Overseas distribution
- Pending human notification proposals
- One-click Start / Stop / Run Once controls

---

## 5. Stopping or Removing the Task

To stop or remove the scheduled task:

```powershell
# Stop currently running task
Stop-ScheduledTask -TaskName "JobAICareerMonitor"

# Disable task temporarily
Disable-ScheduledTask -TaskName "JobAICareerMonitor"

# Remove task completely
Unregister-ScheduledTask -TaskName "JobAICareerMonitor" -Confirm:$false
```
