param([Parameter(Mandatory=$true)][string]$ZoteroExecutable)
$ErrorActionPreference='Stop'
$root=Split-Path -Parent $PSScriptRoot
$base=Join-Path $root 'runtime-verification'
if (!(Test-Path (Join-Path $base '.zvr-isolated-profile'))) {throw 'Prepare the isolated profile first.'}
$p=Start-Process -FilePath $ZoteroExecutable -ArgumentList @('-no-remote','-purgecaches','-profile',('"'+$base+'\profile"'),'-ZoteroDebugText') -PassThru -RedirectStandardOutput ($base+'\stdout.log') -RedirectStandardError ($base+'\stderr.log')
$p.Id | Set-Content ($base+'\process-id.txt')
Write-Output ('Isolated Zotero PID: '+$p.Id)
