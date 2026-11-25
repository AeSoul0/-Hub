# @file desktop/scripts/sign.ps1
# @description Authenticode signature of one file (M15, ADR-021). Tauri runs
# it as the bundle's signCommand for the app and for the installer.
#
# Needs AEHUB_SIGNING_PFX (a .pfx path) and WINDOWS_CERTIFICATE_PASSWORD in
# the environment: the password never appears in the Tauri configuration or
# on a command line that a log could print.

param([Parameter(Mandatory = $true)][string]$File)

$ErrorActionPreference = "Stop"

if (-not $env:AEHUB_SIGNING_PFX -or -not (Test-Path $env:AEHUB_SIGNING_PFX)) {
    throw "AEHUB_SIGNING_PFX does not point to the signing certificate."
}

$signtool = Get-ChildItem "${env:ProgramFiles(x86)}\Windows Kits\10\bin\*\x64\signtool.exe" |
    Sort-Object FullName |
    Select-Object -Last 1

if (-not $signtool) {
    throw "signtool.exe not found (Windows SDK)."
}

& $signtool.FullName sign `
    /f $env:AEHUB_SIGNING_PFX `
    /p $env:WINDOWS_CERTIFICATE_PASSWORD `
    /fd sha256 `
    /tr http://timestamp.digicert.com `
    /td sha256 `
    $File

if ($LASTEXITCODE -ne 0) {
    throw "signtool failed on $File"
}
