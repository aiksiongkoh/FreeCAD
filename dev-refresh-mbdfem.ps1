param(
    [switch]$BuildCpp,
    [switch]$SkipRecoveryCleanup
)

$ErrorActionPreference = "Stop"

$root = $PSScriptRoot
Set-Location -LiteralPath $root

function Invoke-CheckedNativeCommand {
    param(
        [Parameter(Mandatory = $true)]
        [string]$FilePath,
        [Parameter(ValueFromRemainingArguments = $true)]
        [string[]]$Arguments
    )

    & $FilePath @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "$FilePath exited with code $LASTEXITCODE."
    }
}

if ($BuildCpp) {
    Invoke-CheckedNativeCommand cmake --build build\debug --target MbDFEM MbDFEMGui
}

Invoke-CheckedNativeCommand cmake --build build\debug --target MbDFEMScripts

$cachePaths = @(
    (Join-Path $root "src\Mod\MbDFEM\__pycache__"),
    (Join-Path $root "build\debug\Mod\MbDFEM\__pycache__"),
    "C:\Users\askoh\AppData\Roaming\FreeCAD\v26-3\Mod\AutoLoadMbDFEM\__pycache__"
)

foreach ($path in $cachePaths) {
    Remove-Item -LiteralPath $path -Recurse -Force -ErrorAction SilentlyContinue
}

if (-not $SkipRecoveryCleanup) {
    $freecadUserCache = Join-Path $env:LOCALAPPDATA "cache\FreeCAD\v26-3\Cache"
    if (Test-Path -LiteralPath $freecadUserCache) {
        Get-ChildItem -LiteralPath $freecadUserCache -Force -ErrorAction SilentlyContinue |
            Where-Object {
                $_.Name -like "FreeCAD_Doc_*" -or $_.Name -like "FreeCAD_*.lock"
            } |
            ForEach-Object {
                Remove-Item -LiteralPath $_.FullName -Recurse -Force -ErrorAction SilentlyContinue
            }
    }

    $freecadUserConfig = Join-Path $env:APPDATA "FreeCAD\v26-3\user.cfg"
    if (Test-Path -LiteralPath $freecadUserConfig) {
        $configInfo = Get-Item -LiteralPath $freecadUserConfig
        if ($configInfo.Length -lt 32MB) {
            $configText = Get-Content -LiteralPath $freecadUserConfig -Raw
            if ($configText -match '(<FCBool\b[^>]*Name="RecoveryEnabled"[^>]*Value=")[01](")') {
                $configText = $configText -replace '(<FCBool\b[^>]*Name="RecoveryEnabled"[^>]*Value=")[01](")', '${1}0${2}'
                Set-Content -LiteralPath $freecadUserConfig -Value $configText -Encoding UTF8
            }
        } else {
            Write-Warning "Skipping RecoveryEnabled update because $freecadUserConfig is unusually large ($($configInfo.Length) bytes)."
        }
    }
}
