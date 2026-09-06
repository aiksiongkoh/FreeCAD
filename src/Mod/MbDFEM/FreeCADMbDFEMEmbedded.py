# SPDX-License-Identifier: LGPL-2.1-or-later

"""MbDFEM-local view providers for FEM objects owned by FEMPart."""


from femtaskpanels import task_solver_ccxtools

import contextlib
import math
import os
import shutil


_321_CONSTRAINT_TOLERANCE = 1.0e-9
_321_CONSTRAINT_MARKER = "** Automatic 3-2-1 constraints\n"
_MBD_GRAVITY_MARKER = "** MbDAssembly gravity\n"
_MBD_DALEMBERT_MARKER = "** MbDPart D'Alembert element loads\n"
_CCX_STATIC_NO_BC_MESSAGE = "Static analysis: No mechanical boundary conditions defined.\n"
_INP_SECTION_SEPARATOR = 59 * "*"
_MBD_TO_CCX_GRAVITY_SCALE = 1000.0
_CAD_LENGTH_TO_MBD_LENGTH_SCALE = 0.001
_original_solver_reject = None
_original_result_set_label = None


def _linked_results(fem_part):
    results = getattr(fem_part, "results", [])
    if results is None:
        return []
    if isinstance(results, (list, tuple)):
        return [result for result in results if result is not None]
    return [results]


def _append_linked_result(fem_part, result):
    if result is None:
        return
    results = _linked_results(fem_part)
    if result not in results:
        results.append(result)
        fem_part.results = results
    try:
        fem_part.synchronizeResultsFolder()
    except Exception:
        pass


def install_solver_task_panel_close_fallback():
    """Close stock Calculix task panels opened for FEMPart-owned solvers."""
    global _original_solver_reject

    if _original_solver_reject is not None:
        return

    _original_solver_reject = task_solver_ccxtools._TaskPanel.reject

    def reject(task_panel):
        result = _original_solver_reject(task_panel)
        solver = getattr(getattr(task_panel, "fea", None), "solver", None)
        if fem_part_for_solver(solver) is not None:
            import FreeCADGui as Gui

            Gui.Control.closeDialog()
            return True
        return result

    task_solver_ccxtools._TaskPanel.reject = reject


def install_result_task_panel_label_fallback():
    """Avoid the Coin overlay label path that crashes in MbDFEM result display."""
    global _original_result_set_label

    from femtaskpanels import task_result_mechanical

    current_set_label = task_result_mechanical._TaskPanel.set_label
    if getattr(current_set_label, "_mbdfem_overlay_fallback", False):
        return

    if _original_result_set_label is not None:
        return

    _original_result_set_label = current_set_label

    def set_label(task_panel, result_name, mesh_data):
        result_obj = getattr(task_panel, "result_obj", None)
        if fem_part_for_result(result_obj) is not None:
            return
        return _original_result_set_label(task_panel, result_name, mesh_data)

    set_label._mbdfem_overlay_fallback = True
    task_result_mechanical._TaskPanel.set_label = set_label


class FEMPartMaterialTaskPanel:
    """Read-only FEM material view synchronized from the linked MbDMassMarker."""

    def __init__(self, obj):
        from PySide import QtWidgets

        self.obj = obj
        self.material = dict(getattr(obj, "Material", {}) or {})
        self.parameterWidget = QtWidgets.QWidget()
        self.parameterWidget.setWindowTitle("FEM Material")
        self.parameterWidget.setMinimumWidth(320)

        layout = QtWidgets.QVBoxLayout(self.parameterWidget)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        title = QtWidgets.QLabel(getattr(obj, "Label", obj.Name))
        title.setStyleSheet("font-weight: bold;")
        layout.addWidget(title)

        source = QtWidgets.QLabel("Read-only material synchronized from the linked MbDMassMarker.")
        source.setWordWrap(True)
        layout.addWidget(source)

        values = QtWidgets.QGroupBox("Material Properties")
        values_layout = QtWidgets.QFormLayout(values)
        values_layout.setFieldGrowthPolicy(QtWidgets.QFormLayout.AllNonFixedFieldsGrow)
        for label, key in _material_display_rows(getattr(obj, "Category", "")):
            values_layout.addRow(label, _read_only_value(_material_value(self.material, key)))
        layout.addWidget(values)
        layout.addStretch(1)

        self.form = [self.parameterWidget]

    def getStandardButtons(self):
        from PySide import QtGui

        return QtGui.QDialogButtonBox.Ok

    def accept(self):
        return self.reject()

    def reject(self):
        try:
            self.selectionWidget.finish_selection()
        except Exception:
            pass
        gui_doc = self.obj.ViewObject.Document
        gui_doc.Document.abortTransaction()
        gui_doc.resetEdit()
        gui_doc.Document.recompute()
        return True


def _read_only_value(value):
    from PySide import QtCore, QtWidgets

    field = QtWidgets.QLineEdit(value)
    field.setReadOnly(True)
    field.setFocusPolicy(QtCore.Qt.NoFocus)
    return field


def _material_display_rows(category):
    rows = [
        ("Name", "Name"),
        ("Density", "Density"),
        ("Young's modulus", "YoungsModulus"),
        ("Poisson ratio", "PoissonRatio"),
        ("Thermal conductivity", "ThermalConductivity"),
        ("Thermal expansion", "ThermalExpansionCoefficient"),
        ("Reference temperature", "ThermalExpansionReferenceTemperature"),
        ("Specific heat", "SpecificHeat"),
    ]
    if category == "Fluid":
        rows.insert(3, ("Kinematic viscosity", "KinematicViscosity"))
    return rows


def _material_value(material, key):
    value = material.get(key, "")
    if value is None:
        return ""
    return str(value)


def _solver_state_count(fem_part):
    try:
        import FreeCADMbDFEMResultsPanel

        return FreeCADMbDFEMResultsPanel.state_count(fem_part)
    except Exception:
        return 0


def _solver_state_time_text(fem_part, state_index):
    try:
        import FreeCADMbDFEMResultsPanel

        return f"{FreeCADMbDFEMResultsPanel._state_time(fem_part, state_index):.6g} s"
    except Exception:
        return ""


class FEMPartMaterialViewProvider:
    """View provider for FEMPart-owned material objects."""

    def __init__(self, view_object):
        self.attach(view_object)
        view_object.Proxy = self

    def attach(self, view_object):
        self.Object = view_object.Object
        self.ViewObject = view_object

    def getIcon(self):
        obj = getattr(self, "Object", None)
        if obj is None:
            obj = getattr(getattr(self, "ViewObject", None), "Object", None)
        if getattr(obj, "Category", "") == "Fluid":
            return ":/icons/FEM_MaterialFluid.svg"
        return ":/icons/FEM_MaterialSolid.svg"

    def setEdit(self, view_object, mode=0):
        import FreeCADGui as Gui

        Gui.Control.showDialog(FEMPartMaterialTaskPanel(view_object.Object))
        return True

    def unsetEdit(self, view_object, mode=0):
        import FreeCADGui as Gui

        Gui.Control.closeDialog()
        return True

    def doubleClicked(self, view_object):
        import FreeCADGui as Gui

        if Gui.Control.activeDialog() is not None:
            Gui.Control.closeDialog()
        return self.setEdit(view_object)

    def claimChildren(self):
        nonlin = getattr(self.Object, "Nonlinear", None)
        return [nonlin] if nonlin else []

    def dumps(self):
        return None

    def loads(self, state):
        return None


