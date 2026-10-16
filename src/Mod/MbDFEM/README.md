# MbDFEM development workspace on Windows 11

For saved camera shots, PNG image sequences and MP4 export, see
[MbDFEM video sequences](VideoSequence.md).

This guide creates a Windows 11 development workspace for the built-in FreeCAD
`MbDFEM` module. It reproduces the layout used by this checkout:

```text
C:\Users\<WindowsUser>\Documents\FreeCAD\Development\
├── FreeCAD\
│   ├── build\
│   │   └── debug\
│   └── src\Mod\MbDFEM\
└── FreeCAD-LibPack\
    └── LibPack-26.3.0-v3.5.5-x64-Debug\
```

The source directory is a fork of
[FreeCAD/FreeCAD](https://github.com/FreeCAD/FreeCAD). The build directory follows
FreeCAD's checked-in `debug` CMake preset. The LibPack remains outside the source
checkout.

FreeCAD `main` and the LibPack evolve together. The versions above reproduce this
checkout. For a later FreeCAD revision, check the current
[FreeCAD Developers Handbook](https://freecad.github.io/DevelopersHandbook/) and
[FreeCAD-LibPack releases](https://github.com/FreeCAD/FreeCAD-LibPack/releases)
before selecting tool and LibPack versions.

## 1. Install the development tools

Open Windows PowerShell as a normal user. Install Git, GitHub CLI, Visual Studio
Code, CMake, and 7-Zip:

```powershell
winget install --id Git.Git --exact
winget install --id GitHub.cli --exact
winget install --id Microsoft.VisualStudioCode --exact
winget install --id Kitware.CMake --exact
winget install --id 7zip.7zip --exact
```

Install the current Visual Studio Community release that provides the MSVC v145
x64 toolchain. On the machine used for this guide that is Visual Studio 2026
Community. Use Visual Studio Installer to select:

- **Desktop development with C++**
- MSVC v145 x64/x86 build tools
- Windows 11 SDK
- C++ CMake tools for Windows

Restart PowerShell after installation and verify the command-line tools:

```powershell
git --version
gh --version
cmake --version
code --version
```

Install these VS Code extensions:

```powershell
code --install-extension ms-vscode.cpptools
code --install-extension ms-vscode.cmake-tools
```

## 2. Fork FreeCAD

Authenticate GitHub CLI:

```powershell
gh auth login
```

Choose `GitHub.com`, HTTPS, and browser authentication when prompted. Create a
fork under the authenticated GitHub account:

```powershell
gh repo fork FreeCAD/FreeCAD --clone=false
```

GitHub describes a fork as a repository connected to its upstream repository;
see [Fork a repository](https://docs.github.com/en/pull-requests/collaborating-with-pull-requests/working-with-forks/fork-a-repo).

## 3. Create the directory layout and clone the fork

Set workspace variables. These values exist only in the current PowerShell
process at this stage:

```powershell
$Root = Join-Path $HOME "Documents\FreeCAD\Development"
$Source = Join-Path $Root "FreeCAD"
$LibPackRoot = Join-Path $Root "FreeCAD-LibPack"
$Build = Join-Path $Source "build\debug"

New-Item -ItemType Directory -Force -Path $Root, $LibPackRoot | Out-Null
```

Obtain the GitHub login name and clone the fork:

```powershell
$GitHubUser = gh api user --jq .login
git clone "https://github.com/$GitHubUser/FreeCAD.git" $Source
Set-Location $Source
```

Keep the fork as `origin` and register the official repository as `upstream`:

```powershell
git remote add upstream https://github.com/FreeCAD/FreeCAD.git
git remote -v
```

The expected remotes are:

```text
origin    https://github.com/<GitHubUser>/FreeCAD.git
upstream  https://github.com/FreeCAD/FreeCAD.git
```

Fetch branches and check out the branch containing MbDFEM. Replace
`<mbdfem-branch>` with the branch pushed from this development checkout:

```powershell
git fetch --all --prune
git switch --track "origin/<mbdfem-branch>"
```

Upstream FreeCAD does not contain MbDFEM until the module is accepted there, so
checking out the MbDFEM branch is required to reproduce this workspace.

## 4. Install the FreeCAD LibPack

The FreeCAD Developers Handbook recommends the prebuilt LibPack as the easiest
way to supply Windows dependencies. Download this checkout's compatible Debug
archive from the
[FreeCAD-LibPack releases page](https://github.com/FreeCAD/FreeCAD-LibPack/releases):

```text
LibPack-26.3.0-v3.5.5-x64-Debug
```

Place the downloaded archive in `$LibPackRoot`, then extract it with 7-Zip. If
the archive is a `.7z` file:

```powershell
$Archive = Get-ChildItem $LibPackRoot -Filter "LibPack-26.3.0-v3.5.5-x64-Debug*.7z" |
    Select-Object -First 1

if (-not $Archive) {
    throw "The expected LibPack archive was not found in $LibPackRoot"
}

& "${env:ProgramFiles}\7-Zip\7z.exe" x $Archive.FullName "-o$LibPackRoot"
```

Locate and validate the extracted directory:

```powershell
$LibPack = Join-Path $LibPackRoot "LibPack-26.3.0-v3.5.5-x64-Debug"

if (-not (Test-Path (Join-Path $LibPack "bin"))) {
    throw "Invalid LibPack directory: $LibPack"
}
```

Do not place the LibPack inside the `FreeCAD` Git checkout.

## 5. Configure the Windows Debug build

Use the checked-in `windows-debug` preset and setup script described in
[the Windows setup guide](../../../docs/Setup.md#6-configure-and-build-windows-debug).
All Windows debugger configurations use `build/debug`. From ordinary PowerShell:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File tools/build-windows-debug.ps1 `
    -LibPack "C:\path\to\LibPack-26.3.0-v3.5.5-x64-Debug"
```

The script initializes x64 MSVC, configures, and builds FreeCAD with MbDFEM.
Later invocations can omit `-LibPack`, using the path saved in the CMake cache.
A new checkout does not need a local preset or edits to shared dependency paths.

For the manual commands below, set `$Build = Join-Path $Source 'build/debug'`.

## 6. Use the checked-in VS Code configuration

The repository supplies `.vscode/settings.json`, `tasks.json`, `launch.json`,
and `c_cpp_properties.json`. Open the checkout in VS Code and use **Debug MbDFEM**
or **Full Debug FreeCAD** to build C++ and refresh scripts before launch.
**Fast Debug FreeCAD** refreshes scripts and caches only after the initial build.
The default build task (`Ctrl+Shift+B`) builds all targets in `build/debug`.

## 7. Start VS Code with the x64 compiler environment

The checked-in build and debugger tasks initialize MSVC themselves. For direct
use of the CMake Tools extension, close all VS Code windows and open **Developer
PowerShell for VS 2026**, initialize x64 tools, and set the dependency path before
starting VS Code:

```powershell
Enter-VsDevShell -VsInstallPath $env:VSINSTALLDIR -SkipAutomaticLocation -DevCmdArguments '-arch=x64 -host_arch=x64'
$env:FREECAD_LIBPACK_DIR = $LibPack
code $Source
```

Use x64 tools. A missing compiler
environment causes errors such as missing `array` or `io.h`; an x86 environment
can cause unresolved Debug runtime symbols during linking.

## 8. Configure FreeCAD

In VS Code, press `Ctrl+Shift+P` and run **CMake: Configure**. Select
`windows-debug` if prompted.

The equivalent command, run from an x64 Visual Studio developer environment,
is:

```powershell
Set-Location $Source
cmake --preset windows-debug
```

If a failed earlier configure cached a missing compiler, refresh only the build
configuration:

```powershell
cmake --fresh --preset windows-debug
```

Successful output ends with:

```text
Configuring done
Generating done
Build files have been written to: ...\FreeCAD\build\debug
```

Verify important cache values:

```powershell
Select-String -Path "$Build\CMakeCache.txt" -Pattern @(
    '^BUILD_MBDFEM:BOOL=ON',
    '^CMAKE_BUILD_TYPE:STRING=Debug',
    '^FREECAD_LIBPACK_USE:BOOL=ON'
)
```

## 9. Build FreeCAD and MbDFEM

In VS Code:

1. Press `Ctrl+Shift+P` and run **CMake: Set Build Target**.
2. Select `all`.
3. Click **Build** on the status bar, or run **CMake: Build**.

The PowerShell equivalent is:

```powershell
cmake --build $Build
```

A first Debug build compiles several thousand targets. Ninja builds
incrementally, so rerunning the command continues from completed outputs.

Verify the principal artifacts:

```powershell
Get-Item @(
    "$Build\bin\FreeCAD_d.exe",
    "$Build\bin\FreeCADCmd_d.exe",
    "$Build\Mod\MbDFEM\MbDFEM_d.pyd",
    "$Build\Mod\MbDFEM\Init.py",
    "$Build\Mod\MbDFEM\Examples\CreateMbDFEMModel.py"
)
```

## 10. Launch and test MbDFEM

Press `F5` in VS Code and select **Debug MbDFEM** if prompted. In FreeCAD,
select **View > Workbench > MbDFEM**, then enable **View > Panels > Python
console**.

Create the example model:

```python
from pathlib import Path
import MbDFEM

script = Path(MbDFEM.__file__).parent / "Examples" / "CreateMbDFEMModel.py"
exec(script.read_text(encoding="utf-8"))
```

The example creates these persistent relationships:

```text
MbDFEM_Doc
├── MbDAssembly1.assemblies -> [MbDAssembly2]
├── MbDAssembly1.fixedparts -> []
├── MbDAssembly1.parts -> [MbDPart1, MbDPart2]
├── MbDAssembly1.joints -> [MbDJoint1, MbDJoint2]
├── MbDAssembly1.motions -> [MbDMotion1, MbDMotion2]
├── MbDAssembly1.actions -> [MbDAction1, MbDAction2]
├── MbDPart1.markers -> [MbDMarker11, MbDMarker12]
├── MbDPart2.markers -> [MbDMarker21, MbDMarker22]
└── MbDJoint/MbDMotion/MbDAction.markerI, markerJ -> MbDMarker
```

The `assemblies`, `fixedparts`, `parts`, `joints`, `motions`, and `actions`
properties are the authoritative model relationships. MbDFEM also creates
lightweight App folder objects for tree presentation, so the GUI is displayed
as:

```text
MbDFEM_Doc
└── MbDAssembly1
    ├── Assemblies
    │   └── MbDAssembly2
    ├── FixedParts
    ├── Parts
    │   ├── MbDPart1
    │   │   └── Markers
    │   │       ├── MbDMarker11
    │   │       └── MbDMarker12
    │   └── MbDPart2
    │       └── Markers
    │           ├── MbDMarker21
    │           └── MbDMarker22
    ├── Joints
    │   ├── MbDJoint1
    │   │   ├── MbDMarker1
    │   │   └── MbDMarker11
    │   └── MbDJoint2
    │       ├── MbDMarker12
    │       └── MbDMarker21
    ├── Motions
    │   ├── MbDMotion1
    │   │   ├── MbDMarker1
    │   │   └── MbDMarker12
    │   └── MbDMotion2
    │       ├── MbDMarker2
    │       └── MbDMarker22
    └── Actions
        ├── MbDAction1
        │   ├── MbDMarker1
        │   └── MbDMarker21
        └── MbDAction2
            ├── MbDMarker2
            └── MbDMarker22
```

`MbDFEM::AnnuAnnuFacePair` validates its current face references during
recomputation. At least one face must be a complete planar annulus with
concentric circular boundaries. Both faces must be coplanar, and the selected
annulus must be completely contained in the other face, including its holes.
Coincident boundaries and opposite normals are allowed. When both faces are
annular, the smaller face by area is selected (side I breaks equal-area ties).

Call `MbDFEM.annuAnnuValidateGeometry(pair)` to validate immediately. It raises
`RuntimeError` on invalid geometry and returns `annulusSide`, `center`, `axis`,
`innerRadius`, and `outerRadius` on success. The center and outer-circle axis
are in assembly coordinates. Optional linear and angular tolerances use model
length units and radians respectively; negative values select OpenCASCADE's
default tolerances. The containment Boolean uses the linear tolerance and
ignores residual area no larger than its square. Future annular load generation
must call the C++ `validateGeometry()` entry point before distributing loads.

Joint load generation uses four role-specific C++ entry points and Python bindings:

| C++ method | Python binding | Requested part |
| --- | --- | --- |
| `CylCylFacePair::jointHoleLoad` | `MbDFEM.cylCylJointHoleLoad` | Hole part |
| `CylCylFacePair::jointPinLoad` | `MbDFEM.cylCylJointPinLoad` | Pin part |
| `AnnuAnnuFacePair::jointAnnulusLoad` | `MbDFEM.annuAnnuJointAnnulusLoad` | Selected annulus part |
| `AnnuAnnuFacePair::jointOtherAnnulusLoad` | `MbDFEM.annuAnnuJointOtherAnnulusLoad` | Opposing contact part |

All four take `(pair, joint, part, nodes, participatingPairs, lower=-1,
upper=-1, ratio=0)` in Python and reject a part with the wrong role. Face I/J
ordering does not determine the role or the joint reaction sign. When both
faces are annuli, the selected annulus remains the smaller by area, with I
breaking ties. `MbDFEM.annuAnnuValidateSampledGeometry(pair, lower=-1, upper=-1,
ratio=0)` returns the same geometry fields as current-geometry validation and
identifies this role at the requested sample. Export uses this selection to
dispatch to the two annular methods.

Pin loading uses the common hole origin and axis, transforms the sampled hole
face into the pin's mesh coordinates, and restricts loads to pin surface nodes
touching that bounded face. Pin overhangs are excluded. The cylindrical load
bases are shared: cosine-weighted transverse force, quadrant axial force,
transverse force couples for bending, and tangential force for axial torque.
Each component and the combined wrench must satisfy equilibrium. Export calls
the C++ hole/pin methods directly. Invalid geometry or an infeasible cylindrical or annular
mesh raises `RuntimeError` and stops load export rather than dropping a share.

Annular pairs distribute their share of the joint force and torque on both
parts. The role-specific methods sample the global marker-I reaction and placements,
checks the sampled contact geometry, and transfers the moment to the annulus
center. `nodes` is a list of `(nodeId, FreeCAD.Vector)` in the target part's mesh
coordinates. Participating cylindrical and annular pairs share the reaction
equally; repeated objects count once. The returned frames are common to both
sides, and the requested part determines the reaction sign.

The transverse and axial forces use four force quadrants; bending and axial
torques use four independently oriented torque quadrants. Nodes on the other
face are restricted to the selected annular band. Force and axial-torque
quadrant magnitudes are signed and constant per node, with tangential directions
varying by node for axial torque. Bending torque uses the profile
`Fz(node) = nodeX * ForceZquadrant` in each torque quadrant, where
`nodeX = (node.position - origin).dot(torqueXAxis)`. Thus nodes on the torque
frame's Y axis carry zero bending force. This profile applies to both the
selected annulus and the opposing contact face, with signed quadrant coefficients
solved to reproduce the requested torque and zero resultant force.
Empty quadrants are excluded from the solve. Every contribution
and the combined wrench are checked for equilibrium; infeasible meshes raise
`RuntimeError` and stop annular load export.

Both cylindrical and annular pairs have a saved `loadCost` property. Set it
to `"C"` to minimize the sum of squared region coefficients, or `"C2"` (the
default) to minimize the sum of squared nodal force magnitudes. Cylindrical
C2 weights include each node's actual force basis: cosine weights for
transverse force, unit axial force, axial-distance/cosine weights for bending,
and unit tangents for axial torque. The choice applies to all four components
on both hole and pin sides. Annular C2 also includes the squared `nodeX`
weights of the bending profile. These are magnitude objectives, not a
surface-traction model.
The force-frame fallback uses shifted torque crossed with the annulus axis,
then the longer projected X/Y mesh axis of the annulus part (X wins ties).
The torque-frame fallback uses the same mesh-axis rule.

For a supplied wrench rather than sampled joint histories, call
`MbDFEM.annuAnnuFaceLoad(pair, part, nodes, force, torque, markerOrigin)`.
The force, torque, and marker origin are in the target part's mesh coordinates;
the supplied torque is about `markerOrigin`. Both entry points return
`force_quadrants`, `torque_quadrants`, diagnostic `cload_components`, and combined
`cloads` with one record per node and DOF. Annular export uses the combined records;
cylindrical export preserves the separate component records.

Run the module's registered Python tests with the current FreeCAD Test API:

```python
import Test
import TestMbDFEMApp
import TestAnnuAnnuFacePair

Test.runTestsFromModule(TestMbDFEMApp)
Test.runTestsFromModule(TestAnnuAnnuFacePair)
```

Expected result:

```text
OK
```

The tests cover object creation, `TypeId`, placements, relationships, saving,
closing, reopening, and annular face-pair geometry validation.

### Animate FEM bodies together

Solve and import the FEM result states for each body, then select its
`FEMAssembly` in the MbDFEM workbench. Choose **MbDFEM > Animate FEM Results**
or the same command in the tree context menu's **MbDFEM** submenu.

Select the bodies to include, the result field, and the first/last states, then
press **Play**. One slider and timer advance all selected bodies together;
each body retains its own mesh and result pipeline. Only imported states
available for every selected body are played. The panel reports unavailable
states, and rejects results whose recorded times disagree with the linked
MbD assembly. Bodies without imported results cannot be selected.

**Shared color scale** gives the selected bodies the same fixed color range
across the playback interval. Uncheck it for independent body ranges. Existing
result visibility, contour, and legend settings are retained. Closing the
panel stops playback. This command displays existing FEM solutions; it does
not solve missing states or interpolate deformation between them.

The assembly's `animationParameters` link owns an
`MbDFEM::FEMAnimationParameters` object shown as **AnimationParameters** in the
tree. Body selection, current state, playback range, frame rate, result field,
shared color scale, and loop setting are saved with the document and restored
when the panel is reopened. Numeric edits are committed before file saving,
including while the panel remains open. Double-click **AnimationParameters**
to open its assembly's playback panel. Existing documents gain the settings
object when their FEM animation panel is first opened.

### Simulate several FEM parts together

Select an FEMAssembly (or one of its parts), then choose **MbDFEM → Simulate FEM Assembly**.
Select the parts and a shared First/Last State range from the linked MbD simulation.
**Write Inputs** exports the range without running CalculiX; **Solve Current State**
solves the current state for each selected part; **Solve Range** processes every
selected part at each state; **Import Results** imports the range from existing FRD files.
Each part retains its own mesh, material, solver, constraints, and per-state directory.

CalculiX runs sequentially in an asynchronous process. The panel shows overall
progress, completed jobs per part, failed states, and the current job. **Stop after
current job** retains completed results and leaves the remaining jobs pending.
Closing the panel during a run requests the same stop; close it once the current
job finishes. Closing the document terminates its active solver process.
Solver output is saved to the state's calculix.log file. A failed solve retains
previously imported results and cannot import an unchanged old FRD file.

**Only missing or stale imported results** skips states with an imported result,
matching simulation time, and no existing ASMT file freshness warning. This check
is not a fingerprint of all analysis inputs: clear it to replace results after
changing a mesh, material, constraint, load, or other input. **Continue after a
failed job** allows other parts and states to finish; clear it to stop on the first
failure. To resume a partial batch, run the same range with the missing-results
option enabled. Review the failed states and their logs before retrying.

Selections, state controls, and batch options are saved in an
MbDFEM::FEMSimulationParameters object owned by FEMAssembly.femParameters.
Both **SimulationParameters** and **AnimationParameters** appear under FEMAssembly
as soon as it is created. Older files receive missing parameter objects when reopened.
Double-click **SimulationParameters** to reopen the panel. Saving while it is open
commits pending state edits; reopening never starts jobs automatically.
These are separate part analyses sampled from one MbD timeline, rather than a
combined CalculiX model with deformation-dependent contact between parts.
After solving, use **Animate FEM Results** to play the common imported states together.

## 11. Keep the fork synchronized

Before starting new work, update the local view of upstream:

```powershell
Set-Location $Source
git fetch upstream --prune
```

Rebase a feature branch onto current upstream `main` only when the working tree
is clean:

```powershell
git switch <mbdfem-branch>
git rebase upstream/main
```

Push the branch to the fork:

```powershell
git push --force-with-lease origin <mbdfem-branch>
```

Use `--force-with-lease` after a rebase; do not use an unrestricted force push.

## 12. Source-controlled and generated files

The MbDFEM source, tests, example, and this document belong under Git source
control:

```text
src/Mod/MbDFEM/
```

The portable VS Code settings, debugger configurations, build tasks, and
`tools/build-windows-debug.ps1` also belong under source control. The following
are local or generated and are intentionally ignored:

```text
CMakeUserPresets.json
build/
```

Do not edit generated copies under `build/debug/Mod/MbDFEM`. Edit the
authoritative files under `src/Mod/MbDFEM`, rebuild, and test.

Before committing, review only the intended files:

```powershell
git status --short
git diff --check
git diff
```

Stage the MbDFEM module and its three FreeCAD registration changes:

```powershell
git add src/Mod/MbDFEM
git add src/Mod/CMakeLists.txt
git add cMake/FreeCAD_Helpers/InitializeFreeCADBuildOptions.cmake
git add cMake/FreeCAD_Helpers/PrintFinalReport.cmake
```

Commit after the build and tests pass:

```powershell
git commit -m "MbDFEM: Add initial built-in module"
git push -u origin HEAD
```

Do not add unrelated files such as local logs or manually generated `.FCStd`
documents.
