# SPDX-License-Identifier: LGPL-2.1-or-later

"""Synchronized playback of FEM result series belonging to one MbD assembly."""

from bisect import bisect_left
from math import isclose
from time import monotonic

import FreeCAD as App

import FreeCADMbDAnimation
import FreeCADMbDFEMResultsPanel as Results


def ensure_animation_parameters(fem_assembly):
    """Initialize saved playback defaults when the animation panel first opens."""
    parameters = fem_assembly.animationParameters
    if parameters is None:
        parameters = fem_assembly.Document.addObject(
            "MbDFEM::FEMAnimationParameters", f"{fem_assembly.Name}_AnimationParameters"
        )
        parameters.Label = "AnimationParameters"
        fem_assembly.addObject(parameters)
        fem_assembly.animationParameters = parameters
    if not parameters.isDerivedFrom("MbDFEM::FEMAnimationParameters"):
        raise ValueError("FEMAssembly animationParameters must link to FEMAnimationParameters.")
    if not parameters.settingsInitialized:
        parameters.selectedParts = [part for part in fem_assembly.parts if Results._linked_results(part)]
        mbd = getattr(fem_assembly, "mbdItem", None)
        motion_parameters = mbd.getAnimationParameters() if mbd is not None else None
        if motion_parameters is not None:
            parameters.currentFrame = motion_parameters.currentFrame
            parameters.updateRate = motion_parameters.updateRate
        parameters.settingsInitialized = True
    return parameters


class FEMAnimationController:
    """One motion timeline, with an independent FEM result pipeline per body."""

    def __init__(self, fem_assembly):
        self.fem_assembly = fem_assembly
        self.assembly = getattr(fem_assembly, "mbdItem", None)
        if self.assembly is None or not self.assembly.isDerivedFrom("MbDFEM::MbDAssembly"):
            raise ValueError("FEMAssembly has no linked MbDAssembly.")
        self.motion = FreeCADMbDAnimation.AnimationController(self.assembly)
        self.parts = []
        self.states = []
        self.current_frame = self.motion.current_frame
        self._results = {}
        self._ranges = {}
        self.field = Results._DEFAULT_PIPELINE_FIELD

    def set_parts(self, parts):
        """Index imported results and restrict playback to common, matching states."""
        indexed = {}
        selected = []
        count = self.motion.source_frame_count
        times = self.motion.result_times
        for part in parts:
            if part in selected:
                continue
            if part not in self.fem_assembly.parts:
                raise ValueError(f"{part.Label} is not a member of this FEMAssembly.")
            if Results.owning_mbd_assembly(part) != self.assembly:
                raise ValueError(f"{part.Label} does not use the assembly's MbD timeline.")
            states = {}
            for fallback, result in enumerate(Results._linked_results(part)):
                index = Results._result_state_index(result, fallback)
                if index is None or not 0 <= index < count:
                    continue
                if index in states:
                    raise ValueError(f"{part.Label} has duplicate results for state {index}.")
                result_time = getattr(result, Results._STATE_TIME_PROPERTY, None)
                if result_time is not None and not isclose(
                    float(result_time), times[index], rel_tol=1e-9, abs_tol=1e-12
                ):
                    raise ValueError(f"{part.Label} result {index} has a different simulation time.")
                states[index] = result
            indexed[part.Name] = states
            selected.append(part)
        common = set(range(count)) if selected else set()
        for states in indexed.values():
            common.intersection_update(states)
        self.parts = selected
        self._results = indexed
        self.states = sorted(common)
        self._ranges = {}

    def interval_states(self, first, last):
        return [index for index in self.states if first <= index <= last]

    def prepare_display(self, field, shared_scale, first, last, progress=None):
        """Freeze color ranges once for the selected bodies and playback interval."""
        self.field = field
        ranges = {}
        states = self.interval_states(first, last)
        total = len(self.parts) * len(states)
        completed = 0
        for part in self.parts:
            values = []
            for index in states:
                if progress is not None:
                    progress(part, index, completed, total)
                completed += 1
                if not Results._include_state_in_legend_scale(part, index):
                    continue
                value_range = Results._state_pipeline_scalar_range(part, field, index)
                if value_range is not None:
                    values.append(value_range)
            ranges[part.Name] = (
                (min(value[0] for value in values), max(value[1] for value in values))
                if values else None
            )
        available = [value for value in ranges.values() if value is not None]
        if shared_scale and available:
            combined = (min(value[0] for value in available), max(value[1] for value in available))
            ranges = dict.fromkeys(ranges, combined)
        self._ranges = ranges
        if progress is not None and self.parts and states:
            progress(self.parts[-1], states[-1], total, total)

    def show_state(self, index, schedule_refresh=True, progress=None):
        """Advance motion once, then update every selected body's FEM results."""
        if index not in self.states:
            raise ValueError(f"State {index} does not have results for every selected body.")
        if progress is not None:
            progress(f"Updating motion for FEM state {index}", 0, 0)
        self.motion.setFrame(index)
        Results._sync_fem_parts_to_mbd_parts(self.assembly, self.motion.targets)
        for position, part in enumerate(self.parts):
            if progress is not None:
                progress(f"Loading FEM state {index}\nBody: {part.Label}", position, len(self.parts))
            result = self._results[part.Name][index]
            value_range = self._ranges.get(part.Name)
            pipeline = Results._ensure_visual_pipeline(
                part, result, self.field, value_range=value_range,
                schedule_refresh=schedule_refresh
            )
            if pipeline is None:
                raise RuntimeError(f"Unable to display {part.Label} result {index}.")
            if Results._pipeline_field_name(pipeline) != self.field:
                raise ValueError(f"{part.Label} result {index} does not contain {self.field}.")
            Results.update_result_display(part, result, pipeline, value_range,
                                          schedule_refresh=schedule_refresh)
        if progress is not None:
            progress(f"Recomputing FEM state {index}", 0, 0)
        self.assembly.Document.recompute()
        self.current_frame = index
        return index