class FEMPartSolverViewProvider:
    """View provider for FEMPart-owned solver objects outside a FEM Analysis."""

    def __init__(self, view_object):
        self.attach(view_object)
        view_object.Proxy = self

    def attach(self, view_object):
        self.Object = view_object.Object
        self.ViewObject = view_object

    def getIcon(self):
        return ":/icons/FEM_SolverStandard.svg"

    def setEdit(self, view_object, mode=0):
        import FreeCADGui as Gui

        fem_part = fem_part_for_solver(view_object.Object)
        if fem_part is None:
            return False
        Gui.Control.showDialog(FEMPartSolverTaskPanel(fem_part, view_object.Object))
        return True

    def unsetEdit(self, view_object, mode=0):
        import FreeCADGui as Gui

        Gui.Control.closeDialog()
        return True

    def doubleClicked(self, view_object):
        import FreeCADGui as Gui

        gui_doc = Gui.getDocument(view_object.Object.Document)
        if gui_doc is not None and not gui_doc.getInEdit():
            gui_doc.setEdit(view_object.Object.Name)
            return True
        if Gui.Control.activeDialog() is not None:
            Gui.Control.closeDialog()
        return self.setEdit(view_object)

    def dumps(self):
        return None

    def loads(self, state):
        return None


class FEMPartAnalysisAdapter:
    """Small analysis-like object that exposes a FEMPart as an analysis group."""

    Add321Constraints = True

    def __init__(self, fem_part):
        self.fem_part = fem_part
        self.Document = fem_part.Document
        self.Name = fem_part.Name
        self.Label = fem_part.Label
        self._extra_group = []

    @property
    def Group(self):
        group = []
        for obj in (
            _fem_part_material_object(self.fem_part),
            getattr(self.fem_part, "mesh", None),
            getattr(self.fem_part, "solver", None),
        ):
            if obj is not None:
                group.append(obj)
        group.extend(_linked_results(self.fem_part))
        visual = getattr(self.fem_part, "visual", None)
        if visual is not None:
            group.append(visual)
        group.extend(obj for obj in self._extra_group if obj is not None)
        return group

    def addObject(self, obj):
        if _is_result_mesh(obj):
            _hide_result_mesh(obj)
            if obj not in self._extra_group:
                self._extra_group.append(obj)
            return [obj]
        if _is_result_object(obj):
            install_result_task_panel_label_fallback()
            _append_linked_result(self.fem_part, obj)
            self._add_to_fem_part_group(obj)
            return [obj]
        if _is_post_pipeline(obj):
            self.fem_part.visual = obj
            _hide_post_pipeline(obj)
            self._add_to_fem_part_group(obj)
            return [obj]
        if obj not in self._extra_group:
            self._extra_group.append(obj)
        return [obj]

    def _add_to_fem_part_group(self, obj):
        if _is_result_object(obj):
            try:
                self.fem_part.ensureResultsFolder().addObject(obj)
            except Exception:
                pass
            return
        try:
            self.fem_part.addObject(obj)
        except Exception:
            pass

    def getObject(self, name):
        for obj in self.Group:
            if getattr(obj, "Name", None) == name:
                return obj
        return self.Document.getObject(name)

    def getObjectsOfType(self, type_id):
        objects = []
        for obj in self.Group:
            try:
                if obj.isDerivedFrom(type_id):
                    objects.append(obj)
            except Exception:
                pass
        return objects


class FEMPartCcxTools:
    """Calculix tools initialized with a FEMPart-backed analysis adapter."""

    def __new__(cls, fem_part, solver):
        from femtools.ccxtools import FemToolsCcx

        class FEMPartCcxToolsAdapter(FemToolsCcx):
            def setup_working_dir(self, param_working_dir=None, create=False):
                pinned_working_dir = getattr(self, "_mbdfem_working_dir", None)
                if param_working_dir is None and pinned_working_dir:
                    param_working_dir = pinned_working_dir
                    create = True

                super().setup_working_dir(param_working_dir, create)
                if param_working_dir is not None:
                    self._mbdfem_working_dir = self.working_dir

            def setup_ccx(self, ccx_binary=None, ccx_binary_sig="CalculiX"):
                super().setup_ccx(ccx_binary, ccx_binary_sig)
                self.ccx_binary = _resolve_ccx_binary(self.ccx_binary)

            def check_prerequisites(self):
                return _remove_auto_321_static_bc_message(
                    super().check_prerequisites(),
                    _fem_mesh_nodes(self.mesh),
                )

            def write_inp_file(self):
                super().write_inp_file()
                self._use_configured_input_basename()
                self.auto_321_constraint_nodes = None
                if self.inp_file_name:
                    gravity = _add_mbd_gravity_to_inp(self.inp_file_name, fem_part)
                    dalembert_loads = _add_mbd_dalembert_loads_to_inp(
                        self.inp_file_name,
                        fem_part,
                    )
                    if gravity is not None or dalembert_loads:
                        _ensure_mbd_density_in_inp(self.inp_file_name, fem_part)
                nodes = _fem_mesh_nodes(self.mesh)
                if self.inp_file_name and nodes:
                    self.auto_321_constraint_nodes = _add_321_constraints_to_inp(
                        self.inp_file_name,
                        nodes,
                    )

            def _use_configured_input_basename(self):
                if not getattr(self, "inp_file_name", None):
                    return
                base_name = getattr(self, "base_name", None)
                working_dir = getattr(self, "working_dir", None)
                if not base_name or not working_dir:
                    return

                desired_inp_file = os.path.join(working_dir, f"{base_name}.inp")
                current_inp_file = self.inp_file_name
                if os.path.normcase(os.path.abspath(current_inp_file)) == os.path.normcase(
                    os.path.abspath(desired_inp_file)
                ):
                    return

                try:
                    os.makedirs(working_dir, exist_ok=True)
                    os.replace(current_inp_file, desired_inp_file)
                    self.inp_file_name = desired_inp_file
                except OSError as exc:
                    import FreeCAD

                    FreeCAD.Console.PrintWarning(
                        f"MbDFEM: unable to rename CalculiX input file to "
                        f"{desired_inp_file}: {exc}\n"
                    )

            def load_results_ccxfrd(self):
                import FreeCAD
                import feminout.importCcxFrdResults as importCcxFrdResults

                frd_result_file = os.path.splitext(self.inp_file_name)[0] + ".frd"
                if not os.path.isfile(frd_result_file):
                    FreeCAD.Console.PrintError(
                        f"FEM: No frd result file found at {frd_result_file}\n"
                    )
                    return

                with _suspend_femgui_active_analysis():
                    importCcxFrdResults.importFrd(
                        frd_result_file,
                        self.analysis,
                        "CCX_",
                        self.solver.AnalysisType,
                    )

                for obj in self.analysis.Group:
                    try:
                        if obj.isDerivedFrom("Fem::FemResultObject"):
                            self.results_present = True
                            break
                    except Exception:
                        pass

        return FEMPartCcxToolsAdapter(FEMPartAnalysisAdapter(fem_part), solver)


