# SPDX-License-Identifier: LGPL-2.1-or-later

"""Assembly-wide, sequential CalculiX jobs on a shared MbD state timeline."""

import multiprocessing
from math import isclose
from pathlib import Path

import FreeCAD as App
import FreeCADMbDAnimation
import FreeCADMbDBackend as Backend
import FreeCADMbDFEMEmbedded as Embedded
import FreeCADMbDFEMResultsPanel as Results


def ensure_simulation_parameters(assembly):
    parameters = assembly.femParameters
    if parameters is None:
        parameters = assembly.Document.addObject(
            "MbDFEM::FEMSimulationParameters", f"{assembly.Name}_SimulationParameters"
        )
        parameters.Label = "SimulationParameters"
        assembly.addObject(parameters)
        assembly.femParameters = parameters
    if not parameters.isDerivedFrom("MbDFEM::FEMSimulationParameters"):
        raise ValueError("FEMAssembly femParameters must link to FEMSimulationParameters.")
    if not parameters.settingsInitialized:
        parameters.selectedParts = list(assembly.parts)
        mbd = assembly.mbdItem
        motion_parameters = mbd.getAnimationParameters() if mbd is not None else None
        if motion_parameters is not None:
            parameters.currentState = motion_parameters.currentFrame
        parameters.settingsInitialized = True
    return parameters


class FEMSimulationController:
    """Build jobs by state, applying assembly motion once for each state."""

    def __init__(self, assembly):
        self.assembly = assembly
        self.mbd = assembly.mbdItem
        if self.mbd is None or not self.mbd.isDerivedFrom("MbDFEM::MbDAssembly"):
            raise ValueError("FEMAssembly has no linked MbDAssembly.")
        self.motion = FreeCADMbDAnimation.AnimationController(self.mbd)
        self._applied_state = None

    def jobs(self, parts, states, missing_only=False):
        if not parts:
            raise ValueError("Select at least one FEM part.")
        parts = list(dict.fromkeys(parts))
        for part in parts:
            if part not in self.assembly.parts or Results.owning_mbd_assembly(part) != self.mbd:
                raise ValueError(f"{part.Label} does not belong to this assembly's MbD timeline.")
        states = list(states)
        if not states or any(not 0 <= state < self.motion.source_frame_count for state in states):
            raise ValueError("Select a valid range of MbD simulation states.")
        self._applied_state = None
        return [(part, state) for state in states for part in parts
                if not missing_only or not self.has_current_result(part, state)]

    def has_current_result(self, part, state):
        result = Results._result_for_state(part, state)
        if result is None:
            return False
        time = getattr(result, Results._STATE_TIME_PROPERTY, None)
        if time is None or not isclose(float(time), self.motion.result_times[state],
                                      rel_tol=1e-9, abs_tol=1e-12):
            return False
        return not Backend.fem_files_freshness_warning(part, state_index=state)

    def apply_state(self, state):
        if self._applied_state != state:
            self.motion.setFrame(state)
            Results._sync_fem_parts_to_mbd_parts(self.mbd, self.motion.targets)
            self._applied_state = state

    @staticmethod
    def tools(part, state, *, write=False):
        if part.solver is None:
            raise ValueError(f"{part.Label} has no CalculiX solver.")
        fea = Embedded.FEMPartCcxTools(part, part.solver)
        directory = Backend.default_calculix_working_dir(part, state)
        fea.setup_working_dir(str(directory))
        fea.set_base_name(Backend.CALCULIX_BASE_NAME)
        if write:
            fea.update_objects()
            message = fea.check_prerequisites()
            if message:
                raise ValueError(message)
            fea.write_inp_file()
            if not fea.inp_file_name or not Path(fea.inp_file_name).is_file():
                raise RuntimeError("CalculiX input file was not written.")
        return fea


