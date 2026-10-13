# MbDFEM Windows Development Environment Setup

This guide recreates the current MbDFEM FreeCAD development environment on a
new Windows computer using Microsoft-centered tooling: Windows 11, Visual
Studio, VS Code, PowerShell, MSVC, and the VS Code C++ debugger.

Use non-Microsoft tools only where FreeCAD development requires them: Git,
CMake, the FreeCAD LibPack, and optionally 7-Zip for archive extraction.

## Target Workspace

The current development workspace is:

```text
C:\Users\askoh\Documents\GitHub\aiksiongkoh\FreeCAD\feature-mbdfem
```

On a new computer, use the same layout with your Windows user name:

```text
C:\Users\<WindowsUser>\Documents\GitHub\aiksiongkoh\FreeCAD\feature-mbdfem
```

The expected Debug LibPack location is:

```text
C:\Users\<WindowsUser>\Documents\GitHub\FreeCAD\FreeCAD-LibPack\LibPack-26.3.0-v3.5.5-x64-Debug
```

## 1. Install Required Software

Install these first:

- Visual Studio Community 2026 or the current Visual Studio version that
  provides the MSVC v145 x64 toolchain.
- Visual Studio workload: **Desktop development with C++**.
- Visual Studio component: **C++ CMake tools for Windows** (includes Ninja).
- Windows 11 SDK.
- Visual Studio Code.
- Git for Windows.
- CMake.
- 7-Zip, only if Windows cannot extract the LibPack archive.

Use Windows Package Manager where practical:

```powershell
winget install --id Microsoft.VisualStudioCode --exact
winget install --id Git.Git --exact
winget install --id Kitware.CMake --exact
winget install --id 7zip.7zip --exact
```

Install these VS Code extensions:

```powershell
code --install-extension ms-vscode.cpptools
code --install-extension ms-vscode.cmake-tools
```

Optional but useful:

```powershell
code --install-extension GitHub.vscode-github-actions
```

## 2. Clone the Fork and Select the Branch

Create the parent directory:

```powershell
New-Item -ItemType Directory -Force `
    -Path "$HOME\Documents\GitHub\aiksiongkoh\FreeCAD" | Out-Null
```

Clone the fork:

```powershell
git clone https://github.com/aiksiongkoh/FreeCAD.git `
    "$HOME\Documents\GitHub\aiksiongkoh\FreeCAD\feature-mbdfem"
```

Enter the checkout:

```powershell
Set-Location "$HOME\Documents\GitHub\aiksiongkoh\FreeCAD\feature-mbdfem"
```

Register the official FreeCAD repository as `upstream` if it is not already
present:

```powershell
git remote add upstream https://github.com/FreeCAD/FreeCAD.git
```

If Git says the remote already exists, that is fine. Verify remotes:

```powershell
git remote -v
```

Expected:

```text
origin    https://github.com/aiksiongkoh/FreeCAD.git
upstream  https://github.com/FreeCAD/FreeCAD.git
```

Fetch branches and check out the MbDFEM branch:

```powershell
git fetch --all --prune
git switch feature/mbdfem
```

If this is the first checkout and the local branch does not exist yet:

```powershell
git switch --track origin/feature/mbdfem
```

## 3. Initialize Submodules

FreeCAD uses Git submodules. Initialize them before configuring:

```powershell
git submodule update --init --recursive
```

Important submodules include:

```text
src/3rdParty/OndselSolver
src/3rdParty/GSL
src/3rdParty/coin
src/3rdParty/pivy
src/Mod/AddonManager
```

If configuration later reports that `OndselSolver` is not available, rerun the
submodule command.

## 4. Install the Debug LibPack

Download the Debug LibPack that matches this workspace:

```text
LibPack-26.3.0-v3.5.5-x64-Debug
```

Place and extract it under:

```text
C:\Users\<WindowsUser>\Documents\GitHub\FreeCAD\FreeCAD-LibPack
```

After extraction, verify:

```powershell
$LibPack = "$HOME\Documents\GitHub\FreeCAD\FreeCAD-LibPack\LibPack-26.3.0-v3.5.5-x64-Debug"

Test-Path "$LibPack\bin"
Test-Path "$LibPack\bin\python.exe"
Test-Path "$LibPack\bin\Include\Python.h"
Test-Path "$LibPack\bin\libs"
```

All checks should return `True`.

## 5. Open VS Code From the MSVC x64 Environment

Close existing VS Code windows.

Open **x64 Native Tools Command Prompt for VS 2026** from the Windows Start
menu. From that prompt, open the workspace:

```cmd
code "%USERPROFILE%\Documents\GitHub\aiksiongkoh\FreeCAD\feature-mbdfem"
```

This lets VS Code and CMake inherit the MSVC x64 compiler and Windows SDK
environment.

Verify the compiler in the VS Code terminal:

```powershell
where.exe cl
```

Expected path contains:

```text
Hostx64\x64\cl.exe
```

## 6. Configure and Build Windows Debug

The checked-in `windows-debug` preset inherits `debug` and always writes to
`build/debug`. It enables MbDFEM, uses Ninja and the x64 MSVC toolchain, and
copies the LibPack runtime dependencies into the build. No Windows user name
or machine-specific dependency path is stored in the shared preset.

After installing **Desktop development with C++**, **C++ CMake tools for
Windows**, the Windows SDK, and extracting the Debug LibPack, run this from the
checkout in ordinary PowerShell:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File tools/build-windows-debug.ps1 `
    -LibPack "C:\path\to\LibPack-26.3.0-v3.5.5-x64-Debug"