def _fem_mesh_nodes(mesh_object):
    try:
        return mesh_object.FemMesh.Nodes
    except Exception:
        return {}


def _fem_mesh_element_ids(mesh_object):
    try:
        fem_mesh = mesh_object.FemMesh
    except Exception:
        return []

    element_ids = []
    for element_kind in ("Volumes", "Faces", "Edges"):
        try:
            element_ids.extend(getattr(fem_mesh, element_kind))
        except Exception:
            pass
    return sorted(set(element_ids))


def _fem_part_material_object(fem_part, create=True):
    source_material = _mbd_mass_marker_material(fem_part)
    if source_material is None:
        return None

    material = _existing_fem_part_material_object(fem_part)
    if material is None and create and source_material is not None:
        try:
            import ObjectsFem

            material = ObjectsFem.makeMaterialSolid(
                fem_part.Document,
                fem_part.Name + "_Material",
            )
            material.Label = f"Material ({fem_part.Label})"
        except Exception:
            material = None
        if material is not None:
            try:
                fem_part.addObject(material)
            except Exception:
                pass

    if material is not None:
        _sync_fem_material_from_mbd_material(material, source_material)
        _remove_from_other_owner_groups(material, fem_part)
    return material


def _existing_fem_part_material_object(fem_part):
    for obj in getattr(fem_part, "Group", []):
        try:
            if obj.isDerivedFrom("App::MaterialObject"):
                return obj
        except Exception:
            pass
        if getattr(obj, "TypeId", None) == "App::MaterialObjectPython":
            return obj
    return None


def _mbd_mass_marker_material(fem_part):
    mbd_part = getattr(fem_part, "mbdItem", None)
    try:
        mass_marker = mbd_part.getMassMarker()
    except Exception:
        mass_marker = None
    if mass_marker is None:
        try:
            mass_marker = mbd_part.ensureMassMarker()
        except Exception:
            mass_marker = None
    if mass_marker is None:
        return None

    try:
        return mass_marker.material
    except Exception:
        return None


def _sync_fem_material_from_mbd_material(material, source_material):
    if source_material is not None:
        try:
            material.Material = source_material
        except Exception:
            pass
    try:
        material.References = []
    except Exception:
        pass


def _remove_from_other_owner_groups(object_, allowed_owner):
    for owner in list(getattr(object_, "InList", [])):
        if owner is allowed_owner:
            continue
        try:
            if hasattr(owner, "removeObject"):
                owner.removeObject(object_)
        except Exception:
            pass
    try:
        install_material_view_provider(object_.ViewObject)
    except Exception:
        pass


def _is_result_mesh(obj):
    try:
        return obj.isDerivedFrom("Fem::FemMeshObject") and obj.Name.endswith("_Results_Mesh")
    except Exception:
        return False


def _hide_result_mesh(obj):
    view_object = getattr(obj, "ViewObject", None)
    if view_object is None:
        return
    try:
        view_object.Visibility = False
    except Exception:
        pass
    try:
        view_object.ShowInTree = False
    except Exception:
        pass


def _hide_post_pipeline(obj):
    view_object = getattr(obj, "ViewObject", None)
    if view_object is None:
        return
    try:
        view_object.ShowInTree = False
    except Exception:
        pass


def _is_result_object(obj):
    try:
        return obj.isDerivedFrom("Fem::FemResultObject")
    except Exception:
        return False


def _is_post_pipeline(obj):
    try:
        return obj.isDerivedFrom("Fem::FemPostPipeline")
    except Exception:
        return False


def _resolve_ccx_binary(ccx_binary):
    """Return an absolute CalculiX binary path for QProcess launches."""
    if not ccx_binary:
        return ccx_binary
    if os.path.isabs(ccx_binary):
        return os.path.normpath(ccx_binary)

    import FreeCAD as App

    ccx_name = os.path.basename(ccx_binary)
    candidates = (
        shutil.which(ccx_binary),
        shutil.which(ccx_name),
        shutil.which("ccx"),
        os.path.join(App.getHomePath(), "bin", ccx_name),
        os.path.join(App.getHomePath(), ccx_name),
    )
    for candidate in candidates:
        if candidate and os.path.exists(candidate):
            return os.path.abspath(candidate)
    return ccx_binary


def _remove_auto_321_static_bc_message(message, nodes):
    if _calculate_321_constraints(nodes) is None:
        return message
    return message.replace(_CCX_STATIC_NO_BC_MESSAGE, "")


@contextlib.contextmanager
def _suspend_femgui_active_analysis():
    """Avoid activating the FEMPart adapter as a stock FEM analysis object."""
    import FreeCAD

    original_set_active_analysis = None
    if FreeCAD.GuiUp:
        try:
            import FemGui

            original_set_active_analysis = FemGui.setActiveAnalysis
            FemGui.setActiveAnalysis = lambda analysis: None
        except Exception:
            original_set_active_analysis = None
    try:
        yield
    finally:
        if original_set_active_analysis is not None:
            FemGui.setActiveAnalysis = original_set_active_analysis


def _add_321_constraints_to_inp(inp_file_name, nodes):
    import FreeCAD as App

    constraints = _calculate_321_constraints(nodes)
    if constraints is None:
        App.Console.PrintWarning(
            "CalculiX 3-2-1 constraints skipped: at least three suitable mesh nodes are needed.\n"
        )
        return None

    with open(inp_file_name, "r", encoding="utf-8") as inp_file:
        content = inp_file.read()

    constraint_nodes = _321_constraint_nodes(nodes, constraints)
    if _321_CONSTRAINT_MARKER in content:
        return constraint_nodes

    insert_at = _find_321_constraint_insert_position(content)
    if insert_at < 0:
        App.Console.PrintWarning(
            "CalculiX 3-2-1 constraints skipped: no *STEP section found in input file.\n"
        )
        return None

    node_xyz, node_yz, node_z = constraints
    node_comments = "".join(
        f"** {label} {node_id}: {_format_node_coordinates(node)}\n"
        for label, node_id, node in constraint_nodes
    )
    constraint_block = (
        "\n{}\n"
        "{}"
        "{}"
        "*BOUNDARY\n"
        "{},1,1,0\n"
        "{},2,2,0\n"
        "{},3,3,0\n"
        "{},2,2,0\n"
        "{},3,3,0\n"
        "{},3,3,0\n"
    ).format(
        _INP_SECTION_SEPARATOR,
        _321_CONSTRAINT_MARKER,
        node_comments,
        node_xyz,
        node_xyz,
        node_xyz,
        node_yz,
        node_yz,
        node_z,
    )

    with open(inp_file_name, "w", encoding="utf-8") as inp_file:
        inp_file.write(content[:insert_at] + constraint_block + content[insert_at:])
    return constraint_nodes


