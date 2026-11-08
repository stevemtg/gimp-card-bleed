param(
    [string]$GimpExe = (Join-Path $env:LOCALAPPDATA 'Programs\GIMP 3\bin\gimp-console-3.0.exe')
)
$ErrorActionPreference = 'Stop'
$taskRoot = Split-Path -Parent $PSScriptRoot
$taskProfile = Join-Path $taskRoot '.test-profile'
$taskResult = Join-Path $taskRoot 'test-results.json'
if (-not (Test-Path -LiteralPath $GimpExe)) { throw "GIMP not found: $GimpExe" }
New-Item -ItemType Directory -Path $taskProfile -Force | Out-Null
$taskPluginPath = (Join-Path $taskRoot 'plug-ins').Replace('\', '/')
$taskConfig = '(plug-in-path "' + $taskPluginPath + ';${gimp_plug_in_dir}/plug-ins")'
[System.IO.File]::WriteAllText((Join-Path $taskProfile 'gimprc'), $taskConfig)
if (Test-Path -LiteralPath $taskResult) { Remove-Item -LiteralPath $taskResult }
$taskOldProfile = $env:GIMP3_DIRECTORY
$taskOldTemp = $env:TEMP
$taskOldTmp = $env:TMP
try {
    $env:GIMP3_DIRECTORY = $taskProfile
    $env:TEMP = $taskProfile
    $env:TMP = $taskProfile
    Push-Location -LiteralPath $taskRoot
    try {
        & $GimpExe --new-instance --no-interface --no-data --no-fonts --no-splash --console-messages --batch-interpreter=python-fu-eval --batch "exec(open('tests/integration.py', encoding='utf-8').read())" --batch "exec(open('tests/check-dialog.py', encoding='utf-8').read())" --quit
        $taskExitCode = $LASTEXITCODE
        if ($taskExitCode -ne 0) { throw "GIMP exited with code $taskExitCode" }
    } finally { Pop-Location }
    if (-not (Test-Path -LiteralPath $taskResult)) { throw 'GIMP did not produce a test report.' }
    $taskReport = Get-Content -LiteralPath $taskResult -Raw | ConvertFrom-Json
    if (-not $taskReport.passed) { throw $taskReport.error }
    Write-Output "Passed $($taskReport.cases.Count) integration cases in GIMP $($taskReport.gimp_version)."
} finally {
    $env:GIMP3_DIRECTORY = $taskOldProfile
    $env:TEMP = $taskOldTemp
    $env:TMP = $taskOldTmp
}