```

This initializes the Visual Studio x64 compiler environment, configures
`build/debug`, and builds all targets. `-LibPack` is required only for the first
configure; subsequent runs reuse the path saved in `build/debug/CMakeCache.txt`:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File tools/build-windows-debug.ps1
```

Use `-Action Configure` to configure only, `-Action Scripts` to refresh MbDFEM
Python scripts and clear their bytecode cache, and `-Jobs 2` to reduce build
parallelism on a smaller computer. To change LibPack, pass its new path together
with `-Action Configure`.

For direct CMake or CMake Tools usage, start VS Code from an x64 Visual Studio
developer environment with `FREECAD_LIBPACK_DIR` set:

```powershell
$env:FREECAD_LIBPACK_DIR = "C:\path\to\LibPack-26.3.0-v3.5.5-x64-Debug"
cmake --preset windows-debug
cmake --build --preset windows-debug
code .
```

The repository includes portable `.vscode` settings, launch configurations,
and tasks. No `CMakeUserPresets.json` is needed on a new computer. An optional
local preset may inherit `windows-debug` to override dependencies, but should
inherit its `build/debug` output directory too.

When switching from another build directory, configure and rebuild rather than
renaming the old directory: CMake caches and generated files contain absolute
paths. Keep the old build until the new build is verified.

## 7. Build

Use VS Code:

1. Press `Ctrl+Shift+P`.
2. Run **CMake: Set Build Target**.
3. Choose `all`, `FreeCADMain`, or `MbDFEM`.
4. Run **CMake: Build**.

Command-line examples:

```powershell
cmake --build build\debug --config Debug --target FreeCADMain
cmake --build build\debug --config Debug --target MbDFEM
cmake --build build\debug --config Debug --target FreeCADMainPy
```

The main GUI executable should be:

```text
build/debug/bin/FreeCAD_d.exe
```

The MbDFEM module output should be:

```text
build/debug/Mod/MbDFEM/MbDFEM_d.pyd
```

## 8. Debug From VS Code

The local `.vscode/launch.json` launches:

```text
build/debug/bin/FreeCAD_d.exe
```

with:

```text
cwd = build/debug/bin
debugger = cppvsdbg
```

Use **Run and Debug > Debug MbDFEM** or **Full Debug FreeCAD** and press `F5`.
Both run an incremental C++ build before launch. **Fast Debug FreeCAD** refreshes
only scripts and caches; build all targets once before using it.

`stopAtEntry` may be set to `true` while testing debugger startup. If enabled,
FreeCAD stops at `main()` first. Press Continue to reach later breakpoints.

## 9. Verify MbDFEM

Launch FreeCAD, then select:

```text
View > Workbench > MbDFEM
```

Open the Python console and run:

```python
import MbDFEM
```

To create the example document:

```python
from pathlib import Path
import MbDFEM

script = Path(MbDFEM.__file__).parent / "Examples" / "CreateMbDFEMModel.py"
exec(script.read_text(encoding="utf-8"))
```

To run MbDFEM tests from FreeCAD's Python console:

```python
import Test
import TestMbDFEMApp

Test.runTestsFromModule(TestMbDFEMApp)
```

### Windows Application Control troubleshooting

If a workbench or Python test reports `An Application Control policy has blocked
this file` while importing `PySide6.QtWidgets`, inspect the Windows
`Microsoft-Windows-CodeIntegrity/Operational` event log. On this development
computer, Smart App Control rejected the unsigned LibPack file
`bin/Lib/site-packages/PySide6/QtWidgets_d.cp314-win_amd64.pyd` even though the full
Debug build succeeded. Its SHA-256 matched the original LibPack file.

This is separate from the build directory and CMake configuration. A normal
PowerShell execution-policy override does not allow a blocked native extension.
Use a compatible runtime with an accepted signature, or review the computer's
Windows security configuration with its owner or administrator. The setup script
does not change Windows security policies. Microsoft's
[Smart App Control FAQ](https://support.microsoft.com/en-us/windows/security/threat-malware-protection/smart-app-control-frequently-asked-questions)
explains the signing requirements and lack of individual-app exceptions.

## 10. Keep the Shared Branch Updated

For this shared branch, prefer merging upstream `main` instead of rebasing:

```powershell
git fetch upstream main
git merge upstream/main
git submodule update --init --recursive
git push
```

This updates:

```text
origin/feature/mbdfem
```

It does not update:

```text
origin/main
```

## 11. Source Control Guidance

Source-controlled project files include:

```text
src/Mod/MbDFEM
docs
CMakePresets.json
src/Main/CMakeLists.txt
.vscode/launch.json
.vscode/tasks.json
.vscode/settings.json
.vscode/c_cpp_properties.json
tools/build-windows-debug.ps1
```

Local or generated files generally should not be committed:

```text
build
CMakeUserPresets.json
*.log
*.FCStd
```

Before committing:

```powershell
git status --short
git diff --check
git diff --stat
```