class FEMAnimationTaskPanel:
    def __init__(self, fem_assembly):
        from PySide import QtCore, QtWidgets

        self.fem_assembly = fem_assembly
        self.controller = FEMAnimationController(fem_assembly)
        self._document_name = fem_assembly.Document.Name
        self.parameters = ensure_animation_parameters(fem_assembly)
        self._updating = False
        self._observing = False
        self._playing = False
        self._closed = False
        self._accumulator = 0.0
        self._last_tick = None
        self.form = QtWidgets.QWidget()
        self.form.destroyed.connect(self._form_destroyed)
        self._timer = QtCore.QTimer(self.form)
        self._timer.timeout.connect(self._tick)
        self.form.setWindowTitle("FEM Assembly Animation")
        layout = QtWidgets.QVBoxLayout(self.form)
        layout.addWidget(QtWidgets.QLabel("Bodies to animate together:"))
        self.body_checks = []
        for part in fem_assembly.parts:
            check = QtWidgets.QCheckBox(part.Label)
            has_results = bool(Results._linked_results(part))
            check.setChecked(has_results and part in self.parameters.selectedParts)
            check.setEnabled(has_results)
            if not has_results:
                check.setText(f"{part.Label} (no imported results)")
            check.toggled.connect(self._configure)
            self.body_checks.append((part, check))
            layout.addWidget(check)
        self.status_label = QtWidgets.QLabel()
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)
        self.slider = QtWidgets.QSlider(QtCore.Qt.Horizontal)
        layout.addWidget(self.slider)
        settings = QtWidgets.QFormLayout()
        maximum = max(self.controller.motion.source_frame_count - 1, 0)
        self.frame_spin = QtWidgets.QSpinBox()
        self.first_spin = QtWidgets.QSpinBox()
        self.last_spin = QtWidgets.QSpinBox()
        for spin in (self.frame_spin, self.first_spin, self.last_spin):
            spin.setRange(0, maximum)
            spin.setKeyboardTracking(False)
        self.first_spin.setValue(1 if maximum else 0)
        self.last_spin.setValue(maximum)
        self.time_label = QtWidgets.QLabel()
        self.rate_spin = QtWidgets.QDoubleSpinBox()
        self.rate_spin.setDecimals(6)
        self.rate_spin.setRange(-1e9, 1e9)
        self.rate_spin.setToolTip("Frames per second: negative plays backward; zero pauses")
        self.rate_spin.setSuffix(" frames/sec")
        parameters = self.controller.motion._animation_parameters()
        self.rate_spin.setValue(float(getattr(parameters, "updateRate", 30)))
        self.field_combo = QtWidgets.QComboBox()
        for field in Results._PIPELINE_SCALAR_FIELD_PROPERTIES:
            self.field_combo.addItem(Results._pipeline_field_display_label(field), field)
        self.field_combo.setCurrentIndex(
            self.field_combo.findData(Results._DEFAULT_PIPELINE_FIELD)
        )
        self.shared_check = QtWidgets.QCheckBox("Shared color scale")
        self.shared_check.setToolTip("Use the same color range for all selected bodies and playback states")
        self.shared_check.setChecked(True)
        self.loop_check = QtWidgets.QCheckBox()
        self.loop_check.setChecked(True)
        settings.addRow("Current State:", self.frame_spin)
        settings.addRow("Simulation time:", self.time_label)
        settings.addRow("First State:", self.first_spin)
        settings.addRow("Last State:", self.last_spin)
        settings.addRow("Frame Rate:", self.rate_spin)
        settings.addRow("Result field:", self.field_combo)
        settings.addRow(self.shared_check)
        settings.addRow("Loop:", self.loop_check)
        layout.addLayout(settings)
        buttons = QtWidgets.QHBoxLayout()
        self.previous_button = QtWidgets.QPushButton("<")
        self.play_button = QtWidgets.QPushButton("Play")
        self.play_button.setCheckable(True)
        self.next_button = QtWidgets.QPushButton(">")
        for button in (self.previous_button, self.play_button, self.next_button):
            buttons.addWidget(button)
        layout.addLayout(buttons)
        layout.addStretch()
        self.previous_button.clicked.connect(lambda: self._step(-1))
        self.next_button.clicked.connect(lambda: self._step(1))
        self.play_button.clicked.connect(self._toggle_playback)
        self.slider.valueChanged.connect(self._slider_changed)
        self.frame_spin.valueChanged.connect(self._frame_changed)
        self.first_spin.valueChanged.connect(self._settings_changed)
        self.last_spin.valueChanged.connect(self._settings_changed)
        self.field_combo.currentIndexChanged.connect(self._settings_changed)
        self.shared_check.toggled.connect(self._settings_changed)
        self.rate_spin.valueChanged.connect(self._rate_changed)
        self.loop_check.toggled.connect(self._save_settings)
        self._load_settings()
        self._configure()
        App.addDocumentObserver(self)
        self._observing = True

    def getStandardButtons(self):
        from PySide import QtWidgets

        return QtWidgets.QDialogButtonBox.Close

    def accept(self):
        self._pause()
        self._save_settings(commit=True)
        self._remove_observer()
        return True

    def reject(self):
        return self.accept()

    def _form_destroyed(self, *args):
        # The parented timer is destroyed with the form, including programmatic closes.
        self._playing = False
        self._closed = True
        self._remove_observer()

    def _remove_observer(self):
        if self._observing:
            App.removeDocumentObserver(self)
            self._observing = False

    def _load_settings(self):
        self._updating = True
        try:
            self.first_spin.setValue(self.parameters.startFrame)
            end = self.parameters.endFrame
            self.last_spin.setValue(self.last_spin.maximum() if end < 0 else end)
            self.rate_spin.setValue(self.parameters.updateRate)
            index = self.field_combo.findData(self.parameters.fieldName)
            if index >= 0:
                self.field_combo.setCurrentIndex(index)
            self.shared_check.setChecked(self.parameters.sharedColorScale)
            self.loop_check.setChecked(self.parameters.loop)
            self.frame_spin.setValue(self.parameters.currentFrame)
            self.controller.current_frame = self.frame_spin.value()
        finally:
            self._updating = False

    def _save_settings(self, *args, commit=False):
        if self._updating or self._closed:
            return
        if commit:
            for spin in (self.frame_spin, self.first_spin, self.last_spin, self.rate_spin):
                spin.interpretText()
        self.parameters.selectedParts = [part for part, check in self.body_checks if check.isChecked()]
        self.parameters.currentFrame = self.frame_spin.value()
        self.parameters.startFrame = self.first_spin.value()
        self.parameters.endFrame = self.last_spin.value()
        self.parameters.updateRate = self.rate_spin.value()
        self.parameters.fieldName = self.field_combo.currentData()
        self.parameters.sharedColorScale = self.shared_check.isChecked()
        self.parameters.loop = self.loop_check.isChecked()

    def slotStartSaveDocument(self, document, filename):
        # Commit pending keyboard edits before the document is serialized.
        if document.Name == self._document_name:
            self._save_settings(commit=True)

    def slotDeletedDocument(self, document):
        if document.Name == self._document_name:
            self._pause()
            self._remove_observer()
            self._closed = True

    def _pause(self):
        if self._closed:
            return
        self._timer.stop()
        self._playing = False
        self._last_tick = None
        self.play_button.setChecked(False)
        self.play_button.setText("Play")

    def _set_enabled(self, enabled):
        for widget in (self.slider, self.frame_spin, self.previous_button,
                       self.next_button, self.play_button):
            widget.setEnabled(enabled)

    def _configure(self, *args):
        self._pause()
        self._set_enabled(False)
        self._save_settings()
        try:
            self.controller.set_parts([part for part, check in self.body_checks if check.isChecked()])
            self._updating = True
            try:
                self.slider.setRange(0, max(len(self.controller.states) - 1, 0))
            finally:
                self._updating = False
            count = self.controller.motion.source_frame_count
            missing = count - len(self.controller.states)
            self._summary = (
                f"{len(self.controller.parts)} bodies; {len(self.controller.states)} common states. "
                f"{missing} states unavailable for the selected bodies."
            )
            if not self.controller.parts:
                self._summary = "Select at least one body with imported FEM results."
            self.status_label.setText(self._summary)
            if not self.controller.states:
                return
            self._set_enabled(True)
            self._settings_changed()
        except Exception as exc:
            self._fail(exc)

    def _settings_changed(self, *args):
        if self._updating:
            return
        self._pause()
        self._save_settings()
        try:
            self.controller.prepare_display(
                self.field_combo.currentData(), self.shared_check.isChecked(),
                self.first_spin.value(), self.last_spin.value(),
            )
            self._show_nearest(self.controller.current_frame)
        except Exception as exc:
            self._fail(exc)

    def _show_nearest(self, index):
        states = self.controller.states
        if not states:
            return
        position = min(bisect_left(states, index), len(states) - 1)
        self._show_state(states[position])

    def _show_state(self, index):
        try:
            self.controller.show_state(index)
            self._updating = True
            try:
                self.slider.setValue(self.controller.states.index(index))
                self.frame_spin.setValue(index)
                self.time_label.setText(Results._state_time_text(self.controller.parts[0], index))
            finally:
                self._updating = False
            self.status_label.setText(self._summary)
            self._save_settings()
            return True
        except Exception as exc:
            self._fail(exc)
            return False

    def _fail(self, exc):
        self._pause()
        self.status_label.setText(str(exc))
        App.Console.PrintError(f"FEM assembly animation: {exc}\n")

    def _slider_changed(self, position):
        if not self._updating and self.controller.states:
            self._pause()
            self._show_state(self.controller.states[position])

    def _frame_changed(self, index):
        if not self._updating:
            self._pause()
            self._show_nearest(index)

    def _step(self, offset):
        self._pause()
        states = self.controller.states
        if states:
            position = min(bisect_left(states, self.controller.current_frame), len(states) - 1)
            self._show_state(states[max(0, min(position + offset, len(states) - 1))])

    def _rate_changed(self, *args):
        self._save_settings()
        self._accumulator = 0.0
        if self._playing:
            if self.rate_spin.value() == 0:
                self._pause()
            else:
                self._timer.start(max(int(1000 / abs(self.rate_spin.value())), 1))

    def _toggle_playback(self, checked):
        if not checked:
            self._pause()
            return
        for spin in (self.frame_spin, self.first_spin, self.last_spin, self.rate_spin):
            spin.interpretText()
        rate = self.rate_spin.value()
        if rate == 0:
            self._pause()
            return
        states = self.controller.interval_states(self.first_spin.value(), self.last_spin.value())
        if not states:
            self._fail(ValueError("No common solved states in the selected playback range."))
            return
        boundary = states[0] if rate < 0 else states[-1]
        if self.controller.current_frame not in states or self.controller.current_frame == boundary:
            if not self._show_state(states[-1] if rate < 0 else states[0]):
                return
        self._playing = True
        self.play_button.setChecked(True)
        self.play_button.setText("Pause")
        self._accumulator = 0.0
        self._last_tick = monotonic()
        self._timer.start(max(int(1000 / abs(rate)), 1))

    def _tick(self):
        if not self._playing:
            return
        rate = self.rate_spin.value()
        if rate == 0:
            self._pause()
            return
        now = monotonic()
        self._accumulator += max(now - self._last_tick, 0.0) * abs(rate)
        self._last_tick = now
        advance = int(self._accumulator)
        if advance < 1:
            return
        self._accumulator -= advance
        states = self.controller.interval_states(self.first_spin.value(), self.last_spin.value())
        if not states:
            self._pause()
            return
        position = states.index(self.controller.current_frame) + (-advance if rate < 0 else advance)
        if self.loop_check.isChecked():
            position %= len(states)
        else:
            position = max(0, min(position, len(states) - 1))
        self._show_state(states[position])
        if not self.loop_check.isChecked() and position == (0 if rate < 0 else len(states) - 1):
            self._pause()