def _321_constraint_nodes(nodes, constraints):
    node_xyz, node_yz, node_z = constraints
    return (
        ("nodeXYZ", node_xyz, nodes[node_xyz]),
        ("nodeYZ", node_yz, nodes[node_yz]),
        ("nodeZ", node_z, nodes[node_z]),
    )


def _format_node_coordinates(node):
    return "x={:.12g}, y={:.12g}, z={:.12g}".format(node.x, node.y, node.z)


def _format_321_constraint_feedback(constraint_nodes):
    if not constraint_nodes:
        return []
    return [
        "Automatic 3-2-1 constraint nodes:",
        *[
            f"{label} {node_id}: {_format_node_coordinates(node)}"
            for label, node_id, node in constraint_nodes
        ],
    ]


def _add_mbd_gravity_to_inp(inp_file_name, fem_part):
    import FreeCAD as App

    gravity = _mbd_gravity_vector(fem_part)
    if gravity is None:
        return None

    magnitude = _vector_magnitude(gravity)
    if magnitude <= _321_CONSTRAINT_TOLERANCE:
        return None

    with open(inp_file_name, "r", encoding="utf-8") as inp_file:
        content = inp_file.read()

    if _MBD_GRAVITY_MARKER in content:
        return gravity

    insert_at = _find_in_step_insert_position(content)
    if insert_at < 0:
        App.Console.PrintWarning(
            "CalculiX MbDAssembly gravity skipped: no *STEP section found in input file.\n"
        )
        return None

    direction = (
        gravity.x / magnitude,
        gravity.y / magnitude,
        gravity.z / magnitude,
    )
    gravity_block = (
        "\n{}\n"
        "{}"
        "*DLOAD\n"
        "Eall,GRAV,{:.13G},{:.13G},{:.13G},{:.13G}\n"
    ).format(
        _INP_SECTION_SEPARATOR,
        _MBD_GRAVITY_MARKER,
        magnitude * _MBD_TO_CCX_GRAVITY_SCALE,
        direction[0],
        direction[1],
        direction[2],
    )

    with open(inp_file_name, "w", encoding="utf-8") as inp_file:
        inp_file.write(content[:insert_at] + gravity_block + content[insert_at:])
    return gravity


def _add_mbd_dalembert_loads_to_inp(inp_file_name, fem_part):
    import FreeCAD as App

    loads = _mbd_dalembert_element_loads(fem_part)
    if not loads:
        return []

    with open(inp_file_name, "r", encoding="utf-8") as inp_file:
        content = inp_file.read()

    if _MBD_DALEMBERT_MARKER in content:
        return loads

    insert_at = _find_in_step_insert_position(content)
    if insert_at < 0:
        App.Console.PrintWarning(
            "CalculiX MbDPart D'Alembert loads skipped: no *STEP section found in input file.\n"
        )
        return []

    load_lines = "".join(
        "{},GRAV,{:.13G},{:.13G},{:.13G},{:.13G}\n".format(
            element_id,
            magnitude * _MBD_TO_CCX_GRAVITY_SCALE,
            direction.x,
            direction.y,
            direction.z,
        )
        for element_id, magnitude, direction in loads
    )
    load_block = (
        "\n{}\n"
        "{}"
        "*DLOAD\n"
        "{}"
    ).format(
        _INP_SECTION_SEPARATOR,
        _MBD_DALEMBERT_MARKER,
        load_lines,
    )

    with open(inp_file_name, "w", encoding="utf-8") as inp_file:
        inp_file.write(content[:insert_at] + load_block + content[insert_at:])
    return loads


def _ensure_mbd_density_in_inp(inp_file_name, fem_part):
    density = _mbd_density_in_tonne_per_mm3(fem_part)
    if density is None:
        return False

    material = _fem_part_material_object(fem_part, create=False)
    material_name = getattr(material, "Name", None)
    if not material_name:
        return False

    with open(inp_file_name, "r", encoding="utf-8") as inp_file:
        content = inp_file.read()

    material_at = _find_material_section(content, material_name)
    if material_at < 0:
        return False

    next_material_at = content.find("\n*MATERIAL", material_at + 1)
    section_end = next_material_at if next_material_at >= 0 else len(content)
    section = content[material_at:section_end]
    if "\n*DENSITY" in section.upper():
        return False

    insert_at = _find_material_density_insert_position(content, material_at, section_end)
    density_block = "*DENSITY\n{:.13G}\n".format(density)
    with open(inp_file_name, "w", encoding="utf-8") as inp_file:
        inp_file.write(content[:insert_at] + density_block + content[insert_at:])
    return True


def _find_material_section(content, material_name):
    target = material_name.upper()
    search_at = 0
    while True:
        material_at = content.upper().find("*MATERIAL", search_at)
        if material_at < 0:
            return -1
        line_end = content.find("\n", material_at)
        if line_end < 0:
            line_end = len(content)
        line = content[material_at:line_end].upper()
        if "NAME=" in line and line.split("NAME=", 1)[1].split(",", 1)[0].strip() == target:
            return material_at
        search_at = line_end


def _find_material_density_insert_position(content, material_at, section_end):
    elastic_at = content.upper().find("\n*ELASTIC", material_at, section_end)
    if elastic_at < 0:
        line_end = content.find("\n", material_at)
        return len(content) if line_end < 0 else line_end + 1

    next_keyword_at = content.find("\n*", elastic_at + 1, section_end)
    if next_keyword_at >= 0:
        return next_keyword_at + 1
    return section_end


def _mbd_density_in_tonne_per_mm3(fem_part):
    density = _material_density_in_tonne_per_mm3(
        _fem_part_material_object(fem_part, create=False)
    )
    if density is not None:
        return density

    mbd_part = getattr(fem_part, "mbdItem", None)
    try:
        mass_marker = mbd_part.getMassMarker()
    except Exception:
        mass_marker = None
    if mass_marker is None:
        return None

    density = _material_density_in_tonne_per_mm3(mass_marker)
    if density is not None:
        return density

    try:
        return mass_marker.densityInKgPerMm3() * 0.001
    except Exception:
        return None


