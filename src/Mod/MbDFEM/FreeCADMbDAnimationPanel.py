# SPDX-License-Identifier: LGPL-2.1-or-later

"""Task panel for MbDFEM animation playback controls."""

import FreeCAD as App
import FreeCADGui as Gui

import FreeCADMbDAnimation


def owning_assembly(animation_parameters):
    """Return the MbDAssembly that owns *animation_parameters*."""
    document = getattr(animation_parameters, "Document", None)
    if document is None:
        return None

    for obj in document.Objects:
        try:
            if obj.isDerivedFrom("MbDFEM::MbDAssembly") and obj.getAnimationParameters() == animation_parameters:
                return obj
        except Exception:
            pass
    return None


def is_animation_parameters(obj):
    try:
        return obj is not None and obj.isDerivedFrom("MbDFEM::MbDAnimationParameters")
    except Exception:
        return False


class AnimationTaskPanel:
    """Task-tab controls for an MbDAnimationParameters object."""

    def __init__(self, animation_parameters):
        from PySide import QtCore, QtWidgets

        self.animation_parameters = animation_parameters
        self.assembly = owning_assembly(animation_parameters)
        self.controller = (
            FreeCADMbDAnimation.AnimationController(self.assembly) if self.assembly is not None else None
        )
        self._original_parameters = self._parameter_values()
        self._updating = False
        self._timer = QtCore.QTimer()
        self._timer.timeout.connect(self._tick)

        self.form = QtWidgets.QWidget()
        self.form.setWindowTitle("MbDFEM Animation")

        layout = QtWidgets.QVBoxLayout(self.form)
        layout.setSpacing(8)

        self.status_label = QtWidgets.QLabel()
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)

        button_layout = QtWidgets.QHBoxLayout()
        self.step_back_button = QtWidgets.QToolButton()
        self.step_back_button.setText("<")
        self.step_back_button.setToolTip("Step backward")
        self.play_button = QtWidgets.QToolButton()
        self.play_button.setText("Play")
        self.play_button.setToolTip("Play")
        self.play_button.setCheckable(True)
        self.input_button = QtWidgets.QToolButton()
        self.input_button.setText("Input")
        self.input_button.setToolTip("Pause at input frame")
        self.first_button = QtWidgets.QToolButton()
        self.first_button.setText("First")
        self.first_button.setToolTip("Pause at first frame")
        self.last_button = QtWidgets.QToolButton()
        self.last_button.setText("Last")
        self.last_button.setToolTip("Pause at last frame")
        self.step_forward_button = QtWidgets.QToolButton()
        self.step_forward_button.setText(">")
        self.step_forward_button.setToolTip("Step forward")

        for button in (
            self.step_back_button,
            self.play_button,
            self.input_button,
            self.first_button,
            self.last_button,
            self.step_forward_button,
        ):
            button_layout.addWidget(button)
        layout.addLayout(button_layout)

        self.slider = QtWidgets.QSlider(QtCore.Qt.Horizontal)
        layout.addWidget(self.slider)

        frame_layout = QtWidgets.QHBoxLayout()
        frame_layout.addWidget(QtWidgets.QLabel("Current Frame:"))
        self.frame_spin = QtWidgets.QSpinBox()
        self.frame_spin.setToolTip("Current result-series frame index")
        frame_layout.addWidget(self.frame_spin)
        self.frame_count_label = QtWidgets.QLabel()
        frame_layout.addWidget(self.frame_count_label)
        frame_layout.addStretch()
        frame_layout.addWidget(QtWidgets.QLabel("Simulation time:"))
        self.time_label = QtWidgets.QLabel()
        frame_layout.addWidget(self.time_label)
        layout.addLayout(frame_layout)

        settings = QtWidgets.QFormLayout()
        self.update_rate_spin = QtWidgets.QSpinBox()
        self.update_rate_spin.setRange(1, 240)
        self.update_rate_spin.setSuffix(" frames/sec")
        self.update_rate_spin.setToolTip("Simulation frames per real second")
        self.start_frame_spin = QtWidgets.QSpinBox()
        self.start_frame_spin.setToolTip("First result-series frame index used for playback")
        self.end_frame_spin = QtWidgets.QSpinBox()
        self.end_frame_spin.setToolTip("Last result-series frame index used for playback")
        self.speed_spin = QtWidgets.QDoubleSpinBox()
        self.speed_spin.setRange(0.0, 1000000.0)
        self.speed_spin.setDecimals(2)
        self.speed_spin.setSingleStep(0.25)
        self.speed_spin.setSuffix("x")
        self.speed_spin.setToolTip("Simulation seconds per real second from the selected frame rate")
        self.speed_spin.setReadOnly(True)
        self.speed_spin.setButtonSymbols(QtWidgets.QAbstractSpinBox.NoButtons)
        self.skipped_spin = QtWidgets.QSpinBox()
        self.skipped_spin.setRange(0, 2147483647)
        self.skipped_spin.setReadOnly(True)
        self.skipped_spin.setButtonSymbols(QtWidgets.QAbstractSpinBox.NoButtons)
        self.skipped_spin.setToolTip("Simulation frames skipped because display could not keep up")
        self.scale_spin = QtWidgets.QDoubleSpinBox()
        self.scale_spin.setRange(0.001, 1000000.0)
        self.scale_spin.setDecimals(3)
        self.scale_spin.setSingleStep(100.0)
        self.loop_check = QtWidgets.QCheckBox()
        settings.addRow("Frame Rate:", self.update_rate_spin)
        settings.addRow("First Frame:", self.start_frame_spin)
        settings.addRow("Last Frame:", self.end_frame_spin)
        settings.addRow("Playback speed:", self.speed_spin)
        settings.addRow("Frames Skipped:", self.skipped_spin)
        settings.addRow("Position scale:", self.scale_spin)
        settings.addRow("Loop:", self.loop_check)
        layout.addLayout(settings)

        self.step_back_button.clicked.connect(self._step_backward)
        self.play_button.clicked.connect(self._toggle_playback)
        self.input_button.clicked.connect(self._input_frame)
        self.first_button.clicked.connect(self._first_frame)
        self.last_button.clicked.connect(self._last_frame)
        self.step_forward_button.clicked.connect(self._step_forward)
        self.slider.valueChanged.connect(self._set_frame)
        self.frame_spin.valueChanged.connect(self._set_frame)
        self.update_rate_spin.valueChanged.connect(self._set_update_rate)
        self.start_frame_spin.valueChanged.connect(self._set_start_frame)
        self.end_frame_spin.valueChanged.connect(self._set_end_frame)
        self.scale_spin.valueChanged.connect(self._set_scale)
        self.loop_check.toggled.connect(self._set_loop)

        self._load_parameters()
        self._configure_frame_controls()
        self._refresh()

    def getStandardButtons(self):
        from PySide import QtGui

        return QtGui.QDialogButtonBox.Ok | QtGui.QDialogButtonBox.Cancel

    def accept(self):
        self._pause()
        self._apply_parameters()
        return True

    def reject(self):
        self._pause()
        self._restore_parameters(self._original_parameters)
        return True

    def _parameter_values(self):
        return {
            "updateRate": getattr(self.animation_parameters, "updateRate", 30),
            "currentFrame": getattr(self.animation_parameters, "currentFrame", 0),
            "startFrame": getattr(self.animation_parameters, "startFrame", 1),
            "endFrame": getattr(self.animation_parameters, "endFrame", -1),
            "playbackSpeed": getattr(self.animation_parameters, "playbackSpeed", 1.0),
            "showTrails": getattr(self.animation_parameters, "showTrails", False),
            "trailLength": getattr(self.animation_parameters, "trailLength", 60),
            "loop": getattr(self.animation_parameters, "loop", True),
            "lengthScale": getattr(self.animation_parameters, "lengthScale", None),
        }

    def _restore_parameters(self, values):
        self.animation_parameters.updateRate = values["updateRate"]
        self.animation_parameters.currentFrame = values["currentFrame"]
        self.animation_parameters.startFrame = values["startFrame"]
        self.animation_parameters.endFrame = values["endFrame"]
        self.animation_parameters.playbackSpeed = values["playbackSpeed"]
        self.animation_parameters.showTrails = values["showTrails"]
        self.animation_parameters.trailLength = values["trailLength"]
        self.animation_parameters.loop = values["loop"]
        if values["lengthScale"] is not None:
            self.animation_parameters.lengthScale = values["lengthScale"]
        if self.controller is not None and values["lengthScale"] is not None:
            self.controller.length_scale = values["lengthScale"]
            self.controller.setFrame(values["currentFrame"])

    def _apply_parameters(self):
        for spin_box in (
            self.frame_spin,
            self.update_rate_spin,
            self.start_frame_spin,
            self.end_frame_spin,
            self.scale_spin,
        ):
            spin_box.interpretText()

        start_frame = int(self.start_frame_spin.value())
        end_frame = max(int(self.end_frame_spin.value()), start_frame)
        self.animation_parameters.updateRate = int(self.update_rate_spin.value())
        self.animation_parameters.startFrame = start_frame
        self.animation_parameters.endFrame = end_frame
        self.animation_parameters.lengthScale = float(self.scale_spin.value())
        self.animation_parameters.loop = bool(self.loop_check.isChecked())
        if self.controller is not None:
            self.controller.length_scale = float(self.scale_spin.value())
            self.animation_parameters.playbackSpeed = float(self.controller.playback_speed)
            self.controller.setFrame(self.frame_spin.value())
        else:
            self.animation_parameters.playbackSpeed = float(self.speed_spin.value())
            self.animation_parameters.currentFrame = int(self.frame_spin.value())

    def _load_parameters(self):
        self._updating = True
        try:
            self.update_rate_spin.setValue(
                int(
                    getattr(
                        self.animation_parameters,
                        "updateRate",
                        30,
                    )
                )
            )
            self.speed_spin.setValue(
                float(self.controller.playback_speed)
                if self.controller is not None
                else float(getattr(self.animation_parameters, "playbackSpeed", 0.0))
            )
            self.scale_spin.setValue(float(getattr(self.animation_parameters, "lengthScale", 1.0)))
            self.loop_check.setChecked(bool(getattr(self.animation_parameters, "loop", True)))
        finally:
            self._updating = False

    def _configure_frame_controls(self):
        source_frame_count = self.controller.source_frame_count if self.controller is not None else 0
        maximum = max(source_frame_count - 1, 0)
        start_frame = self.controller.start_frame if self.controller is not None else 0
        end_frame = self.controller.end_frame if self.controller is not None else 0

        self._updating = True
        try:
            self.start_frame_spin.setRange(0, maximum)
            self.end_frame_spin.setRange(0, maximum)
            self.start_frame_spin.setValue(start_frame)
            self.end_frame_spin.setValue(end_frame)
            self.slider.setRange(0, maximum)
            self.frame_spin.setRange(0, maximum)
        finally:
            self._updating = False

        enabled = source_frame_count > 0
        for widget in (
            self.step_back_button,
            self.play_button,
            self.input_button,
            self.first_button,
            self.last_button,
            self.step_forward_button,
            self.slider,
            self.frame_spin,
            self.start_frame_spin,
            self.end_frame_spin,
        ):
            widget.setEnabled(enabled)

    def _refresh(self):
        source_frame_count = self.controller.source_frame_count if self.controller is not None else 0
        if self.assembly is None:
            self.status_label.setText("No owning MbDAssembly found.")
        elif source_frame_count == 0:
            self.status_label.setText("No solved MbDFEM result series.")
        else:
            self.status_label.setText(self.assembly.Label)

        current_frame = self.controller.current_frame if self.controller is not None else 0
        current_time = self.controller.current_time if self.controller is not None else 0.0
        last_time = self.controller.times[-1] if self.controller is not None and self.controller.times else 0.0
        playback_speed = self.controller.playback_speed if self.controller is not None else 0.0
        frames_skipped = self.controller.frames_skipped if self.controller is not None else 0
        self._updating = True
        try:
            self.slider.setValue(current_frame)
            self.frame_spin.setValue(current_frame)
            self.speed_spin.setValue(float(playback_speed))
            self.skipped_spin.setValue(int(frames_skipped))
            playing = bool(self.controller is not None and self.controller.is_playing)
            self.play_button.setChecked(playing)
            self.play_button.setText("Pause" if playing else "Play")
            self.play_button.setToolTip("Pause" if playing else "Play")
        finally:
            self._updating = False
        maximum = max(source_frame_count - 1, 0)
        self.frame_count_label.setText(f"/ {maximum}")
        self.time_label.setText(f"{current_time:.6g} / {last_time:.6g} s")

    def _toggle_playback(self, checked=False):
        if checked:
            self._play()
        else:
            self._pause()

    def _play(self):
        if self.controller is None or self.controller.frame_count == 0:
            self._refresh()
            return
        if self.controller.current_frame < self.controller.start_frame or self.controller.current_frame > self.controller.end_frame:
            self.controller.setFrame(self.controller.start_frame)
        interval = max(int(1000.0 / self.controller.frame_rate), 1)
        self.controller.beginPlayback()
        self._timer.start(interval)
        self._refresh()

    def _pause(self):
        self._timer.stop()
        if self.controller is not None:
            self.controller.pause()
        self._refresh()

    def _input_frame(self):
        self._pause()
        if self.controller is not None:
            self.controller.setFrame(0)
        self._refresh()

    def _first_frame(self):
        self._pause()
        if self.controller is not None:
            self.controller.stop()
        self._refresh()

    def _last_frame(self):
        self._pause()
        if self.controller is not None:
            self.controller.setFrame(self.controller.end_frame)
        self._refresh()

    def _tick(self):
        if self.controller is None:
            return
        self.controller.tick()
        if not self.controller.is_playing:
            self._timer.stop()
        self._refresh()

    def _step_forward(self):
        if self.controller is not None:
            self.controller.stepForward()
        self._refresh()

    def _step_backward(self):
        if self.controller is not None:
            self.controller.stepBackward()
        self._refresh()

    def _set_frame(self, frame):
        if self._updating or self.controller is None:
            return
        self.controller.setFrame(frame)
        self._refresh()

    def _set_update_rate(self, value):
        if self._updating:
            return
        self.animation_parameters.updateRate = int(value)
        if self._timer.isActive():
            self._play()

    def _set_start_frame(self, value):
        if self._updating or self.controller is None:
            return
        self.animation_parameters.startFrame = int(value)
        if int(getattr(self.animation_parameters, "endFrame", -1)) >= 0:
            self.animation_parameters.endFrame = max(int(self.animation_parameters.endFrame), int(value))
        self._configure_frame_controls()
        self._refresh()

    def _set_end_frame(self, value):
        if self._updating or self.controller is None:
            return
        self.animation_parameters.endFrame = max(int(value), self.controller.start_frame)
        self._configure_frame_controls()
        self._refresh()

    def _set_scale(self, value):
        self.animation_parameters.lengthScale = float(value)
        if self.controller is not None:
            self.controller.length_scale = float(value)
            self.controller.setFrame(self.controller.current_frame)
        self._refresh()

    def _set_loop(self, checked):
        if not self._updating:
            self.animation_parameters.loop = bool(checked)


def show_animation_task_panel(animation_parameters):
    active = Gui.Control.activeDialog()
    if isinstance(active, AnimationTaskPanel):
        if active.animation_parameters == animation_parameters:
            return active
        Gui.Control.closeDialog()
    elif active is not None:
        Gui.Control.closeDialog()

    panel = AnimationTaskPanel(animation_parameters)
    Gui.Control.showDialog(panel)
    return panel
