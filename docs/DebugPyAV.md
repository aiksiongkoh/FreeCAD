# Assembly video export with the Windows Debug LibPack

The LibPack 3.5.5 runtime uses CPython 3.14 Debug. The standard PyAV 18.1.0
Windows wheel installs release extensions, which this runtime does not load.

A local PyAV 18.1.0 Debug wheel has been built and installed into both:

- `build/debug/bin/Lib/site-packages`
- `LibPack-26.3.0-v3.5.5-x64-Debug/bin/Lib/site-packages`

The wheel is kept at:

`build/pyav-debug/dist/av-18.1.0-cp314-cp314d-win_amd64.whl`

From the repository root, reinstall into the build runtime with:

```powershell
& .\build\debug\bin\python.exe -m pip install --no-deps --force-reinstall --no-index `
  .\build\pyav-debug\dist\av-18.1.0-cp314-cp314d-win_amd64.whl
```

This wheel is specific to Windows x64 CPython 3.14 Debug. Do not replace it with
an ordinary `pip install --upgrade av` wheel. Restart FreeCAD after installation.
No FreeCAD C++ rebuild is required.

## Build provenance

- PyAV: official v18.1.0 tag, commit `7e3d950a8b72062502c1a60d672f8ca565313af5`.
- FFmpeg: official PyAV Windows x64 development bundle, release `8.1.2-1`.
- Compiler: local Visual Studio MSVC, `setup.py build_ext --debug --inplace --parallel 4`.
- The wheel contains FFmpeg DLLs in `av/_ffmpeg` and adds that directory with
  `os.add_dll_directory` before importing PyAV extensions. No system PATH change
  is needed.

The reusable wheel and validation script are under `build/pyav-debug`.
Temporary source, downloads, and build logs were removed after validation.
That directory is build output; preserve the wheel elsewhere before deleting it.

## Validation

The installed package was tested using the current Assembly workbench's
`create_video` method from `src/Mod/Assembly/CommandCreateSimulation.py`.
MP4, AVI, and WebM each encoded 12 generated 64x64 RGB frames and decoded back
to 12 frames successfully. This verifies the encoder; it does not exercise
Assembly's interactive scene capture or save dialog.

```powershell
& .\build\debug\bin\python.exe .\build\pyav-debug\test-assembly-export.py --installed
```