def _material_density_in_tonne_per_mm3(material_owner):
    try:
        material = material_owner.Material
    except Exception:
        material = None

    if isinstance(material, dict) and material.get("Density"):
        try:
            import FreeCAD as App

            return App.Units.Quantity(material["Density"]).getValueAs("t/mm^3").Value
        except Exception:
            pass

    try:
        physical_density = material_owner.material.getPhysicalValue("Density")
    except Exception:
        physical_density = None
    if physical_density:
        try:
            import FreeCAD as App

            return App.Units.Quantity(str(physical_density)).getValueAs("t/mm^3").Value
        except Exception:
            pass

    return None


def _mbd_dalembert_element_loads(fem_part):
    mbd_part = getattr(fem_part, "mbdItem", None)
    mesh_object = getattr(fem_part, "mesh", None)
    if mbd_part is None or mesh_object is None:
        return []

    loads = []
    for element_id in _fem_mesh_element_ids(mesh_object):
        try:
            centroid = fem_part.elementCentroidLocal(int(element_id))
            acceleration = mbd_part.globalAccelerationOf(
                _scaled_vector(centroid, _CAD_LENGTH_TO_MBD_LENGTH_SCALE)
            )
        except Exception:
            continue

        inertial_acceleration = _vector_in_fem_part_coordinates(
            fem_part,
            _scaled_vector(acceleration, -1.0),
        )
        magnitude = _vector_magnitude(inertial_acceleration)
        if magnitude <= _321_CONSTRAINT_TOLERANCE:
            direction = _unit_x_vector()
        else:
            direction = _scaled_vector(inertial_acceleration, 1.0 / magnitude)
        loads.append(
            (
                element_id,
                magnitude,
                direction,
            )
        )
    return loads


def _unit_x_vector():
    import FreeCAD as App

    return App.Vector(1, 0, 0)


def _scaled_vector(vector, scale):
    import FreeCAD as App

    return App.Vector(vector.x * scale, vector.y * scale, vector.z * scale)


def _vector_magnitude(vector):
    return math.sqrt(vector.x * vector.x + vector.y * vector.y + vector.z * vector.z)


def _mbd_gravity_vector(fem_part):
    assembly = _owning_mbd_assembly(fem_part)
    if assembly is None:
        return None

    try:
        gravity_object = assembly.getGravity()
    except Exception:
        gravity_object = getattr(assembly, "gravity", None)
    if gravity_object is None:
        return None

    try:
        gravity = gravity_object.gravity
    except Exception:
        return None

    assembly_rotation = _global_rotation(assembly)
    gravity_global = assembly_rotation.multVec(gravity)
    return _vector_in_fem_part_coordinates(fem_part, gravity_global)


def _vector_in_fem_part_coordinates(fem_part, vector):
    mbd_part = getattr(fem_part, "mbdItem", None)
    local_reference = mbd_part if mbd_part is not None else fem_part
    return _global_rotation(local_reference).inverted().multVec(vector)


def _global_rotation(obj):
    try:
        return obj.getGlobalPlacement().Rotation
    except Exception:
        return obj.Placement.Rotation


def _owning_mbd_assembly(fem_part):
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


def _find_321_constraint_insert_position(content):
    return _find_in_step_insert_position(content)


def _find_in_step_insert_position(content):
    step_at = content.find("*STEP")
    if step_at < 0:
        return -1

    next_section_at = content.find("\n" + _INP_SECTION_SEPARATOR + "\n** ", step_at + 1)
    if next_section_at >= 0:
        return next_section_at

    end_step_at = content.find("*END STEP", step_at + 1)
    if end_step_at >= 0:
        return end_step_at

    return len(content)


def _calculate_321_constraints(nodes, tolerance=_321_CONSTRAINT_TOLERANCE):
    if len(nodes) < 3:
        return None

    node_items = list(nodes.items())
    min_x = min(node.x for _, node in node_items)
    min_y = min(node.y for _, node in node_items)
    min_z = min(node.z for _, node in node_items)

    def distance_to_min_corner(item):
        node_id, node = item
        return (
            (node.x - min_x) ** 2 + (node.y - min_y) ** 2 + (node.z - min_z) ** 2,
            node_id,
        )

    node_xyz, xyz = min(node_items, key=distance_to_min_corner)
    line_x = _select_line_x(node_items, node_xyz, xyz, tolerance)
    if line_x is None:
        return None

    node_yz, _, line_length = line_x
    node_z = _select_node_z(node_items, node_xyz, xyz, node_yz, line_length, tolerance)
    if node_z is None:
        return None

    return node_xyz, node_yz, node_z


def _select_line_x(node_items, node_xyz, xyz, tolerance):
    best = None
    for node_id, node in node_items:
        if node_id == node_xyz:
            continue

        dx = node.x - xyz.x
        dy = node.y - xyz.y
        dz = node.z - xyz.z
        length = math.sqrt(dx * dx + dy * dy + dz * dz)
        if length == 0:
            continue

        direction_cosine = dx / length
        if (
            best is None
            or direction_cosine > best[1] + tolerance
            or (
                abs(direction_cosine - best[1]) <= tolerance
                and (
                    length > best[2] + tolerance
                    or (abs(length - best[2]) <= tolerance and node_id < best[0])
                )
            )
        ):
            best = (node_id, direction_cosine, length)

    return best


def _select_node_z(node_items, node_xyz, xyz, node_yz, line_length, tolerance):
    yz = next(node for node_id, node in node_items if node_id == node_yz)
    line_unit = (
        (yz.x - xyz.x) / line_length,
        (yz.y - xyz.y) / line_length,
        (yz.z - xyz.z) / line_length,
    )

    best = None
    for node_id, node in node_items:
        if node_id in (node_xyz, node_yz):
            continue

        vx = node.x - xyz.x
        vy = node.y - xyz.y
        vz = node.z - xyz.z
        projected_length = (
            vx * line_unit[0] + vy * line_unit[1] + vz * line_unit[2]
        )
        px = projected_length * line_unit[0]
        py = projected_length * line_unit[1]
        pz = projected_length * line_unit[2]
        dx = vx - px
        dy = vy - py
        dz = vz - pz
        distance = math.sqrt(dx * dx + dy * dy + dz * dz)
        if distance == 0:
            continue

        absolute_direction_cosine = abs(dz / distance)
        if (
            best is None
            or absolute_direction_cosine < best[1] - tolerance
            or (
                abs(absolute_direction_cosine - best[1]) <= tolerance
                and (
                    distance > best[2] + tolerance
                    or (abs(distance - best[2]) <= tolerance and node_id < best[0])
                )
            )
        ):
            best = (node_id, absolute_direction_cosine, distance)

    if best is None:
        return None

    return best[0]