def show_animation_task_panel(fem_assembly):
    import FreeCADGui as Gui

    if Gui.Control.activeDialog():
        Gui.Control.closeDialog()
    panel = FEMAnimationTaskPanel(fem_assembly)
    Gui.Control.showDialog(panel)
    return panel


def show_parameters_task_panel(parameters):
    for obj in parameters.Document.Objects:
        if obj.isDerivedFrom("MbDFEM::FEMAssembly") and obj.animationParameters == parameters:
            return show_animation_task_panel(obj)
    raise ValueError("No owning FEMAssembly found for these animation parameters.")


class AnimateFEMResultsCommand:
    def GetResources(self):
        return {
            "MenuText": "Animate FEM Results",
            "ToolTip": "Animate selected FEM bodies together on their shared MbD timeline",
        }

    @staticmethod
    def active_assembly():
        import FreeCADGui as Gui

        document = App.ActiveDocument
        if document is None:
            return None
        for obj in Gui.Selection.getSelection():
            if obj.isDerivedFrom("MbDFEM::FEMAssembly"):
                return obj
            for assembly in document.Objects:
                if assembly.isDerivedFrom("MbDFEM::FEMAssembly") and (
                    obj in assembly.parts or obj == assembly.animationParameters
                ):
                    return assembly
        assemblies = [obj for obj in document.Objects if obj.isDerivedFrom("MbDFEM::FEMAssembly")]
        return assemblies[0] if len(assemblies) == 1 else None

    def IsActive(self):
        return self.active_assembly() is not None

    def Activated(self):
        assembly = self.active_assembly()
        if assembly is None:
            App.Console.PrintError("Select an FEMAssembly to animate its results.\n")
            return
        try:
            show_animation_task_panel(assembly)
        except Exception as exc:
            App.Console.PrintError(f"FEM assembly animation: {exc}\n")
