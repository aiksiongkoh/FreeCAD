# SPDX-License-Identifier: LGPL-2.1-or-later

import copy
import json
import re
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import FreeCADMbDFEMVideo as Video


class VideoTimelineTest(unittest.TestCase):
    def test_export_can_cancel_before_loading_a_fem_body(self):
        from types import SimpleNamespace
        from unittest.mock import Mock
        import FreeCADMbDFEMAnimation as Animation
        controller = Animation.FEMAnimationController.__new__(Animation.FEMAnimationController)
        controller.states = [1]
        controller.motion = SimpleNamespace(setFrame=Mock(), targets=[])
        controller.assembly = SimpleNamespace(Document=SimpleNamespace(recompute=Mock()))
        controller.parts = [SimpleNamespace(Name="Body", Label="Long pendulum")]
        controller.current_frame = 0

        def cancel(stage, done, total):
            if "Loading FEM state" in stage:
                self.assertIn("Long pendulum", stage)
                raise Video._ExportCancelled()

        with patch.object(Animation.Results, "_sync_fem_parts_to_mbd_parts"), \
                patch.object(Animation.Results, "_ensure_visual_pipeline") as load:
            with self.assertRaises(Video._ExportCancelled):
                controller.show_state(1, progress=cancel)
            load.assert_not_called()
            controller.assembly.Document.recompute.assert_not_called()
            self.assertEqual(controller.current_frame, 0)

    def test_fem_colour_scan_reports_before_each_state_and_can_be_cancelled(self):
        from types import SimpleNamespace
        import FreeCADMbDFEMAnimation as Animation
        controller = Animation.FEMAnimationController.__new__(Animation.FEMAnimationController)
        part = SimpleNamespace(Name="Body", Label="Body")
        controller.parts = [part]
        controller.states = [1, 2, 3]
        scanned, reported = [], []

        def scalar_range(part, field, state):
            scanned.append(state)
            return state, state + 1

        def report(part, state, done, total):
            reported.append((state, done, total, len(scanned)))

        with patch.object(Animation.Results, "_include_state_in_legend_scale", return_value=True), \
                patch.object(Animation.Results, "_state_pipeline_scalar_range", side_effect=scalar_range):
            controller.prepare_display("Stress", True, 1, 3, progress=report)
            self.assertEqual(reported, [(1, 0, 3, 0), (2, 1, 3, 1), (3, 2, 3, 2), (3, 3, 3, 3)])
            self.assertEqual(controller._ranges, {"Body": (1, 4)})
            scanned.clear()

            def cancel(part, state, done, total):
                if done == 1:
                    raise Video._ExportCancelled()

            with self.assertRaises(Video._ExportCancelled):
                controller.prepare_display("Stress", True, 1, 3, progress=cancel)
            self.assertEqual(scanned, [1])

    def test_hidden_motion_assembly_requires_recapture_or_fem_mode(self):
        from types import SimpleNamespace
        motion = SimpleNamespace(Name="MbDAssembly", Label="MbDAssembly")
        shot = {"name": "Stress view", "mode": "motion",
                "display": {"MbDAssembly": {"Visibility": False}}}
        with patch.object(Video, "_motion_assembly", return_value=motion):
            with self.assertRaisesRegex(ValueError, "FEM results.*Update shot"):
                Video._check_motion_visibility(None, shot)
            shot["mode"] = "fem"
            Video._check_motion_visibility(None, shot)
            shot["mode"] = "motion"
            shot["display"]["MbDAssembly"]["Visibility"] = True
            Video._check_motion_visibility(None, shot)

    def test_duration_is_quantized_and_endpoints_are_included(self):
        self.assertEqual(Video.frame_count(0.21, 30), 7)
        self.assertEqual(Video.sample_times(2, 4, 3), [2, 3, 4])
        self.assertEqual(Video.sample_times(4, 4, 3), [4, 4, 4])
        self.assertEqual(Video.sample_times(2, 4, 1), [2])
        for duration in (0, -1, float("nan"), float("inf")):
            with self.assertRaises(ValueError):
                Video.frame_count(duration, 30)

    def test_sparse_fem_states_use_time_and_ties_choose_earlier_state(self):
        times = [0, 0.1, 0.2, 1.0]
        self.assertEqual(Video.nearest_state([0, 3], times, 0.49), 0)
        self.assertEqual(Video.nearest_state([0, 3], times, 0.5), 0)
        self.assertEqual(Video.nearest_state([0, 3], times, 0.51), 3)
        with self.assertRaises(ValueError):
            Video.nearest_state([], times, 0.5)