class FEMPartSolverTaskPanel:
    """Calculix task panel using FEMPart material, mesh, and solver as analysis members."""

    def __init__(self, fem_part, solver_object):
        from PySide import QtWidgets
        import FreeCAD as App

        self.fem_part = fem_part
        self.solver_object = solver_object
        self.fea = FEMPartCcxTools(fem_part, solver_object)
        self._set_fea_state_directory(0)
        try:
            self.fea.setup_ccx()
        except FileNotFoundError as exc:
            App.Console.PrintWarning(exc.args[0])

        self.fem_console_message = ""

        self.form = QtWidgets.QWidget()
        self.form.setWindowTitle("FEMPart Calculix")
        self.form.setMinimumWidth(340)

        layout = QtWidgets.QVBoxLayout(self.form)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        self._append_solving_panel(layout)

        header = QtWidgets.QGroupBox("FEMPart")
        header_layout = QtWidgets.QFormLayout(header)
        self.fem_part_label = _read_only_value(getattr(fem_part, "Label", ""))
        self.mbd_part_label = _read_only_value(getattr(getattr(fem_part, "mbdItem", None), "Label", ""))
        header_layout.addRow("FEMPart", self.fem_part_label)
        header_layout.addRow("MbDPart", self.mbd_part_label)
        layout.addWidget(header)

        state_group = QtWidgets.QGroupBox("State")
        state_layout = QtWidgets.QFormLayout(state_group)
        self.state_spin = QtWidgets.QSpinBox()
        self.state_spin.setRange(0, max(_solver_state_count(fem_part) - 1, 0))
        self.time_label = _read_only_value(_solver_state_time_text(fem_part, 0))
        self.working_dir_edit = _read_only_value(getattr(self.fea, "working_dir", ""))
        self.base_name_edit = _read_only_value(getattr(self.fea, "base_name", ""))
        state_layout.addRow("State", self.state_spin)
        state_layout.addRow("Time", self.time_label)
        state_layout.addRow("Working directory", self.working_dir_edit)
        state_layout.addRow("Base name", self.base_name_edit)
        layout.addWidget(state_group)

        prereq_group = QtWidgets.QGroupBox("Prerequisites")
        prereq_layout = QtWidgets.QFormLayout(prereq_group)
        self.mesh_status = QtWidgets.QLabel()
        self.material_status = QtWidgets.QLabel()
        self.solver_status = QtWidgets.QLabel()
        prereq_layout.addRow("Mesh", self.mesh_status)
        prereq_layout.addRow("Material", self.material_status)
        prereq_layout.addRow("CalculiX", self.solver_status)
        layout.addWidget(prereq_group)

        actions = QtWidgets.QGroupBox("Actions")
        action_layout = QtWidgets.QGridLayout(actions)
        self.create_mesh_button = QtWidgets.QPushButton("Create Mesh")
        self.check_button = QtWidgets.QPushButton("Check")
        self.write_inp_button = QtWidgets.QPushButton("Write .inp")
        self.run_button = QtWidgets.QPushButton("Run CalculiX")
        self.solve_state_button = QtWidgets.QPushButton("Solve State")
        action_layout.addWidget(self.create_mesh_button, 0, 0)
        action_layout.addWidget(self.check_button, 0, 1)
        action_layout.addWidget(self.write_inp_button, 1, 0)
        action_layout.addWidget(self.run_button, 1, 1)
        action_layout.addWidget(self.solve_state_button, 2, 0, 1, 2)
        layout.addWidget(actions)

        self.log = QtWidgets.QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumBlockCount(400)
        self.log.setMinimumHeight(120)
        layout.addWidget(self.log)
        layout.addStretch(1)

        self.state_spin.valueChanged.connect(self._state_changed)
        self.create_mesh_button.clicked.connect(self._create_mesh)
        self.check_button.clicked.connect(self.check_prerequisites_helper)
        self.write_inp_button.clicked.connect(self.write_input_file_handler)
        self.run_button.clicked.connect(self.runCalculix)
        self.solve_state_button.clicked.connect(self._solve_state)
        self.solve_previous_button.clicked.connect(self._previous_solve_state)
        self.solve_next_button.clicked.connect(self._next_solve_state)
        self.solve_slider.valueChanged.connect(self._set_solve_state)
        self.solve_state_spin.valueChanged.connect(self._set_solve_state)
        self.solve_start_state_spin.valueChanged.connect(self._refresh_solving_panel)
        self.solve_end_state_spin.valueChanged.connect(self._refresh_solving_panel)
        self.start_solving_button.clicked.connect(self._start_solving)
        self.stop_solving_button.clicked.connect(self._stop_solving)
        self._stop_solving_requested = False
        self._configure_solving_panel()
        self._refresh()

    def _append_solving_panel(self, layout):
        from PySide import QtCore, QtWidgets

        solved_group = QtWidgets.QGroupBox("Solved")
        solved_layout = QtWidgets.QVBoxLayout(solved_group)
        self.solve_status_label = QtWidgets.QLabel()
        self.solve_status_label.setWordWrap(True)
        solved_layout.addWidget(self.solve_status_label)
        layout.addWidget(solved_group)

        current_group = QtWidgets.QGroupBox("Current State")
        current_layout = QtWidgets.QVBoxLayout(current_group)
        self.solve_slider = QtWidgets.QSlider(QtCore.Qt.Horizontal)
        current_layout.addWidget(self.solve_slider)

        state_layout = QtWidgets.QHBoxLayout()
        self.solve_previous_button = QtWidgets.QToolButton()
        self.solve_previous_button.setText("<")
        self.solve_previous_button.setToolTip("Previous state")
        self.solve_next_button = QtWidgets.QToolButton()
        self.solve_next_button.setText(">")
        self.solve_next_button.setToolTip("Next state")
        state_layout.addWidget(self.solve_previous_button)
        state_layout.addWidget(QtWidgets.QLabel("State:"))
        self.solve_state_spin = QtWidgets.QSpinBox()
        state_layout.addWidget(self.solve_state_spin)
        self.solve_state_count_label = QtWidgets.QLabel()
        state_layout.addWidget(self.solve_state_count_label)
        state_layout.addStretch()
        state_layout.addWidget(QtWidgets.QLabel("Time:"))
        self.solve_time_label = QtWidgets.QLabel()
        state_layout.addWidget(self.solve_time_label)
        state_layout.addWidget(self.solve_next_button)
        current_layout.addLayout(state_layout)
        layout.addWidget(current_group)

        range_group = QtWidgets.QGroupBox("Solve Range")
        range_layout = QtWidgets.QVBoxLayout(range_group)

        start_layout = QtWidgets.QHBoxLayout()
        start_layout.addWidget(QtWidgets.QLabel("Start State:"))
        self.solve_start_state_spin = QtWidgets.QSpinBox()
        start_layout.addWidget(self.solve_start_state_spin)
        self.solve_start_state_count_label = QtWidgets.QLabel()
        start_layout.addWidget(self.solve_start_state_count_label)
        start_layout.addStretch()
        start_layout.addWidget(QtWidgets.QLabel("Time:"))
        self.solve_start_time_label = QtWidgets.QLabel()
        start_layout.addWidget(self.solve_start_time_label)
        range_layout.addLayout(start_layout)

        end_layout = QtWidgets.QHBoxLayout()
        end_layout.addWidget(QtWidgets.QLabel("End State:"))
        self.solve_end_state_spin = QtWidgets.QSpinBox()
        end_layout.addWidget(self.solve_end_state_spin)
        self.solve_end_state_count_label = QtWidgets.QLabel()
        end_layout.addWidget(self.solve_end_state_count_label)
        end_layout.addStretch()
        end_layout.addWidget(QtWidgets.QLabel("Time:"))
        self.solve_end_time_label = QtWidgets.QLabel()
        end_layout.addWidget(self.solve_end_time_label)
        range_layout.addLayout(end_layout)
        layout.addWidget(range_group)

        solving_group = QtWidgets.QGroupBox("Solving")
        solving_layout = QtWidgets.QHBoxLayout(solving_group)
        self.start_solving_button = QtWidgets.QPushButton("Start Solving")
        self.stop_solving_button = QtWidgets.QPushButton("Stop Solving")
        solving_layout.addWidget(self.start_solving_button)
        solving_layout.addWidget(self.stop_solving_button)
        layout.addWidget(solving_group)

    def getStandardButtons(self):
        from PySide import QtGui

        return QtGui.QDialogButtonBox.Close

    def reject(self):
        import FreeCADGui as Gui

        self._stop_solving()
        try:
            Gui.ActiveDocument.resetEdit()
        except Exception:
            pass
        Gui.Control.closeDialog()
        return True

    def femConsoleMessage(self, message):
        self.fem_console_message += str(message) + "\n"
        self.log.appendPlainText(str(message))

    def _state_changed(self, state_index):
        self._set_fea_state_directory(state_index)
        self.time_label.setText(_solver_state_time_text(self.fem_part, state_index))
        self._refresh()

    def _set_fea_state_directory(self, state_index):
        import FreeCADMbDBackend

        working_dir = FreeCADMbDBackend.default_calculix_working_dir(
            self.fem_part,
            state_index,
        )
        self.fea.setup_working_dir(str(working_dir), create=True)
        self.fea.set_base_name(FreeCADMbDBackend.CALCULIX_BASE_NAME)

    def _configure_solving_panel(self):
        count = _solver_state_count(self.fem_part)
        maximum = max(count - 1, 0)
        self._updating_solving_panel = True
        try:
            self.solve_slider.setRange(0, maximum)
            self.solve_state_spin.setRange(0, maximum)
            self.solve_start_state_spin.setRange(0, maximum)
            self.solve_end_state_spin.setRange(0, maximum)
            self.solve_start_state_spin.setValue(0)
            self.solve_end_state_spin.setValue(maximum)
        finally:
            self._updating_solving_panel = False

        enabled = count > 0
        for widget in (
            self.solve_previous_button,
            self.solve_next_button,
            self.solve_slider,
            self.solve_state_spin,
            self.solve_start_state_spin,
            self.solve_end_state_spin,
            self.start_solving_button,
        ):
            widget.setEnabled(enabled)
        self.stop_solving_button.setEnabled(False)
        self._refresh_solving_panel()

    def _refresh_solving_panel(self):
        import FreeCADMbDFEMResultsPanel

        count = _solver_state_count(self.fem_part)
        maximum = max(count - 1, 0)
        solved = len(
            {
                FreeCADMbDFEMResultsPanel._result_state_index(result, fallback)
                for fallback, result in enumerate(_linked_results(self.fem_part))
            }
        )
        if count == 0:
            self.solve_status_label.setText("No MbDAssembly state series found.")
        else:
            self.solve_status_label.setText(
                f"{self.fem_part.Label}: {solved} / {count} states solved"
            )

        self.solve_state_count_label.setText(f"/ {maximum}")
        self.solve_start_state_count_label.setText(f"/ {maximum}")
        self.solve_end_state_count_label.setText(f"/ {maximum}")
        self.solve_time_label.setText(
            _solver_state_time_text(self.fem_part, self.solve_state_spin.value())
        )
        self.solve_start_time_label.setText(
            _solver_state_time_text(self.fem_part, self.solve_start_state_spin.value())
        )
        self.solve_end_time_label.setText(
            _solver_state_time_text(self.fem_part, self.solve_end_state_spin.value())
        )

    def _set_solve_state(self, value):
        if self._updating_solving_panel:
            return
        self._updating_solving_panel = True
        try:
            self.solve_slider.setValue(int(value))
            self.solve_state_spin.setValue(int(value))
            self.state_spin.setValue(int(value))
        finally:
            self._updating_solving_panel = False
        self._refresh_solving_panel()

    def _previous_solve_state(self):
        self._set_solve_state(
            max(self.solve_state_spin.value() - 1, self.solve_state_spin.minimum())
        )

    def _next_solve_state(self):
        self._set_solve_state(
            min(self.solve_state_spin.value() + 1, self.solve_state_spin.maximum())
        )

    def _solving_range_indices(self):
        count = _solver_state_count(self.fem_part)
        if count == 0:
            return []
        start = min(self.solve_start_state_spin.value(), self.solve_end_state_spin.value())
        end = max(self.solve_start_state_spin.value(), self.solve_end_state_spin.value())
        return list(range(start, end + 1))

    def _stop_solving(self):
        self._stop_solving_requested = True

    def _refresh(self):
        mesh = getattr(self.fem_part, "mesh", None)
        material = _fem_part_material_object(self.fem_part, create=False)
        ccx_binary = getattr(self.fea, "ccx_binary", "")
        self.mesh_status.setText("Ready" if mesh is not None else "Missing")
        self.material_status.setText("Ready" if material is not None else "Missing")
        self.solver_status.setText(ccx_binary if ccx_binary else "Not found")
        self.working_dir_edit.setText(str(getattr(self.fea, "working_dir", "")))
        self.base_name_edit.setText(str(getattr(self.fea, "base_name", "")))
        self._refresh_solving_panel()

    def _create_mesh(self):
        try:
            import InitGui

            InitGui.CreateFEMPartMeshCommand().createMesh(self.fem_part)
            self.fem_part.Document.recompute()
            self.femConsoleMessage("Mesh created.")
        except Exception as exc:
            self.femConsoleMessage(f"Mesh creation failed: {exc}")
        self._refresh()

    def write_input_file_handler(self):
        try:
            self.fea.update_objects()
            self.fea.write_inp_file()
            self.femConsoleMessage(f"Wrote input file: {self.fea.inp_file_name}")
        except Exception as exc:
            self.femConsoleMessage(f"Write .inp failed: {exc}")
            return
        constraint_nodes = getattr(self.fea, "auto_321_constraint_nodes", None)
        if self.fea.inp_file_name and constraint_nodes:
            for line in _format_321_constraint_feedback(constraint_nodes):
                self.femConsoleMessage(line)

    def check_prerequisites_helper(self):
        from PySide import QtGui

        self.femConsoleMessage("Checking prerequisites...")
        self.fea.update_objects()
        message = _remove_auto_321_static_bc_message(
            self.fea.check_prerequisites(),
            _fem_mesh_nodes(self.fea.mesh),
        )
        if message:
            QtGui.QMessageBox.critical(None, "Missing prerequisite(s)", message)
            self.femConsoleMessage(message)
            self._refresh()
            return False
        self.femConsoleMessage("Prerequisites ready.")
        self._refresh()
        return True

    def runCalculix(self):
        if not self.check_prerequisites_helper():
            return False
        try:
            self.femConsoleMessage("Running CalculiX...")
            result = self.fea.run()
            self.femConsoleMessage("CalculiX run finished." if result else "CalculiX run failed.")
            self._refresh()
            return bool(result)
        except Exception as exc:
            self.femConsoleMessage(f"CalculiX run failed: {exc}")
            self._refresh()
            return False

    def _solve_state(self):
        try:
            import FreeCADMbDFEMResultsPanel

            state_index = self.state_spin.value()
            result = FreeCADMbDFEMResultsPanel.solve_fem_part_state(self.fem_part, state_index)
            self.femConsoleMessage(f"Solved state {state_index}: {result.Label}")
        except Exception as exc:
            self.femConsoleMessage(f"Solve state failed: {exc}")
        self._refresh()

    def _start_solving(self):
        indices = self._solving_range_indices()
        if not indices:
            self.femConsoleMessage("No states in the selected range.")
            return False

        self._stop_solving_requested = False
        self.start_solving_button.setEnabled(False)
        self.stop_solving_button.setEnabled(True)
        try:
            from PySide import QtWidgets
            import FreeCADMbDFEMResultsPanel

            for state_index in indices:
                if self._stop_solving_requested:
                    self.femConsoleMessage("Solving stopped.")
                    return False
                self._set_solve_state(state_index)
                self.femConsoleMessage(f"Solving state {state_index}...")
                QtWidgets.QApplication.processEvents()
                result = FreeCADMbDFEMResultsPanel.solve_fem_part_state(
                    self.fem_part,
                    state_index,
                )
                self.femConsoleMessage(f"Solved state {state_index}: {result.Label}")
            self._refresh()
            return True
        except Exception as exc:
            self.femConsoleMessage(f"Start solving failed: {exc}")
            self._refresh()
            return False
        finally:
            self.start_solving_button.setEnabled(_solver_state_count(self.fem_part) > 0)
            self.stop_solving_button.setEnabled(False)


