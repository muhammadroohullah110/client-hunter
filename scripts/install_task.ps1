# Registers the TDSOCH nightly run with Windows Task Scheduler (2:00 AM daily).
# Run once, in PowerShell, from the project folder:  .\scripts\install_task.ps1
# Remove later with:  Unregister-ScheduledTask -TaskName "TDSOCH Nightly" -Confirm:$false

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$bat  = Join-Path $root "run_all.bat"
if (-not (Test-Path $bat)) { throw "run_all.bat not found in $root" }

$action    = New-ScheduledTaskAction -Execute $bat -WorkingDirectory $root
$trigger   = New-ScheduledTaskTrigger -Daily -At 2:00AM
# Wake the machine if asleep, and still run if it was off at 2 AM (catch-up).
$settings  = New-ScheduledTaskSettingsSet -StartWhenAvailable -WakeToRun `
             -DontStopOnIdleEnd -ExecutionTimeLimit (New-TimeSpan -Hours 3)

Register-ScheduledTask -TaskName "TDSOCH Nightly" -Action $action -Trigger $trigger `
    -Settings $settings -Description "TDSOCH: nightly find -> audit -> score" -Force

Write-Host "Installed 'TDSOCH Nightly' (daily 2:00 AM). Logs: $root\logs\nightly.log"
Write-Host "Tip: on a laptop, keep it plugged in overnight for a clean run."
