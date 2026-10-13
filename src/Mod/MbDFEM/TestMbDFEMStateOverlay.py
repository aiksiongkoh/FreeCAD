# SPDX-License-Identifier: LGPL-2.1-or-later

import unittest
from sys import float_info
from types import SimpleNamespace

import FreeCAD as App
import MbDFEM  # noqa: F401
import FreeCADMbDAnimation
import FreeCADMbDFEMStateOverlay as Overlay


class StateOverlayTest(unittest.TestCase):
    def setUp(self):
        self.document = App.newDocument("StateOverlayTest")
        self.assembly = self.document.addObject("MbDFEM::MbDAssembly", "Assembly")
        self.part = self.document.addObject("MbDFEM::MbDPart", "Part")
        self.assembly.addPart(self.part)
        self.parameters = self.assembly.ensureAnimationParameters()
        if App.GuiUp:
            import FreeCADGui as Gui

            Gui.setActiveDocument(self.document.Name)
            Gui.updateGui()

    def tearDown(self):
        App.closeDocument(self.document.Name)

    def populate(self, count=120):
        self.assembly.times = [index * 0.01 for index in range(count)]
        for name in ("xs", "ys", "zs"):
            setattr(self.part, name, [0.0] * count)

    def test_text_color_uses_the_higher_contrast(self):
        self.assertEqual(Overlay.contrasting_text_color((1, 1, 1)), (0, 0, 0))
        self.assertEqual(Overlay.contrasting_text_color((0, 0, 0)), (1, 1, 1))
        self.assertEqual(Overlay.contrasting_text_color((0.8, 0.8, 0.8)), (0, 0, 0))
        self.assertEqual(Overlay.contrasting_text_color((0.1, 0.1, 0.1)), (1, 1, 1))

    def test_unavailable_render_keeps_the_last_visible_color(self):
        overlay = Overlay.ViewOverlay.__new__(Overlay.ViewOverlay)
        overlay._next_color_check = 0
        overlay._foreground = (0, 0, 0)
        viewer = SimpleNamespace(renderToImage=lambda **kwargs:
                                 SimpleNamespace(isNull=lambda: True))
        overlay.view = SimpleNamespace(getViewer=lambda: viewer)
        self.assertFalse(overlay._update_color())
        self.assertEqual(overlay._foreground, (0, 0, 0))

    def test_state_and_time_match_saved_zero_based_frame(self):
        self.populate()
        self.parameters.currentFrame = 24
        self.assertEqual(Overlay.state_text(self.assembly),
                         "State 24 / 120 · t = 0.240 s")

    def test_empty_and_incomplete_series(self):
        self.assertEqual(Overlay.state_text(self.assembly), "State — / — · t = — s")
        self.populate()
        self.part.zs = [0.0] * 10
        self.parameters.currentFrame = 24
        self.assertEqual(Overlay.state_text(self.assembly), "State 9 / 10 · t = 0.090 s")

    def test_asmt_input_configuration_has_no_timestamp(self):
        self.populate(3)
        self.assembly.times = [-float_info.max, 0.0, 0.01]
        self.assertEqual(Overlay.state_text(self.assembly),
                         "State 0 / 3 · t = — s (Input)")
        controller = FreeCADMbDAnimation.AnimationController(self.assembly)
        self.assertEqual(Overlay.state_text(self.assembly,
                                          (controller.current_frame, controller.current_time)),
                         "State 0 / 3 · t = — s (Input)")
        controller.setFrame(1)
        self.assertEqual(Overlay.state_text(self.assembly), "State 1 / 3 · t = 0.000 s")
        self.assertEqual(self.assembly.times[0], -float_info.max)

    def test_invalid_and_large_times_stay_compact(self):
        self.populate(1)
        for seconds, label in ((float("nan"), "—"), (float("inf"), "—"),
                               (-float("inf"), "—"), (1e100, "1.000e+100")):
            with self.subTest(seconds=seconds):
                self.assertEqual(Overlay.state_text(self.assembly, (0, seconds)),
                                 f"State 0 / 1 · t = {label} s")

    def test_interpolated_time_and_frame_are_kept_together(self):
        self.populate(3)
        self.parameters.startFrame = 0
        controller = FreeCADMbDAnimation.AnimationController(self.assembly)
        controller.setTime(0.015)
        self.assertEqual(self.parameters.currentFrame, controller.current_frame)
        self.assertEqual(Overlay.state_text(self.assembly,
                                          (controller.current_frame, controller.current_time)),
                         f"State {controller.current_frame} / 3 · t = 0.015 s")

    def test_live_state_without_saved_animation_parameters(self):
        self.populate()
        self.document.removeObject(self.parameters.Name)
        self.assertIsNone(self.assembly.getAnimationParameters())
        controller = FreeCADMbDAnimation.AnimationController(self.assembly)
        controller.setFrame(24)
        self.assertEqual(Overlay.state_text(self.assembly,
                                          (controller.current_frame, controller.current_time)),
                         "State 24 / 120 · t = 0.240 s")

    @unittest.skipUnless(App.GuiUp, "Requires the FreeCAD GUI")
    def test_overlay_adapts_to_background_changes_without_a_frame_change(self):
        import FreeCADGui as Gui
        from PySide import QtCore

        self.populate()
        Overlay.install()
        view = Gui.activeDocument().activeView()
        overlay = Overlay._manager.overlays[self.document.Name][view]
        viewer = view.getViewer()
        for background, expected in (((1, 1, 1), (0, 0, 0)),
                                     ((0.05, 0.05, 0.05), (1, 1, 1))):
            with self.subTest(background=background):
                viewer.setBackgroundColor(*background)
                viewer.setGradientBackground("NONE")
                # Exercise the production timer; do not force a color refresh.
                loop = QtCore.QEventLoop()
                QtCore.QTimer.singleShot(1400, loop.quit)
                loop.exec()
                self.assertEqual(overlay._foreground, expected)
        # A light gradient can cover a dark clear color. Detect the gradient,
        # not the render manager's underlying solid background.
        viewer.setGradientBackgroundColor((1, 1, 1), (0.2, 0.2, 0.2))
        viewer.setGradientBackground("LINEAR")
        loop = QtCore.QEventLoop()
        QtCore.QTimer.singleShot(1400, loop.quit)
        loop.exec()
        self.assertEqual(overlay._foreground, (0, 0, 0))

    @unittest.skipUnless(App.GuiUp, "Requires the FreeCAD GUI")
    def test_overlay_updates_survives_camera_changes_and_cleans_up(self):
        import FreeCADGui as Gui

        self.populate()
        Overlay.install()
        controller = FreeCADMbDAnimation.AnimationController(self.assembly)
        controller.setFrame(24)
        view = Gui.activeDocument().activeView()
        overlay = Overlay._manager.overlays[self.document.Name][view]
        self.assertEqual(overlay._text, "State 24 / 120 · t = 0.240 s")
        view.viewTop()
        view.fitAll()
        self.assertEqual(overlay._text, "State 24 / 120 · t = 0.240 s")
        controller.setFrame(25)
        self.assertEqual(overlay._text, "State 25 / 120 · t = 0.250 s")
        Overlay.install()
        self.assertEqual(len(Overlay._manager.overlays[self.document.Name]), 1)
        name = self.document.Name
        App.closeDocument(name)
        self.assertNotIn(name, Overlay._manager.overlays)
        self.document = App.newDocument("StateOverlayTestCleanup")
