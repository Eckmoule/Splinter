<#
Crée (ou met à jour) la tâche Windows qui lance la synchro Splinter chaque soir.

- réveille le PC s'il est en veille (si les minuteurs de réveil sont autorisés)
- rattrape la synchro au prochain démarrage / ouverture de session si le PC était éteint
- tourne dans la session de l'utilisateur, sans fenêtre ; journal dans Data\logs\sync.log

Usage :  powershell -ExecutionPolicy Bypass -File scripts\planifier_synchro.ps1 [-Heure 22:00]
Suppression :  Unregister-ScheduledTask -TaskName "Splinter - synchro Garmin"
#>
param(
    [string]$Heure = "22:00"
)

$ErrorActionPreference = "Stop"
$repo = Split-Path -Parent $PSScriptRoot
$pythonw = Join-Path $repo ".venv\Scripts\pythonw.exe"
if (-not (Test-Path $pythonw)) { throw "Environnement Python introuvable : $pythonw" }

$taskName = "Splinter - synchro Garmin"
$action = New-ScheduledTaskAction -Execute $pythonw -Argument "-m splinter.nightly" -WorkingDirectory $repo
$trigger = New-ScheduledTaskTrigger -Daily -At $Heure
$settings = New-ScheduledTaskSettingsSet -WakeToRun -StartWhenAvailable `
    -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
    -ExecutionTimeLimit (New-TimeSpan -Hours 1) -MultipleInstances IgnoreNew
$principal = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" -LogonType Interactive -RunLevel Limited

Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Settings $settings `
    -Principal $principal -Description "Synchronise Garmin Connect et régénère l'export Splinter pour Claude." -Force | Out-Null

Get-ScheduledTask -TaskName $taskName | Get-ScheduledTaskInfo | Select-Object TaskName, NextRunTime
