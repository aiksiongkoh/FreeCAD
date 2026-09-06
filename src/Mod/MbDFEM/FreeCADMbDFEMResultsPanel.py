# SPDX-License-Identifier: LGPL-2.1-or-later

"""Task panel for solving FEMPart result states over an MbD time series."""

import FreeCAD as App

import FreeCADMbDAnimation
import FreeCADMbDBackend
import FreeCADMbDFEMEmbedded


_STATE_INDEX_PROPERTY = "MbDFEMStateIndex"
_STATE_TIME_PROPERTY = "MbDFEMStateTime"
_DEFAULT_PIPELINE_FIELD = "von Mises Stress"


def owning_fem_part(results_folder):
    document = getattr(results_folder, "Document", None)
    if document is None:
        return None

    for obj in getattr(document, "Objects", []):
        try:
            if obj.isDerivedFrom("MbDFEM::FEMPart") and obj.getResultsFolder() == results_folder:
                return obj
        except Exception:
            pass
    return None


def owning_mbd_assembly(fem_part):
    mbd_part = getattr(fem_part, "mbdItem", None)
    document = getattr(fem_part, "Document", None)
    if document is None or mbd_part is None:
        return None

    for obj in getattr(document, "Objects", []):
        try:
            if not obj.isDerivedFrom("MbDFEM::MbDAssembly"):
                continue
            if mbd_part in list(getattr(obj, "parts", [])) or mbd_part in list(
                getattr(obj, "fixedparts", [])
            ):
                return obj
        except Exception:
            pass
    return None


def state_count(fem_part):
    assembly = owning_mbd_assembly(fem_part)
    if assembly is None:
        return 0

    counts = []
    times = list(getattr(assembly, "times", []))
    if times:
        counts.append(len(times))

    mbd_part = getattr(fem_part, "mbdItem", None)
    if mbd_part is not None:
        for name in ("xs", "ys", "zs", "bryxs", "bryys", "bryzs"):
            values = list(getattr(mbd_part, name, []))
            if values:
                counts.append(len(values))

    return min(counts) if counts else 0


def apply_state(fem_part, state_index):
    assembly = owning_mbd_assembly(fem_part)
    if assembly is None:
        raise ValueError("No owning MbDAssembly found for FEMPart.")

    controller = FreeCADMbDAnimation.AnimationController(assembly)
    if state_index < 0 or state_index >= controller.source_frame_count:
        raise IndexError("MbD state index not in range.")

    controller.setFrame(state_index)
    _sync_fem_parts_to_mbd_parts(assembly, controller.targets)
    return assembly


def _sync_fem_parts_to_mbd_parts(assembly, mbd_parts):
    document = getattr(assembly, "Document", None)
    if document is None:
        return

    mbd_parts = [part for part in mbd_parts if part is not None]
    for obj in getattr(document, "Objects", []):
        try:
            if not obj.isDerivedFrom("MbDFEM::FEMPart"):
                continue
            mbd_part = getattr(obj, "mbdItem", None)
            if mbd_part in mbd_parts:
                obj.Placement = App.Placement(mbd_part.Placement)
        except Exception:
            pass
    document.recompute()


def _linked_results(fem_part):
    return FreeCADMbDFEMEmbedded._linked_results(fem_part)


def _result_state_index(result, fallback_index=None):
    try:
        return int(getattr(result, _STATE_INDEX_PROPERTY))
    except Exception:
        return fallback_index


def _result_for_state(fem_part, state_index, base_results=None):
    results = list(base_results) if base_results is not None else _linked_results(fem_part)
    for fallback_index, result in enumerate(results):
        if _result_state_index(result, fallback_index) == state_index:
            return result
    return None


def _ordered_results_for_storage(results):
    def sort_key(item):
        fallback_index, result = item
        state_index = _result_state_index(result, fallback_index)
        return (state_index if state_index is not None else fallback_index, fallback_index)

    return [result for _, result in sorted(enumerate(results), key=sort_key)]