def fem_part_for_solver(solver):
    document = getattr(solver, "Document", None)
    if document is None:
        return None
    for obj in getattr(document, "Objects", []):
        try:
            if obj.isDerivedFrom("MbDFEM::FEMPart") and getattr(obj, "solver", None) is solver:
                return obj
        except Exception:
            pass
    return None


def fem_part_for_result(result):
    document = getattr(result, "Document", None)
    if document is None:
        return None
    for obj in getattr(document, "Objects", []):
        try:
            if obj.isDerivedFrom("MbDFEM::FEMPart") and result in _linked_results(obj):
                return obj
        except Exception:
            pass
    return None


class FEMPartMeshViewProvider:
    """View provider for FEMPart-owned Gmsh meshes."""

    def __init__(self, view_object):
        from femviewprovider import view_mesh_gmsh

        view_mesh_gmsh.VPMeshGmsh(view_object)
        self.attach(view_object)

    def attach(self, view_object):
        self.ViewObject = view_object
        self.Object = view_object.Object
        view_object.Proxy = self

    def __getattr__(self, name):
        from femviewprovider import view_mesh_gmsh

        delegate = view_mesh_gmsh.VPMeshGmsh(self.ViewObject)
        delegate.attach(self.ViewObject)
        self.ViewObject.Proxy = self
        return getattr(delegate, name)

    def getIcon(self):
        return ":/icons/FEM_MeshGmshFromShape.svg"

    def claimChildren(self):
        shape_child = []
        if getattr(self.Object, "Shape", None) is not None:
            shape_child = [self.Object.Shape]
        return shape_child + self.Object.MeshRefinementList + self.Object.MeshGroupList

    def dumps(self):
        return None

    def loads(self, state):
        return None