class VideoMovieTest(unittest.TestCase):
    def render(self, assembly, sequence, directory, progress, preparation=None):
        from PIL import Image
        directory.mkdir()
        manifest = {"version": 1, "sequence": sequence, "status": "complete", "frames": []}
        for index in range(3):
            name = f"frame_{index:06d}.png"
            Image.new("RGB", (64, 64), (index * 80, 10, 20)).save(directory / name)
            manifest["frames"].append({"file": name, "shot": 0, "time": index / 10, "state": index})
        (directory / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
        return manifest

    def setUp(self):
        self.sequence = {"width": 64, "height": 64, "fps": 10, "shots": []}

    def test_mp4_round_trip_and_unique_folders(self):
        try:
            Video._video_dependencies()
        except RuntimeError as exc:
            self.skipTest(str(exc))
        import av
        with tempfile.TemporaryDirectory() as directory, \
                patch("FreeCADMbDBackend.default_case_dir", return_value=Path(directory)), \
                patch.object(Video, "export_sequence", side_effect=self.render):
            output = Video.export_video(None, self.sequence, "MechanismMotion")
            self.assertEqual(output, Path(directory) / "Videos" / "MechanismMotion")
            self.assertFalse((output / "Frames").exists())
            manifest = json.loads((output / "manifest.json").read_text())
            self.assertEqual(manifest["video"]["status"], "complete")
            self.assertFalse(manifest["video"]["frames_retained"])
            self.assertEqual(manifest["frames"][0]["file"], "Frames/frame_000000.png")
            with av.open(str(output / "MechanismMotion.mp4")) as container:
                frames = list(container.decode(video=0))
                self.assertEqual(len(frames), 3)
                self.assertEqual((frames[0].width, frames[0].height), (64, 64))
                self.assertEqual(container.streams.video[0].average_rate, 10)
            second = Video.export_video(None, self.sequence, "MechanismMotion", keep_frames=True)
            self.assertEqual(second.name, "MechanismMotion_002")
            self.assertTrue((second / "Frames/frame_000002.png").exists())
            self.assertTrue((output / "MechanismMotion.mp4").exists())

    def test_encoding_cancel_and_failure_preserve_frames(self):
        for failure in (False, RuntimeError("Encoder failed")):
            with self.subTest(failure=failure), tempfile.TemporaryDirectory() as directory, \
                    patch.object(Video, "_video_dependencies"), \
                    patch("FreeCADMbDBackend.default_case_dir", return_value=Path(directory)), \
                    patch.object(Video, "export_sequence", side_effect=self.render):
                def encode(output, *args):
                    output.write_bytes(b"partial video")
                    if isinstance(failure, Exception):
                        raise failure
                    return False
                with patch.object(Video, "encode_video", side_effect=encode):
                    if isinstance(failure, Exception):
                        with self.assertRaisesRegex(RuntimeError, "Encoder failed"):
                            Video.export_video(None, self.sequence, "Test")
                    else:
                        Video.export_video(None, self.sequence, "Test")
                output = Path(directory) / "Videos/Test"
                manifest = json.loads((output / "manifest.json").read_text())
                self.assertEqual(manifest["status"], "failed" if failure else "cancelled")
                self.assertTrue((output / "Frames/frame_000002.png").exists())
                self.assertFalse(list(output.glob("*.mp4")))

    def test_success_cleanup_keep_frames_and_repeated_names(self):
        def encode(output, *args):
            output.write_bytes(b"encoded video")
            return True
        with tempfile.TemporaryDirectory() as directory, \
                patch.object(Video, "_video_dependencies"), \
                patch("FreeCADMbDBackend.default_case_dir", return_value=Path(directory)), \
                patch.object(Video, "export_sequence", side_effect=self.render), \
                patch.object(Video, "encode_video", side_effect=encode):
            first = Video.export_video(None, self.sequence, "Test")
            second = Video.export_video(None, self.sequence, "Test", keep_frames=True)
            self.assertEqual(first.name, "Test")
            self.assertEqual(second.name, "Test_002")
            self.assertEqual((first / "Test.mp4").read_bytes(), b"encoded video")
            self.assertTrue((second / "Test_002.mp4").exists())
            self.assertFalse((first / "Frames").exists())
            self.assertTrue((second / "Frames/frame_000002.png").exists())
            for output, retained in ((first, False), (second, True)):
                manifest = json.loads((output / "manifest.json").read_text())
                self.assertEqual(manifest["status"], "complete")
                self.assertEqual(manifest["video"]["frames_retained"], retained)
                self.assertEqual(manifest["frames"][0]["file"], "Frames/frame_000000.png")

    def test_rendering_failure_keeps_completed_frame_records(self):
        def render(*args):
            manifest = self.render(*args)
            manifest.update(status="failed", error="Render failed")
            (args[2] / "manifest.json").write_text(json.dumps(manifest))
            raise RuntimeError("Render failed")
        with tempfile.TemporaryDirectory() as directory, \
                patch.object(Video, "_video_dependencies"), \
                patch("FreeCADMbDBackend.default_case_dir", return_value=Path(directory)), \
                patch.object(Video, "export_sequence", side_effect=render):
            with self.assertRaisesRegex(RuntimeError, "Render failed"):
                Video.export_video(None, self.sequence, "Test")
            manifest = json.loads((Path(directory) / "Videos/Test/manifest.json").read_text())
            self.assertEqual(len(manifest["frames"]), 3)
            self.assertEqual(manifest["status"], "failed")

    def test_invalid_name_or_odd_dimensions_create_no_export(self):
        with tempfile.TemporaryDirectory() as directory, \
                patch.object(Video, "_video_dependencies"), \
                patch("FreeCADMbDBackend.default_case_dir", return_value=Path(directory)):
            for name in ("../outside", "", "A/B", "A\\B"):
                with self.assertRaises(ValueError):
                    Video.export_video(None, self.sequence, name)
            self.sequence["width"] = 65
            with self.assertRaisesRegex(ValueError, "even"):
                Video.export_video(None, self.sequence, "Test")
            self.assertFalse((Path(directory) / "Videos").exists())

    def test_missing_encoder_fails_before_rendering(self):
        with patch.object(Video, "_video_dependencies", side_effect=RuntimeError("PyAV missing")), \
                patch.object(Video, "export_sequence") as render, \
                patch("FreeCADMbDBackend.default_case_dir") as case:
            with self.assertRaisesRegex(RuntimeError, "PyAV missing"):
                Video.export_video(None, self.sequence, "Test")
            render.assert_not_called()
            case.assert_not_called()


class VideoExportTest(unittest.TestCase):
    def setUp(self):
        try:
            import FreeCAD as App
            import FreeCADGui as Gui
        except ImportError:
            self.skipTest("FreeCAD GUI is required")
        if not App.GuiUp:
            self.skipTest("FreeCAD GUI is required")
        import TestMbDFEMGui
        self.App, self.Gui = App, Gui
        self.document = App.newDocument("VideoExportTest")
        Gui.setActiveDocument(self.document.Name)
        helper = TestMbDFEMGui.MbDFEMGuiViewProviderTest()
        helper.document = self.document
        self.assembly, self.parts = helper._make_fem_animation_model()
        import Part
        for part in self.parts:
            part.mbdItem.Shape = Part.makeBox(10, 10, 10)
        markers = []
        for index, part in enumerate(self.parts[:2]):
            marker = self.document.addObject("MbDFEM::MbDMarker", f"VideoMarker{index}")
            part.mbdItem.addMarker(marker)
            markers.append(marker)
        joint = self.document.addObject("MbDFEM::MbDJoint", "VideoJoint")
        joint.markerI, joint.markerJ = markers
        self.assembly.mbdItem.addJoint(joint)
        for prop in ("fxs", "fys", "fzs", "txs", "tys", "tzs"):
            setattr(joint, prop, [1.0, 2.0, 3.0, 4.0])
        Gui.updateGui()
        self.view = Gui.activeDocument().activeView()
        self.view.viewAxonometric()
        self.view.fitAll()
        self.sequence = {"version": 1, "width": 320, "height": 240, "fps": 10,
                         "shots": [self.shot("Motion", "motion", 1, 3),
                                   self.shot("Reactions", "motion", 1, 3),
                                   self.shot("Peak stress", "fem", 2, 2)]}
        self.sequence["shots"][1]["diagrams"] = [self.parts[0].mbdItem.Name]
        camera = self.view.getCamera()
        self.view.viewFront()
        self.sequence["shots"][1]["camera"] = self.view.getCamera()
        self.view.setCamera(camera)
        self.sequence["shots"][1]["display"][self.parts[1].mbdItem.Name]["Transparency"] = 70
        for part in self.parts:
            self.sequence["shots"][2]["display"][part.mbdItem.Name]["Visibility"] = False

    def tearDown(self):
        if hasattr(self, "document"):
            self.Gui.Control.closeDialog()
            import FreeCADMbDFreeBodyDiagram as Diagram
            Diagram.set_visible_parts(self.assembly.mbdItem, [])
            self.App.closeDocument(self.document.Name)

    def shot(self, name, mode, first, last):
        return {"name": name, "mode": mode, "first": first, "last": last,
                "duration": 0.3, "camera": self.view.getCamera(),
                "display": Video.capture_display(self.document), "diagrams": [],
                "parts": [part.Name for part in self.parts], "field": "von Mises Stress",
                "caption": True}

    @staticmethod
    def image(view, width, height):
        from PySide import QtGui
        image = QtGui.QImage(width, height, QtGui.QImage.Format_RGB32)
        image.fill(QtGui.QColor("gray"))
        return image

    def snapshot(self):
        return ([part.mbdItem.Placement.copy() for part in self.parts],
                self.view.getCamera(), Video.capture_display(self.document),
                {obj.Name for obj in self.document.Objects})

    def assert_restored(self, snapshot):
        placements, camera, display, names = snapshot
        for part, placement in zip(self.parts, placements):
            self.assertTrue(part.mbdItem.Placement.isSame(placement, 1e-9))
        # Coin normalizes the axis-angle rotation when reading a saved camera.
        numbers = r"[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?"
        before = [float(value) for value in re.findall(numbers, camera)]
        after = [float(value) for value in re.findall(numbers, self.view.getCamera())]
        self.assertEqual(len(before), len(after))
        for old, restored in zip(before, after):
            self.assertAlmostEqual(old, restored, delta=1e-5)
        self.assertEqual(Video.capture_display(self.document), display)
        self.assertEqual({obj.Name for obj in self.document.Objects}, names)
        self.assertFalse(self.document.HasPendingTransaction)
        import FreeCADMbDFreeBodyDiagram as Diagram
        self.assertEqual(Diagram.visible_parts(self.assembly.mbdItem), [])

    def test_three_shots_export_and_restore(self):
        snapshot = self.snapshot()
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(Video, "_render_frame", side_effect=self.image):
                manifest = Video.export_sequence(self.assembly, self.sequence, directory)
            self.assertEqual(manifest["status"], "complete")
            self.assertEqual(len(manifest["frames"]), 9)
            self.assertEqual([frame["shot"] for frame in manifest["frames"]], [0]*3 + [1]*3 + [2]*3)
            self.assertEqual([frame["state"] for frame in manifest["frames"]][-3:], [2, 2, 2])
            self.assertAlmostEqual(manifest["frames"][0]["time"], 0.1)
            self.assertAlmostEqual(manifest["frames"][2]["time"], 0.3)
            self.assertEqual(len(list(Path(directory).glob("*.png"))), 9)
            self.assertEqual(json.loads(Path(directory, "manifest.json").read_text())["status"], "complete")
        self.assert_restored(snapshot)

    def test_cancellation_and_render_failure_restore_the_document(self):
        for fail in (False, True):
            snapshot = self.snapshot()
            with tempfile.TemporaryDirectory() as directory:
                if fail:
                    with patch.object(Video, "_render_frame", side_effect=RuntimeError("GPU failed")):
                        with self.assertRaisesRegex(RuntimeError, "GPU failed"):
                            Video.export_sequence(self.assembly, self.sequence, directory)
                    expected = "failed"
                else:
                    with patch.object(Video, "_render_frame", side_effect=self.image):
                        manifest = Video.export_sequence(self.assembly, self.sequence, directory,
                                                         lambda done, total: done < 2)
                    self.assertEqual(len(manifest["frames"]), 2)
                    expected = "cancelled"
                self.assertEqual(json.loads(Path(directory, "manifest.json").read_text())["status"], expected)
            self.assert_restored(snapshot)

    def test_existing_files_and_missing_fem_endpoint_are_rejected(self):
        snapshot = self.snapshot()
        with tempfile.TemporaryDirectory() as directory:
            Path(directory, "keep.txt").write_text("keep")
            with self.assertRaisesRegex(ValueError, "empty output"):
                Video.export_sequence(self.assembly, self.sequence, directory)
            self.assertEqual(Path(directory, "keep.txt").read_text(), "keep")
        sequence = copy.deepcopy(self.sequence)
        sequence["shots"][2]["parts"] = ["MissingBody"]
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ValueError, "missing"):
                Video.export_sequence(self.assembly, sequence, directory)
            self.assertFalse(list(Path(directory).glob("*.png")))
        self.assert_restored(snapshot)

    def test_sequence_survives_document_save_and_reopen(self):
        Video.save_sequence(self.assembly, self.sequence)
        name = self.assembly.Name
        with tempfile.TemporaryDirectory() as directory:
            path = str(Path(directory, "Video.FCStd"))
            self.document.saveAs(path)
            self.App.closeDocument(self.document.Name)
            self.document = self.App.openDocument(path)
            self.assembly = self.document.getObject(name)
            self.assertEqual(Video.load_sequence(self.assembly), json.loads(json.dumps(self.sequence)))
            obj = Video.sequence_object(self.assembly)
            self.assertIsInstance(obj.ViewObject.Proxy, Video.VideoSequenceViewProvider)
            self.assertIn(obj, self.assembly.ViewObject.claimChildren())
            self.document.recompute()
            self.assertNotIn("Invalid", self.assembly.State)
            self.assertEqual(self.assembly.getTypeIdOfProperty("videoSequence"), "App::PropertyLinkChild")
            self.assertTrue(obj.ViewObject.Proxy.doubleClicked(obj.ViewObject))
            Video._dialog.close()

    def test_legend_position_is_stable_when_viewport_and_export_sizes_alternate(self):
        from PIL import Image, ImageChops
        import FreeCADMbDFEMAnimation as Animation
        controller = Animation.FEMAnimationController(self.assembly)
        controller.set_parts(self.parts)
        controller.prepare_display("von Mises Stress", True, 1, 3)
        for part in self.parts:
            folder_view = part.getResultsFolder().ViewObject
            folder_view.Visibility = True
            folder_view.ShowColorContour = True
            folder_view.ShowLegend = True
        bounds = []
        with tempfile.TemporaryDirectory() as directory:
            for index, state in enumerate((1, 2, 3, 1)):
                controller.show_state(state, schedule_refresh=False)
                self.Gui.updateGui()
                # The progress dialog redraws the interactive viewport between exports.
                Video._render_frame(self.view, 800, 600)
                image = Video._render_frame(self.view, 1920, 1080)
                self.assertFalse(image.isNull())
                filename = str(Path(directory) / f"legend_{index}.png")
                self.assertTrue(image.save(filename, "PNG"))
                with Image.open(filename) as frame:
                    red, green, blue = frame.convert("RGB").crop((800, 150, 1920, 320)).split()
                    mask = ImageChops.multiply(red.point(lambda v: 255 if v > 180 else 0),
                                               green.point(lambda v: 255 if v < 100 else 0))
                    mask = ImageChops.multiply(mask, blue.point(lambda v: 255 if v < 100 else 0))
                    box = mask.getbbox()
                    self.assertIsNotNone(box, "No contour legend in the rendered frame")
                    bounds.append(box)
        for box in bounds[1:]:
            self.assertEqual(box, bounds[0], bounds)

    def test_export_restores_existing_fem_datasets_and_color_ranges(self):
        import FreeCADMbDFEMAnimation as Animation
        controller = Animation.FEMAnimationController(self.assembly)
        controller.set_parts(self.parts)
        controller.prepare_display("von Mises Stress", False, 1, 1)
        controller.show_state(1, schedule_refresh=False)
        self.Gui.updateGui()
        snapshot = self.snapshot()
        before = [(part.visual.Data, part.visual.ViewObject.FixedColorBarMaximum) for part in self.parts]
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(Video, "_render_frame", side_effect=self.image):
                Video.export_sequence(self.assembly, self.sequence, directory)
        self.assert_restored(snapshot)
        for part, (data, maximum) in zip(self.parts, before):
            restored = part.visual.Data
            if data is None:
                self.assertIsNone(restored)
            else:
                # PropertyPostDataObject returns a deep copy on every Python read.
                self.assertEqual(restored.GetNumberOfPoints(), data.GetNumberOfPoints())
                self.assertEqual(restored.GetNumberOfCells(), data.GetNumberOfCells())
            self.assertEqual(part.visual.ViewObject.FixedColorBarMaximum, maximum)

    def test_real_renderer_exports_the_three_shot_sequence(self):
        from PySide import QtGui
        self.view.redraw()
        self.Gui.updateGui()
        probe = Video._render_frame(self.view, 320, 240)
        if probe.isNull():
            self.skipTest("An OpenGL context is required for the real-renderer check")
        snapshot = self.snapshot()
        with tempfile.TemporaryDirectory() as directory:
            manifest = Video.export_sequence(self.assembly, self.sequence, directory)
            self.assertEqual(manifest["status"], "complete")
            for frame in manifest["frames"]:
                image = QtGui.QImage(str(Path(directory, frame["file"])))
                self.assertFalse(image.isNull())
                self.assertEqual((image.width(), image.height()), (320, 240))
        self.assert_restored(snapshot)

    def test_dialog_captures_updates_reorders_and_saves_shots(self):
        from PySide import QtWidgets
        dialog = Video.show_dialog(self.assembly)
        try:
            self.assertFalse(dialog.isWindow())
            self.assertTrue(self.Gui.Control.activeDialog())
            self.assertTrue(self.Gui.Control.isAllowedAlterView())
            self.assertTrue(self.Gui.Control.isAllowedAlterSelection())
            self.assertIsNone(QtWidgets.QApplication.activeModalWidget())
            obj = Video.sequence_object(self.assembly)
            self.assertEqual(self.assembly.videoSequence, obj)
            self.assertIn(obj, self.assembly.Group)
            self.assertIn(obj, self.assembly.ViewObject.claimChildren())
            dialog.name.setText("Motion")
            dialog.capture()
            dialog.name.setText("Stress pause")
            dialog.mode.setCurrentIndex(dialog.mode.findData("fem"))
            dialog.first.setValue(2)
            dialog.last.setValue(2)
            dialog.capture()
            self.assertEqual(len(dialog.sequence["shots"]), 2)
            dialog.name.setText("Peak stress")
            dialog.update_shot()
            dialog.move(-1)
            self.assertEqual(dialog.sequence["shots"][0]["name"], "Peak stress")
            dialog.save()
            self.assertEqual(Video.load_sequence(self.assembly)["shots"][0]["first"], 2)
        finally:
            dialog.close()
        self.assertFalse(self.Gui.Control.activeDialog())

    def test_close_saves_settings_and_double_click_reopens_the_same_object(self):
        dialog = Video.show_dialog(self.assembly)
        obj = Video.sequence_object(self.assembly)
        dialog.capture()
        dialog.fps.setValue(24)
        dialog.width.lineEdit().setText("1280")
        self.assertTrue(dialog.close())
        self.assertEqual(obj.fps, 24)
        self.assertEqual(obj.width, 1280)
        self.assertEqual(len(Video.load_sequence(self.assembly)["shots"]), 1)
        self.assertTrue(obj.ViewObject.Proxy.doubleClicked(obj.ViewObject))
        reopened = Video._dialog
        self.assertEqual(Video.sequence_object(self.assembly), obj)
        self.assertEqual(reopened.fps.value(), 24)
        self.assertEqual(reopened.width.value(), 1280)
        self.assertTrue(reopened.close())

    def test_export_works_inside_its_own_task_panel(self):
        dialog = Video.show_dialog(self.assembly)
        snapshot = self.snapshot()
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(Video, "_render_frame", side_effect=self.image):
                manifest = Video.export_sequence(self.assembly, self.sequence, directory)
            self.assertEqual(manifest["status"], "complete")
            self.assertEqual(len(manifest["frames"]), 9)
            self.assertTrue(self.Gui.Control.activeDialog())
        self.assert_restored(snapshot)
        dialog.close()

    def test_object_property_edits_update_the_open_task_panel(self):
        dialog = Video.show_dialog(self.assembly)
        obj = Video.sequence_object(self.assembly)
        obj.fps, obj.width, obj.height = 48, 1024, 576
        self.assertEqual(dialog.fps.value(), 48)
        self.assertEqual(dialog.width.value(), 1024)
        self.assertEqual(dialog.height.value(), 576)
        dialog.close()
        self.assertEqual(Video.load_sequence(self.assembly)["fps"], 48)

    def test_video_button_encodes_sequence_inside_its_task_panel(self):
        from PySide import QtWidgets
        def encode(output, files, fps, size, progress):
            self.assertEqual(len(files), 9)
            self.assertTrue(all(filename.is_file() for filename in files))
            self.assertEqual((fps, size), (10, (320, 240)))
            self.assertTrue(progress(0, 9))
            output.write_bytes(b"encoded video")
            return True
        Video.save_sequence(self.assembly, self.sequence)
        dialog = Video.show_dialog(self.assembly)
        snapshot = self.snapshot()
        with tempfile.TemporaryDirectory() as directory, \
                patch.object(Video, "_video_dependencies"), \
                patch.object(Video, "encode_video", side_effect=encode), \
                patch("FreeCADMbDBackend.default_case_dir", return_value=Path(directory)), \
                patch.object(Video, "_render_frame", side_effect=self.image), \
                patch.object(QtWidgets.QInputDialog, "getText", return_value=("FirstVideo", True)), \
                patch.object(QtWidgets.QMessageBox, "information") as info, \
                patch.object(QtWidgets.QMessageBox, "warning") as warning:
            button = next(button for button in dialog.findChildren(QtWidgets.QPushButton)
                          if button.text() == "Export video…")
            button.click()
            warning.assert_not_called()
            info.assert_called_once()
            movie = Path(directory) / "Videos/FirstVideo/FirstVideo.mp4"
            self.assertEqual(movie.read_bytes(), b"encoded video")
            self.assertTrue(self.Gui.Control.activeDialog())
        self.assert_restored(snapshot)
        dialog.close()

    def test_unrelated_task_panel_is_preserved_and_blocks_export(self):
        from PySide import QtWidgets

        class OtherTask:
            form = QtWidgets.QWidget()

        self.Gui.Control.showDialog(OtherTask())
        with self.assertRaisesRegex(ValueError, "current task panel"):
            Video.show_dialog(self.assembly)
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ValueError, "active task panel"):
                Video.export_sequence(self.assembly, self.sequence, directory)
        self.assertTrue(self.Gui.Control.activeDialog())

    def test_mbd_sequence_is_claimed_as_an_assembly_parameter(self):
        assembly = self.assembly.mbdItem
        Video.save_sequence(assembly, self.sequence)
        obj = Video.sequence_object(assembly)
        self.assertIn(obj, assembly.Group)
        self.assertIn(obj, assembly.ViewObject.claimChildren())
        self.assertEqual(obj.getTypeIdOfProperty("VideoAssembly"), "App::PropertyLinkHidden")
        self.document.recompute()
        self.assertNotIn("Invalid", assembly.State)
        self.assertEqual(assembly.getTypeIdOfProperty("videoSequence"), "App::PropertyLinkChild")

    def test_legacy_sequence_is_reused_and_migrated(self):
        obj = self.document.addObject("App::FeaturePython", "LegacyVideoSequence")
        obj.addProperty("App::PropertyLink", "VideoAssembly", "Video")
        obj.addProperty("App::PropertyString", "SequenceJSON", "Video")
        obj.VideoAssembly = self.assembly
        obj.SequenceJSON = json.dumps(self.sequence)
        dialog = Video.show_dialog(self.assembly)
        self.assertEqual(Video.sequence_object(self.assembly), obj)
        self.assertEqual(len(dialog.sequence["shots"]), 3)
        self.assertEqual(obj.getTypeIdOfProperty("VideoAssembly"), "App::PropertyLinkHidden")
        self.assertIn(obj, self.assembly.ViewObject.claimChildren())
        dialog.close()

    def test_reopening_a_hidden_task_panel_retains_captured_shots(self):
        dialog = Video.show_dialog(self.assembly)
        dialog.capture()
        dialog.hide()
        reopened = Video.show_dialog(self.assembly)
        self.assertEqual(len(reopened.sequence["shots"]), 1)
        self.assertTrue(self.Gui.Control.activeDialog())
        reopened.close()

    def test_switching_documents_closes_the_previous_video_task_in_its_own_document(self):
        previous_document = self.document
        dialog = Video.show_dialog(self.assembly)
        dialog.capture()
        other = self.App.newDocument("OtherVideoDocument")
        try:
            assembly = other.addObject("MbDFEM::MbDAssembly", "OtherAssembly")
            assembly.times = [0.0, 0.1]
            self.Gui.setActiveDocument(other.Name)
            reopened = Video.show_dialog(assembly)
            self.assertFalse(self.Gui.Control.activeDialog(self.Gui.getDocument(previous_document.Name)))
            self.assertTrue(self.Gui.Control.activeDialog(self.Gui.getDocument(other.Name)))
            self.assertEqual(len(Video.load_sequence(self.assembly)["shots"]), 1)
            reopened.close()
        finally:
            self.App.closeDocument(other.Name)
            self.Gui.setActiveDocument(previous_document.Name)


if __name__ == "__main__":
    unittest.main()