def _set_result_state_metadata(fem_part, result, state_index):
    if _STATE_INDEX_PROPERTY not in list(getattr(result, "PropertiesList", [])):
        try:
            result.addProperty(
                "App::PropertyInteger",
                _STATE_INDEX_PROPERTY,
                "MbDFEM",
                "MbD time-state index solved by this result",
            )
        except Exception:
            pass
    if _STATE_TIME_PROPERTY not in list(getattr(result, "PropertiesList", [])):
        try:
            result.addProperty(
                "App::PropertyFloat",
                _STATE_TIME_PROPERTY,
                "MbDFEM",
                "MbD time value solved by this result",
            )
        except Exception:
            pass
    try:
        setattr(result, _STATE_INDEX_PROPERTY, int(state_index))
    except Exception:
        pass
    try:
        setattr(result, _STATE_TIME_PROPERTY, float(_state_time(fem_part, state_index)))
    except Exception:
        pass


def _property_enum_names(prop):
    try:
        return list(prop.getEnumVector())
    except Exception:
        pass
    try:
        return [str(prop.getItemText(index)) for index in range(prop.count())]
    except Exception:
        pass
    return []


def _property_enum_value(prop):
    try:
        return str(prop.getValueAsString())
    except Exception:
        pass
    try:
        value = prop.getValue()
        names = _property_enum_names(prop)
        if 0 <= value < len(names):
            return names[value]
    except Exception:
        pass
    return ""


def _set_property_enum_value(prop, value):
    if not value:
        return False
    try:
        prop.setValue(value)
        return True
    except Exception:
        pass
    try:
        names = _property_enum_names(prop)
        if value in names:
            prop.setValue(names.index(value))
            return True
    except Exception:
        pass
    return False


def _pipeline_field_name(pipeline):
    view_object = getattr(pipeline, "ViewObject", None)
    field = getattr(view_object, "Field", None)
    if field is None:
        return ""
    value = _property_enum_value(field)
    return "" if value == "None" else value


def _select_pipeline_field(pipeline, preferred_field=None):
    view_object = getattr(pipeline, "ViewObject", None)
    field = getattr(view_object, "Field", None)
    if field is None:
        return ""

    names = _property_enum_names(field)
    candidates = [preferred_field, _DEFAULT_PIPELINE_FIELD, "Displacement Magnitude"]
    for candidate in candidates:
        if candidate and candidate in names and _set_property_enum_value(field, candidate):
            component = getattr(view_object, "Component", None)
            if component is not None:
                _set_property_enum_value(component, "Not a vector")
            try:
                view_object.updateMaterial()
            except Exception:
                pass
            try:
                view_object.updateColorBars()
            except Exception:
                pass
            return candidate
    return _pipeline_field_name(pipeline)


def _pipeline_field_names(pipeline):
    view_object = getattr(pipeline, "ViewObject", None)
    field = getattr(view_object, "Field", None)
    if field is None:
        return []
    return [name for name in _property_enum_names(field) if name and name != "None"]


def _ensure_visual_pipeline(fem_part, result, preferred_field=None):
    if result is None:
        return None

    document = getattr(fem_part, "Document", None)
    if document is None:
        return None

    pipeline = getattr(fem_part, "visual", None)
    if pipeline is None:
        try:
            pipeline = document.addObject("Fem::FemPostPipeline", "Pipeline_CCX_Results")
            fem_part.visual = pipeline
            try:
                fem_part.addObject(pipeline)
            except Exception:
                pass
        except Exception as exc:
            App.Console.PrintWarning(f"Unable to create FEM result pipeline: {exc}\n")
            return None

    if preferred_field is None:
        preferred_field = _pipeline_field_name(pipeline)
    try:
        pipeline.Label = "Pipeline_CCX_Results"
    except Exception:
        pass
    try:
        pipeline.load(result)
    except Exception as exc:
        App.Console.PrintWarning(f"Unable to load FEM result pipeline: {exc}\n")
        return None
    try:
        pipeline.recomputeChildren()
    except Exception:
        pass
    try:
        pipeline.recompute()
    except Exception:
        pass

    view_object = getattr(pipeline, "ViewObject", None)
    if view_object is not None:
        try:
            view_object.ShowInTree = False
        except Exception:
            pass
        try:
            view_object.DisplayMode = "Surface"
        except Exception:
            pass
        try:
            view_object.SelectionStyle = "BoundBox"
        except Exception:
            pass
        try:
            view_object.Visibility = True
        except Exception:
            pass
        try:
            view_object.updateColorBars()
        except Exception:
            pass

    _select_pipeline_field(pipeline, preferred_field)
    return pipeline