def install_material_view_provider(view_object):
    if view_object is not None:
        FEMPartMaterialViewProvider(view_object)


def install_solver_view_provider(view_object):
    if view_object is not None:
        FEMPartSolverViewProvider(view_object)


def install_mesh_view_provider(view_object):
    return None


def refresh_view_providers(document=None):
    import FreeCAD as App

    install_solver_task_panel_close_fallback()

    documents = [document] if document is not None else list(App.listDocuments().values())
    for doc in documents:
        for obj in getattr(doc, "Objects", []):
            try:
                is_fem_part = obj.isDerivedFrom("MbDFEM::FEMPart")
            except Exception:
                is_fem_part = False
            if not is_fem_part:
                continue

            material = _fem_part_material_object(obj, create=False)
            if material is not None and getattr(material, "ViewObject", None) is not None:
                install_material_view_provider(material.ViewObject)
                if getattr(material, "References", []):
                    material.References = []

            solver = getattr(obj, "solver", None)
            if solver is not None and getattr(solver, "ViewObject", None) is not None:
                install_solver_view_provider(solver.ViewObject)

            mesh = getattr(obj, "mesh", None)
            if mesh is not None and mesh not in getattr(obj, "Group", []):
                try:
                    obj.addObject(mesh)
                except Exception:
                    pass

            for result in _linked_results(obj):
                result_mesh = getattr(result, "Mesh", None)
                if result_mesh is not None:
                    _hide_result_mesh(result_mesh)

            try:
                obj.synchronizeResultsFolder()
            except Exception:
                pass
            visual = getattr(obj, "visual", None)
            if visual is not None:
                _hide_post_pipeline(visual)
            if visual is not None and visual not in getattr(obj, "Group", []):
                try:
                    obj.addObject(visual)
                except Exception:
                    pass


class FEMPartViewProviderObserver:
    _refreshing = False

    def _refresh(self, document):
        if self._refreshing or document is None:
            return
        self._refreshing = True
        try:
            refresh_view_providers(document)
        finally:
            self._refreshing = False

    def slotActivateDocument(self, document):
        self._refresh(document)

    def slotRecomputedDocument(self, document):
        self._refresh(document)

    def slotCreatedObject(self, obj):
        self._refresh(getattr(obj, "Document", None))

    def slotChangedObject(self, obj, prop):
        if prop in {"mbdItem", "solver", "results", "visual"}:
            self._refresh(getattr(obj, "Document", None))


_observer = None


def install_observer():
    import FreeCAD as App

    install_solver_task_panel_close_fallback()

    global _observer
    try:
        if _observer is not None:
            App.removeDocumentObserver(_observer)
    except Exception:
        pass
    _observer = FEMPartViewProviderObserver()
    App.addDocumentObserver(_observer)
