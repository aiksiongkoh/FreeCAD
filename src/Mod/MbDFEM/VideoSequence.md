# MbDFEM video sequences

Select a solved **MbDAssembly** or **FEMAssembly**, close any active task panel,
and choose **MbDFEM → Video Sequence…**. Use an FEMAssembly for shots containing
stress contours. The command creates a **VideoSequence** object under the
assembly and opens its editor in the **Tasks** tab, like AnimationParameters.
Double-click VideoSequence to reopen it. The 3D view remains available for
rotating, panning and zooming, and you can still select objects and change visibility.

Each shot captures a fixed camera, object visibility, transparency, colors,
display modes, contour/legend switches and free-body/CLOAD/DLOAD arrow visibility
and scales. First/last state and screen duration determine the playback speed.
Output FPS determines the number of PNGs, independently of viewport performance.
Choose **Update shot** to capture changed settings for the selected shot.
**Preview** applies a saved shot's camera/display and first simulation state.

## Three-shot example

1. **Mechanism motion**: hide FEM results and arrows, fit the mechanism in an
   axonometric view, select Motion, choose the solved state interval and a
   5-second duration, then **Capture new**. Start at state 1 for models whose
   state 0 represents the ground/input state.
2. **Joint reactions**: zoom into the joint, make surrounding bodies transparent,
   enable FreeBodyDiagram for the relevant MbD body, and capture a second Motion
   shot. Use a longer screen duration to slow the same simulation interval.
3. **Peak stress**: display FEM contours and legends, choose FEM results, select
   the bodies and stress field, set first and last to the same manually selected
   critical state, and capture a 3-second shot. Equal endpoints produce a pause.

Use **Up/Down** to arrange shots. **Save sequence** stores captured shots in the
VideoSequence object. The task panel's **Close** button also saves captured shots
and export settings. Use **Update shot** to record edits to a selected shot before
closing. Resolution and FPS are also available as VideoSequence properties.
Save the FCStd document to retain settings between sessions. Existing sequences
are reused and attached to their assembly when opened; no shots need recapturing.

## Export

### MP4 video

Choose **Export video…**, enter a video name such as `MechanismMotion`, and
MbDFEM renders and encodes the sequence using PyAV (the same FFmpeg binding used
by FreeCAD's Assembly workbench). PyAV and Pillow must be installed in FreeCAD's
Python runtime. Width and height must be even. MP4 uses H.264 when available,
with MPEG-4 as the fallback.

Exports use the document's existing MbDFEM case directory:

```text
Case001/
└── Videos/
    └── MechanismMotion/
        ├── MechanismMotion.mp4
        ├── manifest.json
        └── Frames/
            ├── frame_000000.png
            └── …
```

For a saved document, Case001 is under `<document without .FCStd>/MbDFEM/`.
Unsaved documents use the backend's temporary case directory; save the document
before exporting for a permanent project location. The completion message shows
the actual export directory. Video names use letters, digits, underscores and
hyphens. Repeated names create new directories such as `MechanismMotion_002`.

Frames are removed after successful encoding unless **Keep frames after video
export** is checked. Cancellation or failure preserves completed frames for
recovery and removes the partial MP4. The root manifest records the sequence,
frame paths relative to the export directory, export/video status, output movie
filename and whether frames were retained. When frames are removed, their records
remain in the manifest to trace video frames back to simulation states.

### PNG sequence

Set resolution and FPS, then choose **Export PNGs…** and an empty directory.
The exporter writes `frame_000000.png`, `frame_000001.png`, etc., and a
`manifest.json` with the settings and actual simulation state/time of each frame.
Existing files are never overwritten. Cancellation keeps completed frames and
marks the manifest as cancelled. Failures retain a failed manifest.

Motion shots interpolate motion in simulation time. FEM shots hold the nearest
common saved result state (ties use the earlier state), with a shared fixed
color range across selected bodies and the shot interval. Both endpoints must
have results for every selected body. Missing intermediate states are held;
stress is never interpolated. Generate denser FEM results for smoother playback.
Motion shots hide FEM result geometry to avoid displaying stale contours.

The frame count is the screen duration multiplied by FPS, rounded up. Both
simulation endpoints are included when there is more than one output frame.
The exporter restores document properties, camera, FEM datasets and arrow
visibility after completion, cancellation or failure. Captions are composed
directly onto each exported image so they do not depend on a live overlay timer.

The first version uses cuts between fixed cameras. Camera tracking, transitions,
plots, automatic peak-state selection and split-screen comparison are future
extensions. Numbered PNGs can also be imported into a video editor
at the chosen output FPS.