def _assign_result_for_state(fem_part, state_index, result, base_results=None):
    if result is None:
        raise ValueError("No CalculiX result object was produced.")

    results = list(base_results) if base_results is not None else _linked_results(fem_part)
    _set_result_state_metadata(fem_part, result, state_index)

    existing = _result_for_state(fem_part, state_index, results)
    if existing is None:
        results.append(result)
    else:
        results[results.index(existing)] = result

    fem_part.results = _ordered_results_for_storage(results)
    try:
        fem_part.synchronizeResultsFolder()
    except Exception:
        pass
    return result


def _new_result(before_results, fem_part):
    for result in reversed(_linked_results(fem_part)):
        if result not in before_results:
            return result
    return None


def solve_fem_part_state(fem_part, state_index, runner=None):
    document = getattr(fem_part, "Document", None)
    solver = getattr(fem_part, "solver", None)
    if document is None:
        raise ValueError("FEMPart is not attached to a document.")
    if solver is None:
        raise ValueError("FEMPart has no CalculiX solver.")

    apply_state(fem_part, state_index)
    before_results = _linked_results(fem_part)

    if runner is None:
        fea = FreeCADMbDFEMEmbedded.FEMPartCcxTools(fem_part, solver)
        working_dir = FreeCADMbDBackend.default_calculix_working_dir(fem_part, state_index)
        fea.setup_working_dir(str(working_dir))
        fea.set_base_name(FreeCADMbDBackend.CALCULIX_BASE_NAME)
        fea.setup_ccx()
        if not fea.run():
            raise RuntimeError("CalculiX solve failed.")
        result = _new_result(before_results, fem_part)
    else:
        result = runner(fem_part, state_index)

    assigned = _assign_result_for_state(
        fem_part,
        state_index,
        result,
        base_results=before_results,
    )
    time_value = _state_time(fem_part, state_index)
    try:
        assigned.Label = f"{fem_part.Label} result {state_index} @ {time_value:.6g}s"
    except Exception:
        pass
    _ensure_visual_pipeline(fem_part, assigned)
    document.recompute()
    return assigned


def _state_time(fem_part, state_index):
    assembly = owning_mbd_assembly(fem_part)
    times = list(getattr(assembly, "times", [])) if assembly is not None else []
    if 0 <= state_index < len(times):
        return float(times[state_index])
    return float(state_index)