class FEMSimulationTaskPanel:
    def __init__(self, assembly):
        from PySide import QtCore, QtWidgets

        self.assembly = assembly
        self.controller = FEMSimulationController(assembly)
        self.parameters = ensure_simulation_parameters(assembly)
        self._document_name = assembly.Document.Name
        self._closed = False
        self._observing = False
        self._updating = True
        self._running = False
        self._stop_requested = False
        self._process = None
        self._log = None
        self._queue = []
        self._position = 0
        self._failures = 0
        self._succeeded = 0
        self._mode = ""
        self._active_job = None
        self.form = QtWidgets.QWidget()
        self.form.setWindowTitle("FEM Assembly Simulation")
        self.form.destroyed.connect(self._destroyed)
        self._timer = QtCore.QTimer(self.form)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._next_job)
        layout = QtWidgets.QVBoxLayout(self.form)
        layout.addWidget(QtWidgets.QLabel("Parts to process together:"))
        self.body_checks = []
        for part in assembly.parts:
            check = QtWidgets.QCheckBox(part.Label)
            check.setChecked(part in self.parameters.selectedParts)
            check.toggled.connect(self._save_settings)
            self.body_checks.append((part, check))
            layout.addWidget(check)
        maximum = max(self.controller.motion.source_frame_count - 1, 0)
        settings = QtWidgets.QFormLayout()
        self.current_spin = QtWidgets.QSpinBox()
        self.first_spin = QtWidgets.QSpinBox()
        self.last_spin = QtWidgets.QSpinBox()
        for spin in (self.current_spin, self.first_spin, self.last_spin):
            spin.setRange(0, maximum)
            spin.setKeyboardTracking(False)
            spin.valueChanged.connect(self._save_settings)
        self.current_spin.setValue(self.parameters.currentState)
        self.first_spin.setValue(self.parameters.startState)
        self.last_spin.setValue(maximum if self.parameters.endState < 0 else self.parameters.endState)
        self.time_label = QtWidgets.QLabel()
        settings.addRow("Current State:", self.current_spin)
        settings.addRow("Simulation time:", self.time_label)
        settings.addRow("First State:", self.first_spin)
        settings.addRow("Last State:", self.last_spin)
        self.missing_check = QtWidgets.QCheckBox("Only missing or stale imported results")
        self.missing_check.setChecked(self.parameters.missingOnly)
        self.missing_check.setToolTip(
            "Skip imported results with matching state time and current MbD source files. "
            "Clear this option after changing mesh, material, constraints, or other inputs."
        )
        self.continue_check = QtWidgets.QCheckBox("Continue after a failed job")
        self.continue_check.setChecked(self.parameters.continueOnError)
        for check in (self.missing_check, self.continue_check):
            check.toggled.connect(self._save_settings)
            settings.addRow(check)
        layout.addLayout(settings)
        self.action_buttons = []
        for title, mode, current in (
            ("Write Inputs", "write", False),
            ("Solve Current State", "solve", True),
            ("Solve Range", "solve", False),
            ("Import Results", "import", False),
        ):
            button = QtWidgets.QPushButton(title)
            button.clicked.connect(lambda checked=False, m=mode, c=current: self._start(m, c))
            self.action_buttons.append(button)
            layout.addWidget(button)
        self.stop_button = QtWidgets.QPushButton("Stop after current job")
        self.stop_button.setEnabled(False)
        self.stop_button.clicked.connect(self._stop)
        layout.addWidget(self.stop_button)
        self.progress = QtWidgets.QProgressBar()
        layout.addWidget(self.progress)
        self.status_label = QtWidgets.QLabel(
            f"{self.controller.motion.source_frame_count} MbD states available."
        )
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)
        self.table = QtWidgets.QTableWidget(len(self.body_checks), 4)
        self.table.setHorizontalHeaderLabels(["Part", "Completed jobs", "Status", "Failed states"])
        for row, (part, _) in enumerate(self.body_checks):
            for col, value in enumerate((part.Label, "0", "Ready", "")):
                self.table.setItem(row, col, QtWidgets.QTableWidgetItem(value))
        self.table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self.table.verticalHeader().hide()
        for column in (0, 1, 3):
            self.table.horizontalHeader().setSectionResizeMode(column, QtWidgets.QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QtWidgets.QHeaderView.Stretch)
        layout.addWidget(self.table)
        self._updating = False
        self._save_settings()
        App.addDocumentObserver(self)
        self._observing = True

    def getStandardButtons(self):
        from PySide import QtWidgets

        return QtWidgets.QDialogButtonBox.Close

    def _save_settings(self, *args, commit=False):
        if self._closed or self._updating:
            return
        if commit:
            for spin in (self.current_spin, self.first_spin, self.last_spin):
                spin.interpretText()
        self.parameters.selectedParts = [part for part, check in self.body_checks if check.isChecked()]
        self.parameters.currentState = self.current_spin.value()
        times = self.controller.motion.result_times
        state = self.current_spin.value()
        if 0 <= state < len(times):
            value = times[state]
            self.time_label.setText("Input" if Results._is_input_state_time(value) else f"{value:.6g} s")
        else:
            self.time_label.setText("No MbD states")
        self.parameters.startState = self.first_spin.value()
        self.parameters.endState = self.last_spin.value()
        self.parameters.missingOnly = self.missing_check.isChecked()
        self.parameters.continueOnError = self.continue_check.isChecked()

    def slotStartSaveDocument(self, document, filename):
        if document.Name == self._document_name:
            self._save_settings(commit=True)

    def slotDeletedDocument(self, document):
        if document.Name == self._document_name:
            self._shutdown()

    def _remove_observer(self):
        if self._observing:
            App.removeDocumentObserver(self)
            self._observing = False

    def accept(self):
        if self._running:
            self._stop()
            self.status_label.setText("Stopping after the current job. Close when it finishes.")
            return False
        self._save_settings(commit=True)
        self._shutdown()
        return True

    def reject(self):
        return self.accept()

    def _destroyed(self, *args):
        self._shutdown(form_destroyed=True)

    def _shutdown(self, form_destroyed=False):
        if self._closed:
            return
        self._closed = True
        self._running = False
        if not form_destroyed:
            self._timer.stop()
        if self._process is not None:
            self._process.kill()
            self._process.waitForFinished(1000)
        self._close_log()
        self._remove_observer()

    def _set_busy(self, busy):
        self._running = busy
        for widget in (self.current_spin, self.first_spin, self.last_spin,
                       self.missing_check, self.continue_check, *self.action_buttons):
            widget.setEnabled(not busy)
        for _, check in self.body_checks:
            check.setEnabled(not busy)
        self.stop_button.setEnabled(busy)

    def _part_status(self, part, text, completed=False):
        for row, (member, _) in enumerate(self.body_checks):
            if member == part:
                self.table.item(row, 2).setText(text)
                if completed:
                    item = self.table.item(row, 1)
                    item.setText(str(int(item.text()) + 1))
                break

    def _start(self, mode, current=False):
        if self._running or self._closed:
            return
        self._save_settings(commit=True)
        first, last = self.first_spin.value(), self.last_spin.value()
        if not current and first > last:
            self.status_label.setText("First State must not exceed Last State.")
            return
        states = [self.current_spin.value()] if current else range(first, last + 1)
        try:
            self._queue = self.controller.jobs(
                self.parameters.selectedParts, states,
                missing_only=self.missing_check.isChecked() and mode != "write",
            )
        except Exception as exc:
            self.status_label.setText(str(exc))
            return
        self._mode = mode
        self._position = self._failures = self._succeeded = 0
        self._stop_requested = False
        self._continue_on_error = self.continue_check.isChecked()
        for row in range(self.table.rowCount()):
            self.table.item(row, 1).setText("0")
            self.table.item(row, 2).setText("Ready")
            self.table.item(row, 3).setText("")
            self.table.item(row, 3).setToolTip("")
        self.progress.setRange(0, max(len(self._queue), 1))
        self.progress.setValue(0)
        if not self._queue:
            self.status_label.setText("No jobs to process; selected results are already imported and current.")
            return
        self._set_busy(True)
        self._timer.start(0)

    def _stop(self):
        self._stop_requested = True
        self.stop_button.setEnabled(False)
        self.status_label.setText("Stopping after the current job.")

    def _next_job(self):
        if self._closed or not self._running:
            return
        if self._stop_requested or self._position >= len(self._queue):
            self._finish()
            return
        part, state = self._queue[self._position]
        self._active_job = (part, state)
        self.current_spin.setValue(state)
        self.status_label.setText(
            f"State {state}, {part.Label}: job {self._position + 1} of {len(self._queue)} ({self._mode})."
        )
        self._part_status(part, f"State {state}: {self._mode}")
        try:
            self.controller.apply_state(state)
            if self._mode == "import":
                self._import_result(part, state)
                self._complete_job()
            else:
                fea = self.controller.tools(part, state, write=True)
                if self._mode == "write":
                    self._complete_job()
                else:
                    self._launch(fea, part, state)
        except Exception as exc:
            self._complete_job(exc)

    @staticmethod
    def _import_result(part, state):
        return Results.import_fem_part_state(part, state, state_applied=True)

    def _launch(self, fea, part, state):
        from PySide import QtCore

        fea.setup_ccx()
        if not fea.ccx_binary_present:
            raise RuntimeError("CalculiX executable not found; set its path in FEM preferences.")
        inp = Path(fea.inp_file_name)
        self._frd_path = inp.with_suffix(".frd")
        self._previous_frd = self._frd_signature()
        self._log = inp.with_suffix(".log").open("wb")
        process = QtCore.QProcess(self.form)
        self._process = process
        process.setWorkingDirectory(str(inp.parent))
        environment = QtCore.QProcessEnvironment.systemEnvironment()
        count = App.ParamGet("User parameter:BaseApp/Preferences/Mod/Fem/Ccx").GetInt("AnalysisNumCPUs", 1)
        environment.insert("OMP_NUM_THREADS", str(count if count > 0 else multiprocessing.cpu_count()))
        process.setProcessEnvironment(environment)
        process.setProcessChannelMode(QtCore.QProcess.MergedChannels)
        process.readyReadStandardOutput.connect(self._read_output)
        process.finished.connect(self._process_finished)
        process.errorOccurred.connect(self._process_error)
        process.start(str(fea.ccx_binary), ["-i", inp.stem])

    def _frd_signature(self):
        try:
            stat = self._frd_path.stat()
            return stat.st_mtime_ns, stat.st_size
        except FileNotFoundError:
            return None

    def _read_output(self):
        if self._process is not None:
            output = bytes(self._process.readAllStandardOutput())
            if self._log is not None:
                self._log.write(output)
                self._log.flush()

    def _process_error(self, error):
        from PySide import QtCore

        if not self._closed and error == QtCore.QProcess.FailedToStart:
            self._complete_job(RuntimeError(self._process.errorString()))

    def _process_finished(self, exit_code, exit_status):
        from PySide import QtCore

        if self._closed or self._process is None:
            return
        self._read_output()
        try:
            if exit_status != QtCore.QProcess.NormalExit or exit_code != 0:
                raise RuntimeError(f"CalculiX exited with code {exit_code}; see {self._frd_path.with_suffix('.log')}.")
            signature = self._frd_signature()
            if signature is None or signature == self._previous_frd:
                raise RuntimeError("CalculiX did not produce a new FRD result file.")
            self._import_result(*self._active_job)
            self._complete_job()
        except Exception as exc:
            self._complete_job(exc)

    def _close_log(self):
        if self._log is not None:
            self._log.close()
            self._log = None

    def _complete_job(self, error=None):
        if self._closed:
            return
        self._close_log()
        if self._process is not None:
            self._process.deleteLater()
            self._process = None
        part, state = self._active_job
        if error is None:
            self._succeeded += 1
            self._part_status(part, f"State {state}: completed", completed=True)
        else:
            self._failures += 1
            for row, (member, _) in enumerate(self.body_checks):
                if member == part:
                    item = self.table.item(row, 3)
                    item.setText(", ".join(filter(None, (item.text(), str(state)))))
                    item.setToolTip(item.toolTip() + f"State {state}: {error}\n")
                    break
            self._part_status(part, f"State {state}: failed ({error})")
            App.Console.PrintError(f"FEM assembly {self._mode}, {part.Label}, state {state}: {error}\n")
            if not self._continue_on_error:
                self._stop_requested = True
        self._position += 1
        self.progress.setValue(self._position)
        self._timer.start(0)

    def _finish(self):
        self._set_busy(False)
        prefix = "Stopped" if self._stop_requested else "Finished"
        self.status_label.setText(
            f"{prefix}: {self._succeeded} completed, {self._failures} failed, "
            f"{len(self._queue) - self._position} pending."
        )
        self._save_settings()


