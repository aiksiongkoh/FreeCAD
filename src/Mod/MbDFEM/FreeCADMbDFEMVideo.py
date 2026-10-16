# SPDX-License-Identifier: LGPL-2.1-or-later

"""Saved shots, deterministic PNG sequences and MP4 export for MbDFEM.

FreeCAD imports are lazy so timeline validation can also run without the GUI.
FEM shots hold the nearest common saved state; they never interpolate stress.
"""

from bisect import bisect_left
import json
from math import ceil, isfinite
from pathlib import Path
import re


_VIEW_PROPERTIES = (
    "Visibility", "Transparency", "ShapeColor", "LineColor", "PointColor",
    "DisplayMode", "ShowColorContour", "ShowLegend", "ShowDLOADs", "ShowCLOADs",
    "FreeBodyDiagramAutoScale", "FreeBodyDiagramForceScale", "FreeBodyDiagramTorqueScale",
    "DLOADAutoScale", "DLOADScale", "CLOADAutoScale", "CLOADScale", "DLOADSampleSize",
)
_dialog = None


def frame_count(duration, fps):
    if not isfinite(duration) or duration <= 0 or not 1 <= fps <= 120:
        raise ValueError("Duration must be positive and output FPS must be between 1 and 120.")
    return max(1, ceil(duration * fps))


def sample_times(first, last, count):
    """Include both endpoints; a one-frame shot displays its first endpoint."""
    if count < 1 or not isfinite(first) or not isfinite(last) or last < first:
        raise ValueError("Invalid shot interval.")
    return [first + (last - first) * index / max(count - 1, 1) for index in range(count)]


def nearest_state(states, times, seconds):
    if not states:
        raise ValueError("No common FEM result states in the shot interval.")
    position = bisect_left([times[index] for index in states], seconds)
    candidates = states[max(0, position - 1):min(len(states), position + 1)]
    return min(candidates, key=lambda index: (abs(times[index] - seconds), index))


def validate_sequence(sequence, count):
    if sequence.get("version") != 1 or not sequence.get("shots"):
        raise ValueError("Capture at least one shot.")
    fps = sequence["fps"]
    if not isinstance(fps, int) or not 1 <= fps <= 120:
        raise ValueError("Output FPS must be an integer between 1 and 120.")
    for dimension in ("width", "height"):
        value = sequence[dimension]
        if not isinstance(value, int) or not 64 <= value <= 8192:
            raise ValueError("Image dimensions must be between 64 and 8192 pixels.")
    for shot in sequence["shots"]:
        first, last = shot["first"], shot["last"]
        if not isinstance(first, int) or not isinstance(last, int) or not 0 <= first <= last < count:
            raise ValueError(f"{shot['name']}: state interval is outside the motion results.")
        frame_count(shot["duration"], fps)
        if shot["mode"] not in ("motion", "fem") or not shot.get("camera"):
            raise ValueError("Each shot needs a camera and a motion or FEM mode.")
        if shot["mode"] == "fem" and not shot.get("parts"):
            raise ValueError(f"{shot['name']}: select at least one FEM body.")


def capture_display(document):
    result = {}
    for obj in document.Objects:
        view = getattr(obj, "ViewObject", None)
        if view is None:
            continue
        values = {}
        for name in _VIEW_PROPERTIES:
            if name in view.PropertiesList:
                value = getattr(view, name)
                if isinstance(value, (bool, int, float, str, tuple, list)):
                    values[name] = value
        result[obj.Name] = values
    return result


def apply_display(document, display):
    for name, properties in display.items():
        obj = document.getObject(name)
        if obj is None:
            raise ValueError(f"Shot references missing object {name}; recapture its display settings.")
        view = obj.ViewObject
        for prop, value in properties.items():
            if prop not in _VIEW_PROPERTIES:
                raise ValueError(f"Unsupported shot display property: {prop}")
            setattr(view, prop, tuple(value) if isinstance(value, list) else value)


def sequence_object(assembly):
    linked = getattr(assembly, "videoSequence", None)
    if linked is not None and "SequenceJSON" in linked.PropertiesList:
        return linked
    return next((obj for obj in assembly.Document.Objects
                 if getattr(obj, "VideoAssembly", None) == assembly
                 and "SequenceJSON" in obj.PropertiesList), None)


def load_sequence(assembly):
    obj = sequence_object(assembly)
    if obj is None:
        return {"version": 1, "fps": 30, "width": 1920, "height": 1080, "shots": []}
    sequence = json.loads(obj.SequenceJSON)
    for name in ("fps", "width", "height"):
        if name in obj.PropertiesList:
            sequence[name] = int(getattr(obj, name))
    return sequence