class FEMResultsTaskPanel:
    def __init__(self, results_folder):
        from PySide import QtCore, QtWidgets

        self.results_folder = results_folder
        self.fem_part = owning_fem_part(results_folder)
        self._updating = False
        self._stop_requested = False
        self._playing = False
        self._suppress_fem_freshness_warning = False

        self._form_widget = QtWidgets.QWidget()
        self._form_widget.setWindowTitle("FEMPart Results")
        self._play_timer = QtCore.QTimer(self._form_widget)
        self._play_timer.setInterval(250)
        self._play_timer.timeout.connect(self._play_next_state)

        layout = QtWidgets.QVBoxLayout(self._form_widget)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        header_group = QtWidgets.QGroupBox("Results")
        header_layout = QtWidgets.QVBoxLayout(header_group)
        self.status_label = QtWidgets.QLabel()
        self.status_label.setWordWrap(True)
        header_layout.addWidget(self.status_label)
        layout.addWidget(header_group)

        current_group = QtWidgets.QGroupBox("Current State")
        current_layout = QtWidgets.QVBoxLayout(current_group)

        self.slider = QtWidgets.QSlider(QtCore.Qt.Horizontal)
        current_layout.addWidget(self.slider)

        frame_layout = QtWidgets.QHBoxLayout()
        self.previous_button = QtWidgets.QToolButton()
        self.previous_button.setText("<")
        self.previous_button.setToolTip("Previous state")
        self.next_button = QtWidgets.QToolButton()
        self.next_button.setText(">")
        self.next_button.setToolTip("Next state")
        frame_layout.addWidget(self.previous_button)
        frame_layout.addWidget(QtWidgets.QLabel("State:"))
        self.state_spin = QtWidgets.QSpinBox()
        frame_layout.addWidget(self.state_spin)
        self.state_count_label = QtWidgets.QLabel()
        frame_layout.addWidget(self.state_count_label)
        frame_layout.addStretch()
        frame_layout.addWidget(QtWidgets.QLabel("Time:"))
        self.time_label = QtWidgets.QLabel()
        frame_layout.addWidget(self.time_label)
        frame_layout.addWidget(self.next_button)
        current_layout.addLayout(frame_layout)
        layout.addWidget(current_group)

        interval_group = QtWidgets.QGroupBox("Play Range")
        interval_layout = QtWidgets.QVBoxLayout(interval_group)

        start_layout = QtWidgets.QHBoxLayout()
        start_layout.addWidget(QtWidgets.QLabel("Start State:"))
        self.start_state_spin = QtWidgets.QSpinBox()
        start_layout.addWidget(self.start_state_spin)
        self.start_state_count_label = QtWidgets.QLabel()
        start_layout.addWidget(self.start_state_count_label)
        start_layout.addStretch()
        start_layout.addWidget(QtWidgets.QLabel("Time:"))
        self.start_time_label = QtWidgets.QLabel()
        start_layout.addWidget(self.start_time_label)
        interval_layout.addLayout(start_layout)

        end_layout = QtWidgets.QHBoxLayout()
        end_layout.addWidget(QtWidgets.QLabel("End State:"))
        self.end_state_spin = QtWidgets.QSpinBox()
        end_layout.addWidget(self.end_state_spin)
        self.end_state_count_label = QtWidgets.QLabel()
        end_layout.addWidget(self.end_state_count_label)
        end_layout.addStretch()
        end_layout.addWidget(QtWidgets.QLabel("Time:"))
        self.end_time_label = QtWidgets.QLabel()
        end_layout.addWidget(self.end_time_label)
        interval_layout.addLayout(end_layout)

        layout.addWidget(interval_group)

        display_group = QtWidgets.QGroupBox("Display")
        display_layout = QtWidgets.QVBoxLayout(display_group)
        playback_layout = QtWidgets.QHBoxLayout()
        self.play_button = QtWidgets.QPushButton("Play")
        self.stop_playback_button = QtWidgets.QPushButton("Stop")
        playback_layout.addWidget(self.play_button)
        playback_layout.addWidget(self.stop_playback_button)
        display_layout.addLayout(playback_layout)
        layout.addWidget(display_group)
        layout.addStretch(1)

        self.previous_button.clicked.connect(self._previous_state)
        self.next_button.clicked.connect(self._next_state)
        self.slider.valueChanged.connect(self._set_state)
        self.state_spin.valueChanged.connect(self._set_state)
        self.start_state_spin.valueChanged.connect(self._refresh)
        self.end_state_spin.valueChanged.connect(self._refresh)
        self.play_button.clicked.connect(self._play_results)
        self.stop_playback_button.clicked.connect(self._stop_playback)

        pipeline_widgets = self._pipeline_task_widgets()
        self.form = [self._form_widget, *pipeline_widgets] if pipeline_widgets else self._form_widget

        self._configure()
        self._refresh()

    def getStandardButtons(self):
        from PySide import QtGui

        return QtGui.QDialogButtonBox.Close

    def reject(self):
        import FreeCADGui as Gui

        self._stop_solver()
        self._stop_playback()
        Gui.Control.closeDialog()
        return True

    def _configure(self):
        count = state_count(self.fem_part) if self.fem_part is not None else 0
        maximum = max(count - 1, 0)
        self._updating = True
        try:
            self.slider.setRange(0, maximum)
            self.state_spin.setRange(0, maximum)
            self.start_state_spin.setRange(0, maximum)
            self.end_state_spin.setRange(0, maximum)
            self.start_state_spin.setValue(0)
            self.end_state_spin.setValue(maximum)
        finally:
            self._updating = False
        enabled = self.fem_part is not None and count > 0
        for widget in (
            self.previous_button,
            self.next_button,
            self.slider,
            self.state_spin,
            self.start_state_spin,
            self.end_state_spin,
            self.play_button,
        ):
            widget.setEnabled(enabled)
        self.stop_playback_button.setEnabled(False)

    def _refresh(self, message=None):
        count = state_count(self.fem_part) if self.fem_part is not None else 0
        index = self.state_spin.value()
        if self.fem_part is None:
            self.status_label.setText("No owning FEMPart found.")
        elif count == 0:
            self.status_label.setText("No MbDAssembly state series found.")
        elif message:
            self.status_label.setText(message)
        else:
            solved = len(
                {
                    _result_state_index(result, fallback)
                    for fallback, result in enumerate(_linked_results(self.fem_part))
                }
            )
            self.status_label.setText(f"{self.fem_part.Label}: {solved} / {count} states solved")

        self.state_count_label.setText(f"/ {max(count - 1, 0)}")
        self.time_label.setText(f"{_state_time(self.fem_part, index):.6g} s")
        self.start_state_count_label.setText(f"/ {max(count - 1, 0)}")
        self.end_state_count_label.setText(f"/ {max(count - 1, 0)}")
        self.start_time_label.setText(
            f"{_state_time(self.fem_part, self.start_state_spin.value()):.6g} s"
        )
        self.end_time_label.setText(
            f"{_state_time(self.fem_part, self.end_state_spin.value()):.6g} s"
        )

    def _pipeline_for_task_panel(self):
        if self.fem_part is None:
            return None
        pipeline = getattr(self.fem_part, "visual", None)
        if pipeline is not None:
            return pipeline

        results = _linked_results(self.fem_part)
        if not results:
            return None
        return _ensure_visual_pipeline(self.fem_part, results[0])

    def _pipeline_task_widgets(self):
        pipeline = self._pipeline_for_task_panel()
        view_object = getattr(pipeline, "ViewObject", None)
        if view_object is None:
            return []

        widgets = []
        for method_name in (
            "createDisplayTaskWidget",
            "createExtractionTaskWidget",
            "createFramesTaskWidget",
        ):
            try:
                widgets.append(getattr(view_object, method_name)())
            except NotImplementedError:
                pass
            except Exception as exc:
                App.Console.PrintWarning(
                    f"Unable to append FEM pipeline task widget {method_name}: {exc}\n"
                )
        return [widget for widget in widgets if widget is not None]

    def _refresh_pipeline_task_widgets(self):
        pipeline = getattr(self.fem_part, "visual", None)
        view_object = getattr(pipeline, "ViewObject", None)
        if view_object is None:
            return
        for method_name in ("updateColorBars",):
            method = getattr(view_object, method_name, None)
            if method is None:
                continue
            try:
                method()
            except Exception:
                pass

    def _set_pipeline_from_task_panel(self):
        pipeline = getattr(self.fem_part, "visual", None)
        if pipeline is None:
            return
        view_object = getattr(pipeline, "ViewObject", None)
        if view_object is None:
            return
        try:
            field = _pipeline_field_name(pipeline)
            if field:
                _select_pipeline_field(pipeline, field)
        except Exception:
            pass

    def _set_state(self, value):
        if self._updating:
            return
        self._updating = True
        try:
            self.slider.setValue(int(value))
            self.state_spin.setValue(int(value))
        finally:
            self._updating = False
        self._apply_current_state()

    def _previous_state(self):
        self._set_state(max(self.state_spin.value() - 1, self.state_spin.minimum()))

    def _next_state(self):
        self._set_state(min(self.state_spin.value() + 1, self.state_spin.maximum()))

    def _apply_current_state(self):
        if self.fem_part is None:
            return
        try:
            self._show_state(self.state_spin.value())
            self._refresh()
        except Exception as exc:
            App.Console.PrintError(f"{exc}\n")
            self._refresh(str(exc))

    def _times(self):
        assembly = owning_mbd_assembly(self.fem_part) if self.fem_part is not None else None
        times = list(getattr(assembly, "times", [])) if assembly is not None else []
        count = state_count(self.fem_part) if self.fem_part is not None else 0
        if times:
            return [float(value) for value in times[:count]]
        return [float(index) for index in range(count)]

    def _interval_indices(self):
        count = state_count(self.fem_part) if self.fem_part is not None else 0
        if count == 0:
            return []
        start = min(self.start_state_spin.value(), self.end_state_spin.value())
        end = max(self.start_state_spin.value(), self.end_state_spin.value())
        return list(range(start, end + 1))

    def _stop_solver(self):
        self._stop_requested = True

    def _play_results(self):
        indices = self._interval_indices()
        if not indices:
            self._refresh("No states in the selected time interval.")
            return

        self._playing = True
        self.play_button.setEnabled(False)
        self.stop_playback_button.setEnabled(True)
        self._set_state(indices[0])
        self._play_timer.start()

    def _stop_playback(self):
        self._playing = False
        try:
            self._play_timer.stop()
        except RuntimeError:
            return
        count = state_count(self.fem_part) if self.fem_part is not None else 0
        self.play_button.setEnabled(count > 0)
        self.stop_playback_button.setEnabled(False)

    def _play_next_state(self):
        if not self._playing:
            return

        indices = self._interval_indices()
        if not indices:
            self._stop_playback()
            return

        current = self.state_spin.value()
        try:
            next_position = indices.index(current) + 1
        except ValueError:
            next_position = 0
        if next_position >= len(indices):
            next_position = 0
        self._set_state(indices[next_position])

    def _show_state(self, index):
        current_result = _result_for_state(self.fem_part, index)
        if current_result is not None and not self._suppress_fem_freshness_warning:
            if not self._confirm_warning(
                FreeCADMbDBackend.fem_files_freshness_warning(self.fem_part, index),
                "Stale FEM Files",
            ):
                raise RuntimeError("FEM result display canceled.")

        apply_state(self.fem_part, index)
        pipeline = _ensure_visual_pipeline(self.fem_part, current_result)
        self._refresh_pipeline_task_widgets()
        for result in _linked_results(self.fem_part):
            visible = result is current_result
            view_object = getattr(result, "ViewObject", None)
            if view_object is not None:
                try:
                    view_object.Visibility = visible and pipeline is None
                except Exception:
                    pass
            result_mesh = getattr(result, "Mesh", None)
            mesh_view = getattr(result_mesh, "ViewObject", None)
            if mesh_view is not None:
                try:
                    mesh_view.Visibility = visible and pipeline is None
                except Exception:
                    pass
        visual = getattr(self.fem_part, "visual", None)
        visual_view = getattr(visual, "ViewObject", None)
        if visual_view is not None:
            try:
                visual_view.Visibility = pipeline is not None
            except Exception:
                pass
        return current_result

    def _run_state(self, index):
        from PySide import QtWidgets

        if self.fem_part is None:
            return False
        try:
            self._refresh(f"Solving state {index}...")
            QtWidgets.QApplication.processEvents()
            result = solve_fem_part_state(self.fem_part, index)
            self._refresh(f"Solved state {index}: {result.Label}")
            return True
        except Exception as exc:
            App.Console.PrintError(f"{exc}\n")
            self._refresh(str(exc))
            return False

    def _set_buttons_enabled(self, enabled):
        count = state_count(self.fem_part) if self.fem_part is not None else 0
        enabled = bool(enabled and self.fem_part is not None and count > 0)
        for widget in (
            self.previous_button,
            self.next_button,
            self.slider,
            self.state_spin,
            self.start_state_spin,
            self.end_state_spin,
            self.play_button,
        ):
            widget.setEnabled(enabled)
        self.stop_playback_button.setEnabled(self._playing)

    def _confirm_warning(self, message, title):
        if not message:
            return True

        App.Console.PrintWarning(message + "\n")
        if not App.GuiUp:
            return True

        from PySide import QtGui

        buttons = QtGui.QMessageBox.Ok | QtGui.QMessageBox.Cancel
        response = QtGui.QMessageBox.warning(None, title, message, buttons, QtGui.QMessageBox.Cancel)
        return response == QtGui.QMessageBox.Ok


def show_results_task_panel(results_folder):
    import FreeCADGui as Gui

    active = Gui.Control.activeDialog()
    if isinstance(active, FEMResultsTaskPanel):
        if active.results_folder == results_folder:
            return active
        Gui.Control.closeDialog()
    elif active is not None:
        Gui.Control.closeDialog()

    panel = FEMResultsTaskPanel(results_folder)
    Gui.Control.showDialog(panel)
    return panel
