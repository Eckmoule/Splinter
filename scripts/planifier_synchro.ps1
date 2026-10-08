<#
Crée (ou met à jour) la tâche Windows qui lance la synchro Splinter chaque soir.

Deux déclencheurs :
- chaque soir à l'heure choisie, en réveillant le PC s'il est en veille ;
- à chaque sortie de veille : quand le minuteur réveille le PC en retard, Windows considère le
  créneau comme manqué et ne rattrape la tâche qu'une dizaine de minutes plus tard, alors que le
  PC se rendort au bout de 2 min. Ce déclencheur démarre tout de suite.
La synchro est ignorée si la dernière réussie date de moins de -IntervalleMin heures, pour ne pas
resynchroniser à chaque réveil dans la journée. Elle est aussi rattrapée au prochain démarrage si
le PC était éteint. Sans fenêtre, dans la session de l'utilisateur ; journal dans Data\logs\sync.log.

Usage :  powershell -ExecutionPolicy Bypass -File scripts\planifier_synchro.ps1 [-Heure 22:00] [-IntervalleMin 6]
Suppression :  Unregister-ScheduledTask -TaskName "Splinter - synchro Garmin"
#>
param(
    [string]$Heure = "22:00",
    [double]$IntervalleMin = 6
)

$ErrorActionPreference = "Stop"
$repo = Split-Path -Parent $PSScriptRoot
$pythonw = Join-Path $repo ".venv\Scripts\pythonw.exe"
if (-not (Test-Path $pythonw)) { throw "Environnement Python introuvable : $pythonw" }

$taskName = "Splinter - synchro Garmin"
$arg = "-m splinter.nightly --if-older-than " + $IntervalleMin.ToString([Globalization.CultureInfo]::InvariantCulture)
$action = New-ScheduledTaskAction -Execute $pythonw -Argument $arg -WorkingDirectory $repo

$daily = New-ScheduledTaskTrigger -Daily -At $Heure

# sortie de veille : événement 1 de Power-Troubleshooter dans le journal Système
$eventClass = Get-CimClass -ClassName MSFT_TaskEventTrigger -Namespace Root/Microsoft/Windows/TaskScheduler
$wake = $eventClass | New-CimInstance -ClientOnly
$wake.Enabled = $true
$wake.Subscription = @"
<QueryList><Query Id="0" Path="System"><Select Path="System">*[System[Provider[@Name='Microsoft-Windows-Power-Troubleshooter'] and EventID=1]]</Select></Query></QueryList>
"@

$settings = New-ScheduledTaskSettingsSet -WakeToRun -StartWhenAvailable `
    -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
    -ExecutionTimeLimit (New-TimeSpan -Hours 1) -MultipleInstances IgnoreNew
$principal = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" -LogonType Interactive -RunLevel Limited

Register-ScheduledTask -TaskName $taskName -Action $action -Trigger @($daily, $wake) -Settings $settings `
    -Principal $principal -Description "Synchronise Garmin Connect et régénère l'export Splinter pour Claude." -Force | Out-Null

Get-ScheduledTask -TaskName $taskName | Get-ScheduledTaskInfo | Select-Object TaskName, NextRunTime