def show_simulation_task_panel(assembly):
    import FreeCADGui as Gui

    if Gui.Control.activeDialog():
        Gui.Control.closeDialog()
        if Gui.Control.activeDialog():
            raise RuntimeError("Close the active task before opening assembly simulation.")
    panel = FEMSimulationTaskPanel(assembly)
    Gui.Control.showDialog(panel)
    return panel


def show_parameters_task_panel(parameters):
    for obj in parameters.Document.Objects:
        if obj.isDerivedFrom("MbDFEM::FEMAssembly") and obj.femParameters == parameters:
            return show_simulation_task_panel(obj)
    raise ValueError("No owning FEMAssembly found for these simulation parameters.")


class SimulateFEMAssemblyCommand:
    def GetResources(self):
        return {"MenuText": "Simulate FEM Assembly",
                "ToolTip": "Write, solve, or import CalculiX states for selected FEM parts"}

    @staticmethod
    def active_assembly():
        import FreeCADGui as Gui

        document = App.ActiveDocument
        if document is None:
            return None
        assemblies = [obj for obj in document.Objects if obj.isDerivedFrom("MbDFEM::FEMAssembly")]
        for obj in Gui.Selection.getSelection():
            for assembly in assemblies:
                if obj == assembly or obj in assembly.parts or obj == assembly.femParameters:
                    return assembly
        return assemblies[0] if len(assemblies) == 1 else None

    def IsActive(self):
        return self.active_assembly() is not None

    def Activated(self):
        assembly = self.active_assembly()
        if assembly is None:
            App.Console.PrintError("Select an FEMAssembly to simulate its parts.\n")
            return
        try:
            show_simulation_task_panel(assembly)
        except Exception as exc:
            App.Console.PrintError(f"FEM assembly simulation: {exc}\n")
