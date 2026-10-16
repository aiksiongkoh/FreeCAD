# SPDX-License-Identifier: LGPL-2.1-or-later

"""Persistent, screen-space state/time indicator for MbDFEM 3D views."""

from math import isfinite
from sys import float_info
from time import monotonic

import FreeCAD as App


def state_text(assembly, sample=None):
    """Read the saved state without applying placements or recomputing the model."""
    times = assembly.times
    counts = [len(times)] if times else []
    for part in list(assembly.parts) + list(assembly.fixedparts):
        for name in ("xs", "ys", "zs"):
            values = getattr(part, name, [])
            if values:
                counts.append(len(values))
    count = min(counts) if counts else 0
    if not count:
        return "State — / — · t = — s"
    parameters = assembly.getAnimationParameters()
    frame = int(parameters.currentFrame) if parameters else (sample[0] if sample else 0)
    frame = max(0, min(frame, count - 1))
    rate = max(abs(float(parameters.updateRate)), 1.0) if parameters else 30.0
    seconds = float(times[frame]) if times else frame / rate
    if sample is not None and sample[0] == frame:
        seconds = sample[1]
    # ASMT's Input configuration has no simulation time. The importer preserves
    # it as -DBL_MAX so it remains distinct from the following t=0 state.
    is_input = seconds == -float_info.max
    if is_input or not isfinite(seconds):
        time_label = "—"
    elif abs(seconds) >= 1e6:
        time_label = f"{seconds:.3e}"
    else:
        time_label = f"{seconds:.3f}"
    suffix = " (Input)" if is_input else ""
    return f"State {frame} / {count - 1} · t = {time_label} s{suffix}"


def contrasting_text_color(rgb):
    """Choose black or white by their contrast with the sampled sRGB color."""
    linear = [value / 12.92 if value <= 0.04045
              else ((value + 0.055) / 1.055) ** 2.4 for value in rgb]
    luminance = sum(value * weight for value, weight in
                    zip(linear, (0.2126, 0.7152, 0.0722)))
    black_contrast = (luminance + 0.05) / 0.05
    white_contrast = 1.05 / (luminance + 0.05)
    return (0, 0, 0) if black_contrast >= white_contrast else (1, 1, 1)


class ViewOverlay:
    """A renderer superimposition, independent of the model camera and picking."""

    def __init__(self, view):
        from pivy import coin

        self.view = view
        self.render = view.getViewer().getSoRenderManager()
        self.root = coin.SoSeparator()
        camera = coin.SoOrthographicCamera()
        camera.aspectRatio = 1
        camera.viewportMapping = coin.SoCamera.LEAVE_ALONE
        self.root.addChild(camera)
        self.translation = coin.SoTranslation()
        self.root.addChild(self.translation)
        font = coin.SoFont()
        font.name = "Arial,FreeSans,sans"
        font.size = 16
        self.root.addChild(font)
        self.color = coin.SoBaseColor()
        self.color.rgb = (0, 0, 0)
        self.root.addChild(self.color)
        self.text = coin.SoText2()
        self.text.justification = coin.SoText2.LEFT
        self.root.addChild(self.text)
        self.handle = self.render.addSuperimposition(self.root)
        self._text = None
        self._viewport_size = None
        self._foreground = None
        self._next_color_check = 0.0

    def _update_color(self):
        now = monotonic()
        if now < self._next_color_check:
            return False
        self._next_color_check = now + 1.0
        viewer = self.view.getViewer()
        # The live framebuffer can be stale (or blank) when sampled by a timer.
        # Render a small fresh image instead; it also excludes our own text.
        image = viewer.renderToImage(width=128, height=128, samples=0)
        if image.isNull():
            # Keep the last usable color until the view can render. The clear
            # color alone is misleading when a gradient covers it.
            return False
        # Sample above the glyphs, never the overlay itself. Reading the
        # actual viewport also handles gradients and per-view overrides.
        colors = [image.pixelColor(x, 1) for x in (1, 5, 10)]
        rgb = tuple(sum(getattr(color, channel)() for color in colors) / len(colors)
                    for channel in ("redF", "greenF", "blueF"))
        foreground = contrasting_text_color(rgb)
        if foreground == self._foreground:
            return False
        self.color.rgb = foreground
        self._foreground = foreground
        return True

    def update(self, text):
        size = self.render.getViewportRegion().getViewportSizePixels()
        viewport_size = (max(int(size[0]), 1), max(int(size[1]), 1))
        changed = viewport_size != self._viewport_size
        if changed:
            width, height = viewport_size
            # Keep the text 12 pixels from the left edge at every view size.
            self.translation.translation = (-1 + 24 / width, 1 - 56 / height, 0)
            self._viewport_size = viewport_size
        if text != self._text:
            self.text.string = text
            self._text = text
            changed = True
        changed = self._update_color() or changed
        if changed:
            self.view.redraw()

    def remove(self):
        self.render.removeSuperimposition(self.handle)
        self.view.redraw()


class StateOverlayManager:
    def __init__(self):
        import FreeCADGui as Gui
        from PySide import QtCore

        self.overlays = {}
        self.assemblies = {}
        self.samples = {}
        self.timer = QtCore.QTimer(Gui.getMainWindow())
        self.timer.setInterval(200)
        self.timer.timeout.connect(self.refresh)
        # Polling also discovers newly opened views and restored documents.
        self.timer.start()
        App.addDocumentObserver(self)

    def slotDeletedDocument(self, document):
        # The viewer is being destroyed: do not dereference its render manager.
        self.overlays.pop(document.Name, None)
        self.assemblies.pop(document.Name, None)
        self.samples.pop(document.Name, None)

    def slotChangedObject(self, obj, prop):
        if prop in {"times", "currentFrame", "xs", "ys", "zs"}:
            self.samples.pop(obj.Document.Name, None)

    def show_state(self, controller):
        document = getattr(controller.assembly, "Document", None)
        if document is None:
            return
        self.assemblies[document.Name] = controller.assembly.Name
        self.samples[document.Name] = (controller.current_frame, controller.current_time)
        self.refresh()

    def refresh(self):
        import FreeCADGui as Gui

        document = App.ActiveDocument
        for name in list(self.overlays):
            if App.getDocument(name) is None:
                self.overlays.pop(name, None)
        if document is None:
            return
        gui_document = Gui.getDocument(document.Name)
        if gui_document is None:
            return
        views = gui_document.mdiViewsOfType("Gui::View3DInventor")
        # Drop closed views without accessing their now-invalid render managers.
        overlays = self.overlays.setdefault(document.Name, {})
        for view in list(overlays):
            if view not in views:
                del overlays[view]
        assembly = document.getObject(self.assemblies.get(document.Name, ""))
        if assembly is None or not assembly.isDerivedFrom("MbDFEM::MbDAssembly"):
            self.samples.pop(document.Name, None)
            assembly = next((obj for obj in document.Objects
                             if obj.isDerivedFrom("MbDFEM::MbDAssembly")), None)
        if assembly is None:
            for overlay in overlays.values():
                overlay.remove()
            overlays.clear()
            return
        text = state_text(assembly, self.samples.get(document.Name))
        for view in views:
            if view not in overlays:
                overlays[view] = ViewOverlay(view)
            overlays[view].update(text)


_manager = None


def install():
    global _manager
    if App.GuiUp and _manager is None:
        _manager = StateOverlayManager()
    if _manager is not None:
        _manager.refresh()


def update(controller):
    """Called after both discrete frame changes and interpolated playback."""
    if not App.GuiUp:
        return
    install()
    _manager.show_state(controller)
