# SPDX-License-Identifier: LGPL-2.1-or-later

"""MbDFEM-local view providers for FEM objects owned by FEMPart."""


from femtaskpanels import task_material_common
from femtaskpanels import task_solver_ccxtools

import contextlib
import math
import os
import shutil


_321_CONSTRAINT_TOLERANCE = 1.0e-9
_321_CONSTRAINT_MARKER = "** Automatic 3-2-1 constraints\n"
_CCX_STATIC_NO_BC_MESSAGE = "Static analysis: No mechanical boundary conditions defined.\n"
_INP_SECTION_SEPARATOR = 59 * "*"
_original_solver_reject = None


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


class FEMPartMaterialTaskPanel(task_material_common._TaskPanel):
    """FEM material editor without a geometry selector."""

    def __init__(self, obj):
        super().__init__(obj)
        self.form = [self.parameterWidget]

    def accept(self):
        self.obj.Material = self.material
        self.obj.UUID = self.uuid
        self.obj.References = []
        try:
            self.selectionWidget.finish_selection()
        except Exception:
            pass
        gui_doc = self.obj.ViewObject.Document
        gui_doc.Document.recompute()
        gui_doc.resetEdit()
        gui_doc.Document.commitTransaction()
        return True

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
            getattr(self.fem_part, "material", None),
            getattr(self.fem_part, "mesh", None),
            getattr(self.fem_part, "solver", None),
        ):
            if obj is not None:
                group.append(obj)
        group.extend(obj for obj in self._extra_group if obj is not None)
        return group

    def addObject(self, obj):
        if obj not in self._extra_group:
            self._extra_group.append(obj)
        try:
            self.fem_part.addObject(obj)
        except Exception:
            pass
        return [obj]

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
                nodes = _fem_mesh_nodes(self.mesh)
                if self.inp_file_name and nodes:
                    _add_321_constraints_to_inp(
                        self.inp_file_name,
                        nodes,
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
        return

    with open(inp_file_name, "r", encoding="utf-8") as inp_file:
        content = inp_file.read()

    if _321_CONSTRAINT_MARKER in content:
        return

    insert_at = _find_321_constraint_insert_position(content)
    if insert_at < 0:
        App.Console.PrintWarning(
            "CalculiX 3-2-1 constraints skipped: no *STEP section found in input file.\n"
        )
        return

    node_xyz, node_yz, node_z = constraints
    constraint_block = (
        "\n{}\n"
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
        node_xyz,
        node_xyz,
        node_xyz,
        node_yz,
        node_yz,
        node_z,
    )

    with open(inp_file_name, "w", encoding="utf-8") as inp_file:
        inp_file.write(content[:insert_at] + constraint_block + content[insert_at:])


def _find_321_constraint_insert_position(content):
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

        direction_cosine = dz / distance
        if (
            best is None
            or direction_cosine < best[1] - tolerance
            or (
                abs(direction_cosine - best[1]) <= tolerance
                and (
                    distance > best[2] + tolerance
                    or (abs(distance - best[2]) <= tolerance and node_id < best[0])
                )
            )
        ):
            best = (node_id, direction_cosine, distance)

    if best is None:
        return None

    return best[0]


class FEMPartSolverTaskPanel(task_solver_ccxtools._TaskPanel):
    """Calculix task panel using FEMPart material, mesh, and solver as analysis members."""

    def __init__(self, fem_part, solver_object):
        import time

        from PySide import QtCore
        import FreeCAD
        import FreeCADGui

        self.form = FreeCADGui.PySideUic.loadUi(
            FreeCAD.getHomePath() + "Mod/Fem/Resources/ui/SolverCcxTools.ui"
        )

        self.fea = FEMPartCcxTools(fem_part, solver_object)
        self.fea.setup_working_dir()
        try:
            self.fea.setup_ccx()
        except FileNotFoundError as exc:
            FreeCAD.Console.PrintWarning(exc.args[0])

        self.Calculix = QtCore.QProcess()
        self.Timer = QtCore.QTimer()
        self.Timer.start(300)

        self.fem_console_message = ""
        self.CCX_pipeline = None
        self.CCX_mesh_visibility = False

        ccx_mesh = self.fea.analysis.Document.getObject("CCX_Results_Mesh")
        if ccx_mesh is not None:
            self.CCX_mesh_visibility = ccx_mesh.ViewObject.Visibility

        QtCore.QObject.connect(
            self.form.tb_choose_working_dir,
            QtCore.SIGNAL("clicked()"),
            self.choose_working_dir,
        )
        QtCore.QObject.connect(
            self.form.pb_write_inp,
            QtCore.SIGNAL("clicked()"),
            self.write_input_file_handler,
        )
        QtCore.QObject.connect(
            self.form.pb_edit_inp,
            QtCore.SIGNAL("clicked()"),
            self.editCalculixInputFile,
        )
        QtCore.QObject.connect(self.form.pb_run_ccx, QtCore.SIGNAL("clicked()"), self.stopCalculix)
        QtCore.QObject.connect(self.form.pb_run_ccx, QtCore.SIGNAL("clicked()"), self.runCalculix)
        QtCore.QObject.connect(
            self.form.rb_static_analysis,
            QtCore.SIGNAL("clicked()"),
            self.select_static_analysis,
        )
        QtCore.QObject.connect(
            self.form.rb_frequency_analysis,
            QtCore.SIGNAL("clicked()"),
            self.select_frequency_analysis,
        )
        QtCore.QObject.connect(
            self.form.rb_thermomech_analysis,
            QtCore.SIGNAL("clicked()"),
            self.select_thermomech_analysis,
        )
        QtCore.QObject.connect(
            self.form.rb_check_mesh,
            QtCore.SIGNAL("clicked()"),
            self.select_check_mesh,
        )
        QtCore.QObject.connect(
            self.form.rb_buckling_analysis,
            QtCore.SIGNAL("clicked()"),
            self.select_buckling_analysis,
        )
        QtCore.QObject.connect(self.Calculix, QtCore.SIGNAL("started()"), self.calculixStarted)
        QtCore.QObject.connect(
            self.Calculix,
            QtCore.SIGNAL("stateChanged(QProcess::ProcessState)"),
            self.calculixStateChanged,
        )
        QtCore.QObject.connect(
            self.Calculix,
            QtCore.SIGNAL("error(QProcess::ProcessError)"),
            self.calculixError,
        )
        QtCore.QObject.connect(
            self.Calculix,
            QtCore.SIGNAL("finished(int, QProcess::ExitStatus)"),
            self.calculixFinished,
        )
        QtCore.QObject.connect(self.Timer, QtCore.SIGNAL("timeout()"), self.UpdateText)

        self.Start = time.time()
        self.update()

    def reject(self):
        import FreeCADGui as Gui

        Gui.ActiveDocument.resetEdit()
        Gui.Control.closeDialog()
        return True

    def check_prerequisites_helper(self):
        import time

        from PySide import QtGui

        self.Start = time.time()
        self.femConsoleMessage("Check dependencies...")
        self.form.l_time.setText(f"Time: {time.time() - self.Start:4.1f}: ")

        self.fea.update_objects()
        message = _remove_auto_321_static_bc_message(
            self.fea.check_prerequisites(),
            _fem_mesh_nodes(self.fea.mesh),
        )
        if message:
            QtGui.QMessageBox.critical(None, "Missing prerequisite(s)", message)
            return False
        return True


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

            material = getattr(obj, "material", None)
            if material is not None and getattr(material, "ViewObject", None) is not None:
                install_material_view_provider(material.ViewObject)
                if getattr(material, "References", []):
                    material.References = []

            solver = getattr(obj, "solver", None)
            if solver is not None and getattr(solver, "ViewObject", None) is not None:
                install_solver_view_provider(solver.ViewObject)


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
        if prop in {"material", "solver"}:
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
