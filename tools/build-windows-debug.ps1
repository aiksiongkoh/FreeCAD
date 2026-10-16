# SPDX-License-Identifier: LGPL-2.1-or-later
[CmdletBinding()]
param(
    [ValidateSet('Configure', 'Build', 'Scripts')]
    [string]$Action = 'Build',
    [ValidateSet('Debug', 'Release')]
    [string]$Configuration = 'Debug',
    [string]$LibPack = $env:FREECAD_LIBPACK_DIR,
    [ValidateRange(1, 128)]
    [int]$Jobs = 4
)

$ErrorActionPreference = 'Stop'
$sourceDir = Split-Path -Parent $PSScriptRoot
$buildDir = Join-Path $sourceDir "build/$($Configuration.ToLowerInvariant())"
$cacheFile = Join-Path $buildDir 'CMakeCache.txt'
$configurePreset = if ($Configuration -eq 'Release') { 'windows-release' } else { 'windows-debug' }

# Windows cannot replace DLLs loaded by a running executable from this build.
# Script-only refreshes are safe while FreeCAD is running.
if ($Action -eq 'Build') {
    $buildBin = [System.IO.Path]::GetFullPath((Join-Path $buildDir 'bin'))
    $processNames = if ($Configuration -eq 'Release') { @('FreeCAD', 'FreeCADCmd') } else { @('FreeCAD_d', 'FreeCADCmd_d') }
    $running = @(Get-Process -Name $processNames -ErrorAction SilentlyContinue |
        Where-Object { -not $_.HasExited -and $_.Path -and (Split-Path -Parent $_.Path) -eq $buildBin })
    if ($running.Count -gt 0) {
        $processList = ($running | ForEach-Object { "$($_.ProcessName) (PID $($_.Id))" }) -join ', '
        throw "Close FreeCAD from this $Configuration build and stop its debug session before rebuilding. Running: $processList. Loaded DLLs cannot be overwritten."
    }
}

# Reuse the dependency path saved by the first configure, not another build tree.
if ($Configuration -eq 'Release' -and -not $PSBoundParameters.ContainsKey('LibPack') -and (Test-Path -LiteralPath $cacheFile)) {
    $LibPack = $null
}
if (-not $LibPack -and (Test-Path -LiteralPath $cacheFile)) {
    $entry = Select-String -LiteralPath $cacheFile -Pattern '^FREECAD_LIBPACK_DIR:PATH=(.+)$'
    if ($entry) { $LibPack = $entry.Matches[0].Groups[1].Value }
}
if (-not $LibPack -or -not (Test-Path -LiteralPath (Join-Path $LibPack 'bin'))) {
    throw "Supply -LibPack <extracted $Configuration LibPack directory> or set FREECAD_LIBPACK_DIR. See docs/Setup.md."
}
$env:FREECAD_LIBPACK_DIR = (Resolve-Path -LiteralPath $LibPack).Path

# Initialize x64 MSVC and the SDK even when launched by an ordinary VS Code task.
$vswhere = Join-Path ${env:ProgramFiles(x86)} 'Microsoft Visual Studio/Installer/vswhere.exe'
if (-not (Test-Path -LiteralPath $vswhere)) { throw 'Install Visual Studio with Desktop development with C++.' }
$vsInstall = & $vswhere -latest -products '*' -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 Microsoft.VisualStudio.Component.VC.CMake.Project -property installationPath
if (-not $vsInstall) {
    $vsInstall = & $vswhere -latest -products '*' -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath
}
if (-not $vsInstall) { throw 'Visual Studio x64 C++ tools were not found.' }
& (Join-Path $vsInstall 'Common7/Tools/Launch-VsDevShell.ps1') -VsInstallationPath $vsInstall -Arch amd64 -HostArch amd64 -SkipAutomaticLocation | Out-Host
if (-not (Get-Command ninja -ErrorAction SilentlyContinue)) {
    $ninjaDir = Join-Path $vsInstall 'Common7/IDE/CommonExtensions/Microsoft/CMake/Ninja'
    if (-not (Test-Path -LiteralPath (Join-Path $ninjaDir 'ninja.exe'))) {
        throw 'Install Ninja or the Visual Studio C++ CMake tools for Windows component.'
    }
    $env:PATH = "$ninjaDir;$env:PATH"
}
if (-not (Get-Command cmake -ErrorAction SilentlyContinue)) {
    $env:PATH = "$(Join-Path $vsInstall 'Common7/IDE/CommonExtensions/Microsoft/CMake/CMake/bin');$env:PATH"
}

Push-Location $sourceDir
try {
    if ($Action -eq 'Configure' -or -not (Test-Path -LiteralPath $cacheFile)) {
        & cmake --preset $configurePreset "-DFREECAD_LIBPACK_DIR=$env:FREECAD_LIBPACK_DIR"
        if ($LASTEXITCODE -ne 0) { throw "CMake configure failed ($LASTEXITCODE)." }
    }
    if ($Action -ne 'Configure') {
        $buildArgs = @('--build', $buildDir, '--parallel', $Jobs)
        if ($Action -eq 'Scripts') { $buildArgs += @('--target', 'MbDFEMScripts') }
        & cmake @buildArgs
        if ($LASTEXITCODE -ne 0) { throw "CMake build failed ($LASTEXITCODE)." }
    }
}
finally { Pop-Location }