def _ensure_sequence_object(assembly):
    """Create or migrate a persistent parameter object owned by the assembly."""
    document = assembly.Document
    obj = sequence_object(assembly)
    if obj is None:
        obj = document.addObject("App::FeaturePython", "VideoSequence")
        obj.Label = "VideoSequence"
        obj.addProperty("App::PropertyLinkHidden", "VideoAssembly", "Video")
        obj.addProperty("App::PropertyString", "SequenceJSON", "Video")
        obj.SequenceJSON = json.dumps(load_sequence(assembly))
    elif obj.getTypeIdOfProperty("VideoAssembly") != "App::PropertyLinkHidden":
        # A back-reference must not create a dependency cycle with its owner.
        obj.removeProperty("VideoAssembly")
        obj.addProperty("App::PropertyLinkHidden", "VideoAssembly", "Video")
    obj.VideoAssembly = assembly
    obj.setEditorMode("VideoAssembly", 1)
    settings = json.loads(obj.SequenceJSON)
    for name, minimum, maximum, default in (("fps", 1, 120, 30),
                                             ("width", 64, 8192, 1920),
                                             ("height", 64, 8192, 1080)):
        if name not in obj.PropertiesList:
            obj.addProperty("App::PropertyIntegerConstraint", name, "Video")
            setattr(obj, name, (int(settings.get(name, default)), minimum, maximum, 1))
    if ("videoSequence" in assembly.PropertiesList
            and assembly.getTypeIdOfProperty("videoSequence") != "App::PropertyLinkChild"):
        assembly.removeProperty("videoSequence")
    if "videoSequence" not in assembly.PropertiesList:
        assembly.addProperty("App::PropertyLinkChild", "videoSequence", "MbDFEM",
                             "Saved camera shots and video export settings")
    if obj not in assembly.Group:
        assembly.addObject(obj)
    assembly.videoSequence = obj
    view = getattr(obj, "ViewObject", None)
    if view is not None and not isinstance(view.Proxy, VideoSequenceViewProvider):
        VideoSequenceViewProvider(view)
    return obj


def save_sequence(assembly, sequence):
    document = assembly.Document
    document.openTransaction("Save MbDFEM video sequence")
    try:
        obj = _ensure_sequence_object(assembly)
        obj.SequenceJSON = json.dumps(sequence)
        for name in ("fps", "width", "height"):
            setattr(obj, name, int(sequence[name]))
        document.commitTransaction()
    except Exception:
        document.abortTransaction()
        raise
    return obj


class VideoSequenceViewProvider:
    """Persistent double-click behavior for the assembly's VideoSequence."""

    def __init__(self, view_object):
        view_object.Proxy = self

    def getIcon(self):
        return ":/icons/Document.svg"

    def updateData(self, obj, prop):
        if prop not in ("fps", "width", "height") or _dialog is None:
            return
        if getattr(_dialog.assembly, "videoSequence", None) == obj:
            getattr(_dialog, prop).setValue(int(getattr(obj, prop)))

    def doubleClicked(self, view_object):
        import FreeCAD as App
        try:
            show_dialog(view_object.Object.VideoAssembly)
            return True
        except Exception as exc:
            App.Console.PrintError(f"Video Sequence: {exc}\n")
            return False

    def dumps(self):
        return None

    def loads(self, state):
        pass


class VideoSequenceTaskPanel:
    """FreeCAD task-panel lifecycle, with settings retained on Close."""

    def __init__(self, editor):
        self.editor = editor
        self.form = editor
        self._closed = False
        editor.destroyed.connect(self._destroyed)

    def getStandardButtons(self):
        from PySide import QtWidgets
        return QtWidgets.QDialogButtonBox.Close

    def isAllowedAlterDocument(self):
        return True

    def isAllowedAlterView(self):
        return True

    def isAllowedAlterSelection(self):
        return True

    def accept(self):
        return self.editor.save()

    def reject(self):
        return self.accept()

    def close(self):
        import FreeCADGui as Gui
        if self._closed:
            return True
        if not self.reject():
            return False
        Gui.Control.closeDialog(Gui.getDocument(self.editor.assembly.Document.Name))
        return True

    def _destroyed(self, *args):
        self._closed = True
        global _dialog
        if _dialog is self.editor:
            _dialog = None


def _is_own_task_panel(assembly):
    import FreeCADGui as Gui
    if (_dialog is None or getattr(_dialog, "assembly", None) != assembly
            or getattr(_dialog, "_task_panel", None) is None or _dialog._task_panel._closed):
        return False
    if Gui.activeDocument().Document != assembly.Document:
        return False
    active = Gui.Control.activeTaskDialog(Gui.getDocument(assembly.Document.Name))
    return active is not None and any(widget.isAncestorOf(_dialog)
                                      for widget in active.getDialogContent())


def _motion_assembly(assembly):
    return assembly.mbdItem if assembly.isDerivedFrom("MbDFEM::FEMAssembly") else assembly


class _ExportCancelled(Exception):
    """Stop preparation while preserving the export cancellation manifest."""


def _fem_controller(assembly, shot, preparation=None):
    import FreeCADMbDFEMAnimation as Animation
    if not assembly.isDerivedFrom("MbDFEM::FEMAssembly"):
        raise ValueError("FEM shots require an FEMAssembly.")
    controller = Animation.FEMAnimationController(assembly)
    parts = [assembly.Document.getObject(name) for name in shot["parts"]]
    if any(part is None for part in parts):
        raise ValueError(f"{shot['name']}: a selected FEM body is missing.")
    controller.set_parts(parts)
    states = controller.interval_states(shot["first"], shot["last"])
    if shot["first"] not in states or shot["last"] not in states:
        raise ValueError(f"{shot['name']}: both interval endpoints need results for every selected body.")
    def report(part, state, done, total):
        if preparation is not None and preparation(
                f"Preparing FEM colour scale: {part.Label}, state {state}", done, total) is False:
            raise _ExportCancelled()
    controller.prepare_display(shot["field"], True, shot["first"], shot["last"], progress=report)
    return controller, states


def _set_diagrams(motion_assembly, names):
    import FreeCADMbDFreeBodyDiagram as Diagram
    Diagram.set_visible_parts(motion_assembly, names)


def _load_diagram_modules():
    import FreeCADMbDFEMCLOADs
    import FreeCADMbDFEMDLOADs
    return {"cloads": FreeCADMbDFEMCLOADs, "dloads": FreeCADMbDFEMDLOADs}


def capture_load_diagrams(assembly):
    return {key: [diagram.fem_part.Name for diagram in module._diagrams.values()
                  if diagram.assembly is assembly and diagram.is_valid()]
            for key, module in _load_diagram_modules().items()}


def apply_load_diagrams(assembly, settings):
    current = capture_load_diagrams(assembly)
    for key, module in _load_diagram_modules().items():
        names = set(settings.get(key, []))
        for name in set(current[key]).symmetric_difference(names):
            part = assembly.Document.getObject(name)
            if part is None or not part.isDerivedFrom("MbDFEM::FEMPart"):
                raise ValueError(f"Missing FEM load-arrow body: {name}")
            visible = module._toggle_fem_part(part)
            if name in names and not visible:
                raise RuntimeError(f"Unable to display {key} for {name}.")
        if names:
            module.prepare_diagram_scale(assembly, force=True)


def _check_motion_visibility(assembly, shot):
    """A hidden motion assembly cannot replace the FEM geometry hidden for motion shots."""
    if shot["mode"] != "motion":
        return
    motion = _motion_assembly(assembly)
    if shot["display"].get(motion.Name, {}).get("Visibility") is False:
        raise ValueError(
            f"{shot['name']}: the captured Motion shot hides {motion.Label}. "
            "Motion export hides FEM results, so this would leave the model invisible. "
            "Show the MbD assembly and choose Update shot, or choose FEM results "
            "and Update shot to export stress contours.")


def _hide_fem_results(document, selected=()):
    """Avoid showing stale FEM geometry in motion shots or unselected bodies."""
    import FreeCADMbDFEMResultsPanel as Results
    for part in document.Objects:
        if part.isDerivedFrom("MbDFEM::FEMPart") and part.Name not in selected:
            objects = [getattr(part, "visual", None)] + Results._linked_results(part)
            for obj in objects:
                if obj is not None:
                    obj.ViewObject.Visibility = False
                    mesh = getattr(obj, "Mesh", None)
                    if mesh is not None:
                        mesh.ViewObject.Visibility = False


def _caption(image, shot, motion):
    from PySide import QtCore, QtGui
    painter = QtGui.QPainter(image)
    try:
        font = QtGui.QFont("Arial")
        font.setPixelSize(max(14, image.height() // 40))
        painter.setFont(font)
        text = (f"{shot['name']}\nState {motion.current_frame}"
                f"  |  t = {motion.current_time:.6g} s")
        flags = int(QtCore.Qt.AlignLeft | QtCore.Qt.AlignTop)
        bounds = painter.boundingRect(QtCore.QRect(20, 20, image.width() - 40, image.height() - 40),
                                      flags, text)
        painter.fillRect(bounds.adjusted(-8, -6, 8, 6), QtGui.QColor(0, 0, 0, 190))
        painter.setPen(QtGui.QColor("white"))
        painter.drawText(bounds, flags, text)
    finally:
        painter.end()


def _render_frame(view, width, height):
    return view.getViewer().renderToImage(width=width, height=height, samples=0)


def _export_progress_dialog(parent):
    from PySide import QtCore, QtWidgets
    dialog = QtWidgets.QProgressDialog("Preparing export…", "Cancel", 0, 0, parent)
    dialog.setWindowTitle("MbDFEM video export")
    label = QtWidgets.QLabel("Preparing export…")
    label.setWordWrap(True)
    label.setTextFormat(QtCore.Qt.PlainText)
    label.setAlignment(QtCore.Qt.AlignLeft | QtCore.Qt.AlignVCenter)
    label.setMinimumHeight(80)
    dialog.setLabel(label)
    dialog.setMinimumSize(640, 180)
    dialog.setWindowModality(QtCore.Qt.ApplicationModal)
    dialog.setMinimumDuration(0)
    dialog.setAutoClose(False)
    dialog.setAutoReset(False)
    dialog.show()
    QtWidgets.QApplication.processEvents()
    return dialog


def _video_dependencies():
    """Check the encoder before spending time rendering frames."""
    try:
        import av
        from PIL import Image
    except ImportError as exc:
        raise RuntimeError("Video export requires PyAV and Pillow in FreeCAD's Python runtime.") from exc
    for codec in ("libx264", "mpeg4"):
        try:
            av.codec.Codec(codec, "w")
            return av, Image, codec
        except av.codec.codec.UnknownCodecError:
            pass
    raise RuntimeError("No MP4 encoder is available in PyAV.")


def encode_video(output, files, fps, size, progress=None):
    """Encode PNGs with FreeCAD Assembly's PyAV approach; False means cancelled."""
    av, Image, codec = _video_dependencies()
    with av.open(str(output), "w", format="mp4") as container:
        stream = container.add_stream(codec, rate=fps)
        stream.width, stream.height = size
        stream.pix_fmt = "yuv420p"
        for index, filename in enumerate(files):
            if progress is not None and progress(index, len(files)) is False:
                return False
            with Image.open(filename) as image:
                frame = av.VideoFrame.from_image(image.convert("RGB"))
            for packet in stream.encode(frame):
                container.mux(packet)
        for packet in stream.encode(None):
            container.mux(packet)
    return True


def export_video(assembly, sequence, name, keep_frames=False, progress=None):
    """Create Case001/Videos/name[/Frames], preserving frames on failure/cancel."""
    import FreeCADMbDBackend as Backend

    _video_dependencies()
    if sequence["width"] % 2 or sequence["height"] % 2:
        raise ValueError("MP4 export requires even width and height.")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]*", name):
        raise ValueError("Use a video name starting with a letter or digit, followed by letters, digits, _ or -.")
    videos = Backend.default_case_dir(assembly) / "Videos"
    videos.mkdir(parents=True, exist_ok=True)
    # Reserve a new directory without overwriting any earlier export.
    index = 1
    while True:
        label = name if index == 1 else f"{name}_{index:03d}"
        output = videos / label
        try:
            output.mkdir()
            break
        except FileExistsError:
            index += 1
    frames = output / "Frames"
    movie = output / f"{label}.mp4"
    partial = output / f"{label}.partial.mp4"
    manifest = {"version": 1, "sequence": sequence, "frames": [], "status": "failed"}
    video = {"file": movie.name, "status": "rendering", "frames_retained": True}
    try:
        callback = (lambda done, total: progress("Rendering frames", done, total)) if progress else None
        options = {"preparation": progress} if progress is not None else {}
        manifest = export_sequence(assembly, sequence, frames, callback, **options)
        if manifest["status"] != "complete":
            video["status"] = "cancelled"
            return output
        video["status"] = "encoding"
        callback = (lambda done, total: progress("Encoding video", done, total)) if progress else None
        if not encode_video(partial, [frames / item["file"] for item in manifest["frames"]],
                            sequence["fps"], (sequence["width"], sequence["height"]), callback):
            manifest["status"] = video["status"] = "cancelled"
            return output
        partial.rename(movie)
        video["status"] = "complete"
        if not keep_frames:
            for item in manifest["frames"]:
                (frames / item["file"]).unlink()
            (frames / "manifest.json").unlink()
            frames.rmdir()
            video["frames_retained"] = False
        return output
    except Exception as exc:
        # Rendering writes its own failure manifest; preserve its completed frame list.
        if video["status"] == "rendering" and (frames / "manifest.json").exists():
            manifest = json.loads((frames / "manifest.json").read_text(encoding="utf-8"))
        manifest["status"] = video["status"] = "failed"
        manifest["error"] = str(exc)
        raise RuntimeError(f"Video export failed. Frames and manifest: {output}\n{exc}") from exc
    finally:
        partial.unlink(missing_ok=True)
        manifest["video"] = video
        for item in manifest["frames"]:
            item["file"] = "Frames/" + item["file"]
        (output / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")


def export_sequence(assembly, sequence, directory, progress=None, preparation=None):
    """Export to a new/empty directory. Return manifest, also written on cancellation.

    progress(completed, total) returns False to cancel. Export changes are enclosed
    in an aborted document transaction; cameras and transient diagrams are restored
    separately. FEM datasets use the document transaction's native VTK backups.
    """
    import FreeCADGui as Gui
    import FreeCADMbDAnimation as Animation
    import FreeCADMbDFreeBodyDiagram as Diagram

    document = assembly.Document
    if document.HasPendingTransaction:
        raise ValueError("Finish the current document edit before exporting.")
    if Gui.Control.activeDialog() and not _is_own_task_panel(assembly):
        raise ValueError("Close the active task panel before exporting.")
    motion_assembly = _motion_assembly(assembly)
    # Creating a controller can apply its saved state, so do it inside the transaction.
    count = len(motion_assembly.times)
    validate_sequence(sequence, count)
    for shot in sequence["shots"]:
        _check_motion_visibility(assembly, shot)
    output = Path(directory)
    if output.exists() and any(output.iterdir()):
        raise ValueError("Choose an empty output directory; existing files will not be overwritten.")
    view = Gui.activeDocument().activeView()
    if Gui.activeDocument().Document != document:
        raise ValueError("Activate the sequence's document before exporting.")
    view.stopAnimating()
    camera = view.getCamera()
    modified = Gui.activeDocument().Modified
    display = capture_display(document)
    diagrams = Diagram.visible_parts(motion_assembly)
    load_diagrams = capture_load_diagrams(motion_assembly)
    pipelines = [obj for obj in document.Objects
                if obj.isDerivedFrom("Fem::FemPostPipeline")]
    total = sum(frame_count(shot["duration"], sequence["fps"]) for shot in sequence["shots"])
    manifest = {"version": 1, "sequence": sequence, "status": "cancelled", "frames": []}
    output.mkdir(parents=True, exist_ok=True)
    document.openTransaction("Render MbDFEM video sequence")
    try:
        def prepare(stage):
            if preparation is not None and preparation(stage, 0, 0) is False:
                raise _ExportCancelled()
        prepare("Preparing motion timeline")
        motion = Animation.AnimationController(motion_assembly)
        if motion.source_frame_count != count:
            validate_sequence(sequence, motion.source_frame_count)
        parameters = motion_assembly.ensureAnimationParameters()
        parameters.startFrame = 0
        parameters.endFrame = count - 1
        parameters.interpolateFrames = True
        # Validate every shot before writing frames.
        fem = {}
        for index, shot in enumerate(sequence["shots"]):
            prepare(f"Preparing shot {index + 1}/{len(sequence['shots'])}: {shot['name']}")
            apply_display(document, shot["display"])
            if shot["mode"] == "fem":
                fem[index] = _fem_controller(assembly, shot, preparation)
        for shot_index, shot in enumerate(sequence["shots"]):
            prepare(f"Applying camera and display for shot {shot_index + 1}: {shot['name']}")
            apply_display(document, display)
            apply_display(document, shot["display"])
            view.setCamera(shot["camera"])
            _set_diagrams(motion_assembly, shot.get("diagrams", []))
            if shot.get("diagrams"):
                Diagram.prepare_diagram_scales(motion_assembly, force=True)
            apply_load_diagrams(motion_assembly, shot.get("loads", {}))
            prepare(f"Preparing result visibility for shot {shot_index + 1}: {shot['name']}")
            _hide_fem_results(document, shot["parts"] if shot["mode"] == "fem" else ())
            times = motion.result_times
            samples = sample_times(times[shot["first"]], times[shot["last"]],
                                   frame_count(shot["duration"], sequence["fps"]))
            previous_state = None
            for seconds in samples:
                if progress is not None and progress(len(manifest["frames"]), total) is False:
                    return manifest
                if shot["mode"] == "fem":
                    controller, states = fem[shot_index]
                    state = nearest_state(states, times, seconds)
                    if state != previous_state:
                        def state_progress(stage, done, total):
                            if preparation is not None and preparation(stage, done, total) is False:
                                raise _ExportCancelled()
                        controller.show_state(state, schedule_refresh=False, progress=state_progress)
                        previous_state = state
                    active_motion = controller.motion
                else:
                    motion.setTime(seconds)
                    active_motion = motion
                if progress is not None and progress(len(manifest["frames"]), total) is False:
                    return manifest
                Gui.updateGui()
                image = _render_frame(view, sequence["width"], sequence["height"])
                if image.isNull():
                    raise RuntimeError("Unable to render the active 3D view.")
                if shot.get("caption", True):
                    _caption(image, shot, active_motion)
                filename = f"frame_{len(manifest['frames']):06d}.png"
                if not image.save(str(output / filename), "PNG"):
                    raise OSError(f"Unable to save {filename}.")
                manifest["frames"].append({"file": filename, "shot": shot_index,
                                            "time": active_motion.current_time,
                                            "state": active_motion.current_frame})
        manifest["status"] = "complete"
        if progress is not None:
            progress(total, total)
        return manifest
    except _ExportCancelled:
        return manifest
    except Exception as exc:
        manifest["status"] = "failed"
        manifest["error"] = str(exc)
        raise
    finally:
        # Restoration must finish even after cancellation; keep its stage visible.
        if preparation is not None:
            preparation("Restoring scene and FEM result data", 0, 0)
        document.abortTransaction()
        for position, obj in enumerate(pipelines):
            if preparation is not None:
                preparation(f"Restoring FEM display\n{obj.Label}", position, len(pipelines))
            obj.recomputeChildren()
        apply_display(document, display)
        _set_diagrams(motion_assembly, diagrams)
        apply_load_diagrams(motion_assembly, load_diagrams)
        if diagrams:
            Diagram.refresh_assembly_diagrams(document.Name, motion_assembly.Name, True)
        for key, module in _load_diagram_modules().items():
            if load_diagrams[key]:
                module.refresh_assembly_diagrams(document.Name, motion_assembly.Name, True)
        import FreeCADMbDFEMStateOverlay as Overlay
        if Overlay._manager is not None:
            Overlay._manager.samples.pop(document.Name, None)
            Overlay._manager.refresh()
        if preparation is not None:
            preparation("Recomputing restored scene", 0, 0)
        document.recompute()
        Gui.updateGui()
        view.setCamera(camera)
        Gui.activeDocument().Modified = modified
        (output / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")


class VideoSequenceCommand:
    def GetResources(self):
        return {"MenuText": "Video Sequence…",
                "ToolTip": "Save camera shots and export an MbDFEM video or PNG image sequence"}

    @staticmethod
    def active_assembly():
        import FreeCAD as App
        import FreeCADGui as Gui
        document = App.ActiveDocument
        if document is None:
            return None
        kinds = ("MbDFEM::MbDAssembly", "MbDFEM::FEMAssembly")
        for obj in Gui.Selection.getSelection():
            if any(obj.isDerivedFrom(kind) for kind in kinds):
                return obj
            linked = getattr(obj, "VideoAssembly", None)
            if linked is not None:
                return linked
        assemblies = [obj for obj in document.Objects if obj.isDerivedFrom(kinds[1])]
        if not assemblies:
            assemblies = [obj for obj in document.Objects if obj.isDerivedFrom(kinds[0])]
        return assemblies[0] if len(assemblies) == 1 else None

    def IsActive(self):
        assembly = self.active_assembly()
        if assembly is None:
            return False
        motion = _motion_assembly(assembly)
        return motion is not None and bool(getattr(motion, "times", []))

    def Activated(self):
        from PySide import QtWidgets
        import FreeCADGui as Gui
        try:
            show_dialog(self.active_assembly())
        except Exception as exc:
            QtWidgets.QMessageBox.warning(Gui.getMainWindow(), "Video Sequence", str(exc))


def show_dialog(assembly):
    """Open the assembly's persistent VideoSequence in FreeCAD's Tasks tab."""
    from PySide import QtCore, QtWidgets
    import FreeCADGui as Gui
    import FreeCADMbDFreeBodyDiagram as Diagram
    import FreeCADMbDFEMResultsPanel as Results

    if assembly is None or _motion_assembly(assembly) is None:
        raise ValueError("Select an assembly linked to a solved MbD motion timeline.")
    if not _motion_assembly(assembly).times:
        raise ValueError("Solve or import motion results before creating a video sequence.")
    gui_document = Gui.getDocument(assembly.Document.Name)
    Gui.setActiveDocument(assembly.Document.Name)
    global _dialog
    if Gui.Control.activeDialog(gui_document):
        if _is_own_task_panel(assembly):
            if _dialog.isVisible():
                return _dialog
            if not _dialog.close():
                raise ValueError("Save the current video settings before reopening its task panel.")
        else:
            raise ValueError("Close the current task panel before opening Video Sequence.")
    if sequence_object(assembly) is None or not hasattr(assembly, "videoSequence"):
        save_sequence(assembly, load_sequence(assembly))
    else:
        _ensure_sequence_object(assembly)

    class VideoPanel(QtWidgets.QWidget):
        def __init__(self):
            super().__init__()
            self.assembly = assembly
            self._task_panel = None
            self.setWindowTitle("MbDFEM Video Sequence")
            self.sequence = load_sequence(assembly)
            layout = QtWidgets.QVBoxLayout(self)
            help_text = QtWidgets.QLabel(
                "Arrange the 3D view, visibility, colors and arrows, then capture a shot.\n"
                "A fixed camera is saved per shot. Equal first/last states create a pause.\n"
                "FEM shots hold the nearest saved common state; stress is not interpolated.")
            help_text.setWordWrap(True)
            layout.addWidget(help_text)
            self.shots = QtWidgets.QListWidget()
            self.shots.setMinimumHeight(80)
            self.shots.setMaximumHeight(160)
            layout.addWidget(self.shots)
            form = QtWidgets.QFormLayout()
            layout.addLayout(form)
            self.name = QtWidgets.QLineEdit("Mechanism motion")
            self.first = QtWidgets.QSpinBox()
            self.last = QtWidgets.QSpinBox()
            maximum = max(0, len(_motion_assembly(assembly).times) - 1)
            for spin in (self.first, self.last):
                spin.setRange(0, maximum)
            self.first.setValue(1 if maximum else 0)
            self.last.setValue(maximum)
            self.duration = QtWidgets.QDoubleSpinBox()
            self.duration.setRange(0.01, 3600)
            self.duration.setValue(5)
            self.duration.setSuffix(" s")
            self.mode = QtWidgets.QComboBox()
            self.mode.addItem("Motion", "motion")
            if assembly.isDerivedFrom("MbDFEM::FEMAssembly"):
                self.mode.addItem("FEM results", "fem")
            self.field = QtWidgets.QComboBox()
            for field in Results._PIPELINE_SCALAR_FIELD_PROPERTIES:
                self.field.addItem(Results._pipeline_field_display_label(field), field)
            self.field.setCurrentIndex(self.field.findData(Results._DEFAULT_PIPELINE_FIELD))
            self.parts = QtWidgets.QListWidget()
            self.parts.setMaximumHeight(95)
            for part in getattr(assembly, "parts", []):
                if Results._linked_results(part):
                    item = QtWidgets.QListWidgetItem(part.Label)
                    item.setData(QtCore.Qt.UserRole, part.Name)
                    item.setFlags(item.flags() | QtCore.Qt.ItemIsUserCheckable)
                    item.setCheckState(QtCore.Qt.Checked)
                    self.parts.addItem(item)
            self.caption = QtWidgets.QCheckBox("Shot title and state/time caption")
            self.caption.setChecked(True)
            for label, widget in (("Shot name", self.name), ("First state", self.first),
                                  ("Last state", self.last), ("Screen duration", self.duration),
                                  ("Playback", self.mode), ("FEM field", self.field),
                                  ("FEM bodies", self.parts), ("", self.caption)):
                form.addRow(label, widget)
            buttons = QtWidgets.QGridLayout()
            layout.addLayout(buttons)
            shot_actions = (("Capture new", self.capture), ("Update shot", self.update_shot),
                            ("Preview", self.preview), ("Remove", self.remove),
                            ("Up", lambda: self.move(-1)), ("Down", lambda: self.move(1)))
            for index, (title, callback) in enumerate(shot_actions):
                button = QtWidgets.QPushButton(title)
                button.clicked.connect(callback)
                buttons.addWidget(button, index // 3, index % 3)
            self.feedback = QtWidgets.QLabel("Capture a shot to begin.")
            self.feedback.setWordWrap(True)
            layout.addWidget(self.feedback)
            settings = QtWidgets.QFormLayout()
            layout.addLayout(settings)
            self.fps = QtWidgets.QSpinBox()
            self.fps.setRange(1, 120)
            self.fps.setValue(self.sequence["fps"])
            self.width = QtWidgets.QSpinBox()
            self.height = QtWidgets.QSpinBox()
            for label, widget, key in (("Width", self.width, "width"), ("Height", self.height, "height")):
                widget.setRange(64, 8192)
                widget.setValue(self.sequence[key])
                settings.addRow(label, widget)
            settings.addRow("Output FPS", self.fps)
            self.keep_frames = QtWidgets.QCheckBox("Keep frames after video export")
            layout.addWidget(self.keep_frames)
            actions = QtWidgets.QGridLayout()
            layout.addLayout(actions)
            for index, (title, callback) in enumerate(
                    (("Save sequence", self.save_with_confirmation), ("Export PNGs…", self.export),
                     ("Export video…", self.export_movie))):
                button = QtWidgets.QPushButton(title)
                button.clicked.connect(callback)
                actions.addWidget(button, index // 2, index % 2, 1, 2 if index == 2 else 1)
            self.shots.currentRowChanged.connect(self.select)
            self.mode.currentIndexChanged.connect(self.mode_changed)
            self.refresh()
            self.mode_changed()

        def close(self):
            if self._task_panel is not None:
                return self._task_panel.close()
            return super().close()

        def mode_changed(self):
            enabled = self.mode.currentData() == "fem"
            self.field.setEnabled(enabled)
            self.parts.setEnabled(enabled)

        def refresh(self, row=-1):
            self.shots.blockSignals(True)
            self.shots.clear()
            for shot in self.sequence["shots"]:
                self.shots.addItem(f"{shot['name']}  |  {shot['first']}–{shot['last']}  |  {shot['duration']:g} s")
            self.shots.blockSignals(False)
            self.shots.setCurrentRow(row)

        def select(self, row):
            if row < 0:
                return
            shot = self.sequence["shots"][row]
            self.name.setText(shot["name"])
            self.first.setValue(shot["first"])
            self.last.setValue(shot["last"])
            self.duration.setValue(shot["duration"])
            self.mode.setCurrentIndex(self.mode.findData(shot["mode"]))
            self.field.setCurrentIndex(self.field.findData(shot["field"]))
            self.caption.setChecked(shot.get("caption", True))
            for index in range(self.parts.count()):
                item = self.parts.item(index)
                item.setCheckState(QtCore.Qt.Checked if item.data(QtCore.Qt.UserRole) in shot["parts"]
                                   else QtCore.Qt.Unchecked)

        def shot(self):
            if Gui.activeDocument().Document != assembly.Document:
                raise ValueError("Activate this sequence's document before capturing a shot.")
            Gui.activeDocument().activeView().stopAnimating()
            return {"name": self.name.text().strip() or "Shot", "first": self.first.value(),
                    "last": self.last.value(), "duration": self.duration.value(),
                    "mode": self.mode.currentData(), "field": self.field.currentData(),
                    "parts": [self.parts.item(index).data(QtCore.Qt.UserRole)
                              for index in range(self.parts.count())
                              if self.parts.item(index).checkState() == QtCore.Qt.Checked],
                    "camera": Gui.activeDocument().activeView().getCamera(),
                    "display": capture_display(assembly.Document),
                    "diagrams": Diagram.visible_parts(_motion_assembly(assembly)),
                    "loads": capture_load_diagrams(_motion_assembly(assembly)),
                    "caption": self.caption.isChecked()}

        def capture(self):
            try:
                self.sequence["shots"].append(self.shot())
                self.refresh(len(self.sequence["shots"]) - 1)
                self.feedback.setText(
                    f"Captured shot {len(self.sequence['shots'])}: {self.sequence['shots'][-1]['name']}. "
                    "Use Save sequence to store it in the document.")
            except Exception as exc:
                QtWidgets.QMessageBox.warning(self, "Video Sequence", str(exc))

        def update_shot(self):
            row = self.shots.currentRow()
            if row >= 0:
                try:
                    self.sequence["shots"][row] = self.shot()
                    self.refresh(row)
                    self.feedback.setText(
                        f"Updated shot {row + 1}. Use Save sequence to store the changes.")
                except Exception as exc:
                    QtWidgets.QMessageBox.warning(self, "Video Sequence", str(exc))

        def preview(self):
            import FreeCADMbDAnimation as Animation
            try:
                self.settings()
                row = self.shots.currentRow()
                if row < 0:
                    self.feedback.setText("Select a captured shot to preview.")
                    return
                if Gui.activeDocument().Document != assembly.Document:
                    raise ValueError("Activate this sequence's document before previewing.")
                shot = self.sequence["shots"][row]
                _check_motion_visibility(assembly, shot)
                motion_assembly = _motion_assembly(assembly)
                apply_display(assembly.Document, shot["display"])
                Gui.activeDocument().activeView().stopAnimating()
                Gui.activeDocument().activeView().setCamera(shot["camera"])
                _set_diagrams(motion_assembly, shot["diagrams"])
                apply_load_diagrams(motion_assembly, shot.get("loads", {}))
                _hide_fem_results(assembly.Document, shot["parts"] if shot["mode"] == "fem" else ())
                if shot["mode"] == "fem":
                    controller, _ = _fem_controller(assembly, shot)
                    controller.show_state(shot["first"])
                else:
                    Animation.AnimationController(motion_assembly).setFrame(shot["first"])
                Gui.updateGui()
                self.feedback.setText(
                    f"Preview applied: {shot['name']}, state {shot['first']}. "
                    "Preview shows the first state; export the sequence for video playback.")
            except Exception as exc:
                QtWidgets.QMessageBox.warning(self, "Video Sequence", str(exc))

        def remove(self):
            row = self.shots.currentRow()
            if row >= 0:
                self.sequence["shots"].pop(row)
                self.refresh(min(row, len(self.sequence["shots"]) - 1))

        def move(self, offset):
            row = self.shots.currentRow()
            other = row + offset
            shots = self.sequence["shots"]
            if 0 <= row < len(shots) and 0 <= other < len(shots):
                shots[row], shots[other] = shots[other], shots[row]
                self.refresh(other)

        def settings(self, allow_empty=False):
            for spin in (self.first, self.last, self.duration, self.fps, self.width, self.height):
                spin.interpretText()
            self.sequence.update(fps=self.fps.value(), width=self.width.value(), height=self.height.value())
            if self.sequence["shots"] or not allow_empty:
                validate_sequence(self.sequence, len(_motion_assembly(assembly).times))

        def save(self):
            try:
                self.settings(allow_empty=True)
                save_sequence(assembly, self.sequence)
                count = len(self.sequence["shots"])
                self.feedback.setText(
                    f"Sequence saved in document ({count} {'shot' if count == 1 else 'shots'}). "
                    "Save the FCStd file to keep it between sessions.")
                return True
            except Exception as exc:
                QtWidgets.QMessageBox.warning(self, "Video Sequence", str(exc))
                return False

        def save_with_confirmation(self):
            if self.save():
                QtWidgets.QMessageBox.information(
                    self, "Sequence saved", self.feedback.text())

        def export_movie(self):
            try:
                self.settings()
                name, accepted = QtWidgets.QInputDialog.getText(
                    self, "Export video", "Video name (saved under Case001/Videos):",
                    text="MechanismMotion")
                if not accepted:
                    return
                view = Gui.activeDocument().activeView()
                camera = view.getCamera()
                progress = _export_progress_dialog(self)
                try:
                    def advance(stage, done, total):
                        progress.setLabelText(
                            f"{stage}\n{done} / {total}" if total else stage + "…")
                        progress.setRange(0, total)
                        progress.setValue(done)
                        QtWidgets.QApplication.processEvents()
                        return not progress.wasCanceled()
                    advance("Preparing video export", 0, 0)
                    directory = export_video(assembly, self.sequence, name.strip(),
                                             self.keep_frames.isChecked(), advance)
                finally:
                    progress.close()
                    QtWidgets.QApplication.processEvents()
                    view.setCamera(camera)
                manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
                QtWidgets.QMessageBox.information(
                    self, "Video Sequence", f"Video export {manifest['video']['status']}.\n{directory}")
            except Exception as exc:
                QtWidgets.QMessageBox.warning(self, "Video Sequence", str(exc))

        def export(self):
            try:
                self.settings()
                directory = QtWidgets.QFileDialog.getExistingDirectory(self, "Choose an empty frame directory")
                if not directory:
                    return
                view = Gui.activeDocument().activeView()
                camera = view.getCamera()
                progress = _export_progress_dialog(self)
                try:
                    def advance(done, total):
                        progress.setLabelText(f"Rendering frames ({done}/{total})…")
                        progress.setMaximum(total)
                        progress.setValue(done)
                        QtWidgets.QApplication.processEvents()
                        return not progress.wasCanceled()
                    def prepare(stage, done, total):
                        progress.setLabelText(
                            f"{stage}\n{done} / {total}" if total else stage + "…")
                        progress.setRange(0, total)
                        progress.setValue(done)
                        QtWidgets.QApplication.processEvents()
                        return not progress.wasCanceled()
                    prepare("Preparing PNG export", 0, 0)
                    manifest = export_sequence(assembly, self.sequence, directory, advance,
                                               preparation=prepare)
                finally:
                    progress.close()
                    QtWidgets.QApplication.processEvents()
                    view.setCamera(camera)
                QtWidgets.QMessageBox.information(
                    self, "Video Sequence",
                    f"Export {manifest['status']}: {len(manifest['frames'])} frames.\n{directory}")
            except Exception as exc:
                QtWidgets.QMessageBox.warning(self, "Video Sequence", str(exc))

    if _dialog is not None:
        previous = _dialog
        previous_task = getattr(previous, "_task_panel", None)
        if not previous.close():
            raise ValueError("Close the previous Video Sequence task panel first.")
        if previous_task is None:
            old_dock = getattr(previous, "_dock", None)
            (old_dock if old_dock is not None else previous).deleteLater()
    legacy_dock = Gui.getMainWindow().findChild(QtWidgets.QDockWidget, "MbDFEMVideoSequence")
    if legacy_dock is not None:
        legacy_dock.close()
        legacy_dock.deleteLater()
    _dialog = VideoPanel()
    panel = VideoSequenceTaskPanel(_dialog)
    _dialog._task_panel = panel
    handle = Gui.Control.showDialog(panel, gui_document)
    handle.setAutoCloseOnTransactionChange(False)
    handle.setAutoCloseOnResetEdit(False)
    return _dialog
