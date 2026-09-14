# SPDX-License-Identifier: LGPL-2.1-or-later

"""Coin overlay arrows for FEMPart dynamic loads."""

import FreeCAD as App

import FreeCADMbDFEMEmbedded
import FreeCADMbDFreeBodyDiagram


_DLOAD_COLOR = (0.95, 0.50, 0.05)
_GRAVITY_COLOR = (0.0, 0.85, 0.95)
_ZERO_TOLERANCE = 1.0e-9
_DEFAULT_DISPLAYED_ELEMENTS = 20
_DEFAULT_DLOAD_AUTO_SCALE = True
_DEFAULT_DLOAD_SCALE = 1.0
_AUTO_SCALE_DIAGONAL_FRACTION = 0.1
_diagrams = {}
_prepared_auto_scales = {}
_sampled_element_view_states = {}


def install():
    """Register the MbDFEM FEMPart DLOAD GUI command."""
    import FreeCADGui as Gui

    Gui.addCommand("MbDFEM_ShowFEMPartDLOADs", ShowDLOADsCommand())
    Gui.addCommand("MbDFEM_ShowFEMPartDLOADElements", ShowDLOADElementsCommand())


def update_active_diagrams(controller, sample):
    """Refresh every visible FEMPart DLOAD diagram for *controller*'s assembly."""
    _update_active_sampled_element_views(controller, sample)
    if not _diagrams:
        return

    prepare_diagram_scale(controller.assembly)
    for key, diagram in list(_diagrams.items()):
        if diagram.assembly is controller.assembly:
            if not diagram.is_valid():
                _diagrams.pop(key, None)
                diagram.remove()
            else:
                diagram.update(sample)


def refresh_assembly_diagrams(document_name, assembly_name, force_scale_prepare=False):
    """Refresh visible DLOAD diagrams for the named assembly after a property edit."""
    document = App.getDocument(document_name)
    source = document.getObject(assembly_name) if document is not None else None
    assembly = _mbd_assembly_from_scale_source(source)
    if assembly is None:
        return

    if force_scale_prepare:
        prepare_diagram_scale(assembly, force=True)
    for key, diagram in list(_diagrams.items()):
        if diagram.assembly is assembly:
            if not diagram.is_valid():
                _diagrams.pop(key, None)
                diagram.remove()
            else:
                frame = diagram.current_frame
                diagram.update((frame, frame, 0.0, frame))


def prepare_diagram_scale(assembly, force=False):
    """Prepare the assembly-wide DLOAD auto scale used during animation."""
    scale_owner = _scale_owner(assembly)
    if not _auto_scale_enabled(scale_owner):
        return _view_scale_multiplier(scale_owner)

    key = FreeCADMbDFreeBodyDiagram._assembly_key(scale_owner)
    if force or key not in _prepared_auto_scales:
        _prepared_auto_scales[key] = _assembly_auto_diagram_scale(assembly)

    return _prepared_auto_scales[key] * _view_scale_multiplier(scale_owner)


def reset_diagram_scales(assembly=None):
    """Forget prepared DLOAD scales."""
    if assembly is None:
        _prepared_auto_scales.clear()
        return
    _prepared_auto_scales.pop(
        FreeCADMbDFreeBodyDiagram._assembly_key(_scale_owner(assembly)),
        None,
    )


def active_fem_parts():
    """Return selected FEMPart objects, resolving selected children when possible."""
    import FreeCADGui as Gui

    document = App.ActiveDocument
    if document is None:
        return []

    parts = []
    seen = set()

    try:
        selection = Gui.Selection.getSelection(document.Name)
    except Exception:
        selection = []

    for obj in selection:
        for fem_part in _fem_parts_from_object(obj):
            if fem_part is not None and fem_part.Name not in seen:
                parts.append(fem_part)
                seen.add(fem_part.Name)

    if parts:
        return parts

    try:
        selection = Gui.Selection.getSelectionEx(document.Name)
    except Exception:
        selection = []

    for selected in selection:
        for fem_part in _fem_parts_from_selection(selected):
            if fem_part is not None and fem_part.Name not in seen:
                parts.append(fem_part)
                seen.add(fem_part.Name)

    return parts


def _fem_parts_from_object(obj):
    if _is_fem_part(obj):
        return [obj]

    fem_part = _fem_part_containing_child(obj)
    return [fem_part] if fem_part is not None else []


def _fem_parts_from_selection(selected):
    obj = getattr(selected, "Object", None)
    if _is_fem_part(obj):
        return [obj]

    sub_names = list(getattr(selected, "SubElementNames", []))
    if obj is not None and sub_names:
        for sub_name in sub_names:
            try:
                sub_object = obj.getSubObject(sub_name)
            except Exception:
                sub_object = None
            if _is_fem_part(sub_object):
                return [sub_object]

    fem_part = _fem_part_containing_child(obj)
    return [fem_part] if fem_part is not None else []


def _is_fem_part(obj):
    try:
        return obj is not None and obj.isDerivedFrom("MbDFEM::FEMPart")
    except Exception:
        return False


def _fem_part_containing_child(child):
    document = getattr(child, "Document", None)
    if document is None:
        return None

    for obj in document.Objects:
        if not _is_fem_part(obj):
            continue
        try:
            if child in obj.Group:
                return obj
        except Exception:
            pass
        if child in (
            getattr(obj, "mesh", None),
            getattr(obj, "solver", None),
            getattr(obj, "visual", None),
        ):
            return obj
        try:
            if child in obj.results:
                return obj
        except Exception:
            pass
    return None


def _diagram_key(fem_part):
    return (fem_part.Document.Name, fem_part.Name)


def _toggle_fem_part(fem_part):
    key = _diagram_key(fem_part)
    diagram = _diagrams.pop(key, None)
    if diagram is not None:
        diagram.remove()
        return False

    assembly = FreeCADMbDFEMEmbedded._owning_mbd_assembly(fem_part)
    if assembly is None:
        App.Console.PrintError("FEMPart is not linked to an MbDPart in an MbDAssembly.\n")
        return False

    diagram = None
    try:
        diagram = FEMPartDLOADDiagram(fem_part, assembly)
        diagram.update((diagram.current_frame, diagram.current_frame, 0.0, diagram.current_frame))
    except Exception as exc:
        if diagram is not None:
            diagram.remove()
        App.Console.PrintError(f"Show DLOADs failed: {exc}\n")
        return False

    _diagrams[key] = diagram
    return True


class ShowDLOADsCommand:
    """Toggle D'Alembert and gravity acceleration arrows for selected FEMParts."""

    def GetResources(self):
        return {
            "MenuText": "Show DLOADs",
            "ToolTip": "Toggle D'Alembert and gravity acceleration arrows for the selected FEMPart",
        }

    def IsActive(self):
        return App.ActiveDocument is not None

    def Activated(self):
        fem_parts = active_fem_parts()
        if not fem_parts:
            App.Console.PrintError("Select a FEMPart to toggle DLOAD arrows.\n")
            return

        for fem_part in fem_parts:
            _toggle_fem_part(fem_part)


class ShowDLOADElementsCommand:
    """Toggle sampled FEMPart elements and DLOAD arrows."""

    def GetResources(self):
        return {
            "MenuText": "Show DLOAD Elements",
            "ToolTip": "Show only the sampled FEM elements used by DLOAD arrows",
        }

    def IsActive(self):
        return App.ActiveDocument is not None

    def Activated(self):
        fem_parts = active_fem_parts()
        if not fem_parts:
            App.Console.PrintError("Select a FEMPart to toggle sampled DLOAD elements.\n")
            return

        for fem_part in fem_parts:
            try:
                _toggle_sampled_elements(fem_part)
            except Exception as exc:
                App.Console.PrintError(f"Show DLOAD Elements failed: {exc}\n")


class FEMPartDLOADDiagram:
    """Scene graph overlay tied to one FEMPart."""

    def __init__(self, fem_part, assembly):
        from pivy import coin

        self.fem_part = fem_part
        self.assembly = assembly
        self._coin = coin
        self.current_frame = 0
        self.root = coin.SoSeparator()
        self.root.ref()
        self.arrows = []
        self._view = FreeCADMbDFreeBodyDiagram._active_view(fem_part)
        self._scene_graph = self._view.getSceneGraph()
        self._scene_graph.addChild(self.root)

    def is_valid(self):
        return self.fem_part.Document is not None and self.assembly.Document is not None

    def remove(self):
        try:
            self._scene_graph.removeChild(self.root)
        except Exception:
            pass
        try:
            self.root.unref()
        except Exception:
            pass

    def update(self, sample):
        self.current_frame = sample[3]
        vectors = _diagram_vectors(self.fem_part, self.assembly, sample)
        scale = _diagram_scale(self.fem_part, self.assembly)
        self._ensure_arrows(len(vectors))
        for arrow, vector in zip(self.arrows, vectors):
            arrow.update(vector.origin, vector.value, scale, _color_for_vector(vector.kind))
        for arrow in self.arrows[len(vectors) :]:
            arrow.hide()

    def _ensure_arrows(self, count):
        while len(self.arrows) < count:
            arrow = FreeCADMbDFreeBodyDiagram._make_arrow(
                self._coin,
                use_load_style=True,
                view=self._view,
            )
            self.arrows.append(arrow)
            self.root.addChild(arrow.root)


class _DiagramVector:
    def __init__(self, kind, origin, value):
        self.kind = kind
        self.origin = origin
        self.value = value


def _color_for_vector(kind):
    return _GRAVITY_COLOR if kind == "gravity" else _DLOAD_COLOR


def _diagram_vectors(fem_part, assembly, sample=None):
    if not _fem_part_visible(fem_part):
        return []

    mbd_part = getattr(fem_part, "mbdItem", None)
    if mbd_part is None:
        return []

    gravity = _gravity_acceleration_global(assembly)
    vectors = []
    for element_id in _visible_element_ids(fem_part):
        try:
            centroid_local = fem_part.elementCentroidLocal(int(element_id))
            origin = fem_part.elementCentroidGlobal(int(element_id))
            acceleration = mbd_part.globalAccelerationOf(centroid_local)
        except Exception:
            continue
        vectors.append(
            _DiagramVector(
                "dalembert",
                origin,
                App.Vector(-acceleration.x, -acceleration.y, -acceleration.z),
            )
        )
        if gravity is not None:
            vectors.append(_DiagramVector("gravity", origin, gravity))
    return vectors


def _visible_element_ids(fem_part):
    mesh_object = getattr(fem_part, "mesh", None)
    if mesh_object is None:
        return []
    return _sample_element_ids(
        FreeCADMbDFEMEmbedded._fem_mesh_volume_ids(mesh_object),
        _display_sample_size(fem_part),
    )


def _toggle_sampled_elements(fem_part):
    key = _diagram_key(fem_part)
    state = _sampled_element_view_states.pop(key, None)
    if state is not None:
        _restore_sampled_elements(state)
        return False

    _sampled_element_view_states[key] = _show_sampled_elements(fem_part)
    return True


def _show_sampled_elements(fem_part):
    import FreeCADGui as Gui

    mesh_object = getattr(fem_part, "mesh", None)
    if mesh_object is None:
        raise ValueError("Selected FEMPart has no mesh. Create the mesh first.")

    assembly = FreeCADMbDFEMEmbedded._owning_mbd_assembly(fem_part)
    if assembly is None:
        raise ValueError("FEMPart is not linked to an MbDPart in an MbDAssembly.")

    element_ids = _visible_element_ids(fem_part)
    if not element_ids:
        raise ValueError("Selected FEMPart has no sampled volume elements.")

    document = fem_part.Document
    display_object = document.addObject(
        "Fem::FemMeshObject",
        f"{fem_part.Name}_DLOADElements",
    )
    display_object.Label = f"DLOAD Elements ({fem_part.Label})"
    try:
        _add_to_fem_part_group(fem_part, display_object)
        display_object.FemMesh = _sampled_elements_fem_mesh(mesh_object, element_ids)
        _set_property(
            display_object,
            "Placement",
            _sampled_elements_display_placement(fem_part),
        )

        state = _capture_sampled_elements_state(fem_part, mesh_object, display_object)
        _apply_sampled_elements_view(state)

        created_diagram = _ensure_fem_part_diagram(fem_part, assembly)
        state["created_diagram"] = created_diagram
    except Exception:
        try:
            document.removeObject(display_object.Name)
        except Exception:
            pass
        raise

    if document is not None:
        document.recompute()

    Gui.Selection.clearSelection()
    Gui.Selection.addSelection(display_object)

    App.Console.PrintMessage(
        "MbDFEM Show DLOAD Elements: "
        f"{len(element_ids)} sampled elements displayed with DLOAD arrows.\n"
    )
    return state


def _restore_sampled_elements(state):
    import FreeCADGui as Gui

    fem_part = state.get("fem_part")
    display_object = state.get("display_object")
    document = getattr(fem_part, "Document", None)

    _restore_property(fem_part, "Visibility", state, "fem_part_visibility")
    _restore_property(
        getattr(fem_part, "ViewObject", None),
        "Visibility",
        state,
        "fem_part_view_visibility",
    )
    _restore_property(
        getattr(fem_part, "ViewObject", None),
        "Transparency",
        state,
        "fem_part_transparency",
    )
    _restore_property(state.get("mesh_object"), "Visibility", state, "mesh_visibility")
    _restore_property(
        getattr(state.get("mesh_object"), "ViewObject", None),
        "Visibility",
        state,
        "mesh_view_visibility",
    )
    _restore_property(
        getattr(state.get("visual"), "ViewObject", None),
        "Visibility",
        state,
        "visual_view_visibility",
    )

    if state.get("created_diagram"):
        key = _diagram_key(fem_part)
        diagram = _diagrams.pop(key, None)
        if diagram is not None:
            diagram.remove()

    if document is not None and display_object is not None:
        try:
            _remove_from_fem_part_group(fem_part, display_object)
            document.removeObject(display_object.Name)
        except Exception:
            pass
        document.recompute()

    Gui.Selection.clearSelection()
    if fem_part is not None:
        Gui.Selection.addSelection(fem_part)
    App.Console.PrintMessage("MbDFEM Show DLOAD Elements: restored previous view.\n")


def _capture_sampled_elements_state(fem_part, mesh_object, display_object):
    visual = getattr(fem_part, "visual", None)
    return {
        "fem_part": fem_part,
        "mesh_object": mesh_object,
        "visual": visual,
        "display_object": display_object,
        "created_diagram": False,
        "fem_part_visibility": _get_property(fem_part, "Visibility"),
        "fem_part_view_visibility": _get_property(
            getattr(fem_part, "ViewObject", None),
            "Visibility",
        ),
        "fem_part_transparency": _get_property(
            getattr(fem_part, "ViewObject", None),
            "Transparency",
        ),
        "mesh_visibility": _get_property(mesh_object, "Visibility"),
        "mesh_view_visibility": _get_property(
            getattr(mesh_object, "ViewObject", None),
            "Visibility",
        ),
        "visual_view_visibility": _get_property(
            getattr(visual, "ViewObject", None),
            "Visibility",
        ),
    }


def _apply_sampled_elements_view(state):
    fem_part = state.get("fem_part")
    mesh_object = state.get("mesh_object")
    visual = state.get("visual")
    display_object = state.get("display_object")

    _set_property(fem_part, "Visibility", True)
    _set_property(getattr(fem_part, "ViewObject", None), "Visibility", True)
    _set_property(getattr(fem_part, "ViewObject", None), "Transparency", 85)
    _set_property(mesh_object, "Visibility", False)
    _set_property(getattr(mesh_object, "ViewObject", None), "Visibility", False)
    _set_property(getattr(visual, "ViewObject", None), "Visibility", False)
    _set_property(display_object, "Visibility", True)
    _set_property(getattr(display_object, "ViewObject", None), "Visibility", True)
    _set_property(getattr(display_object, "ViewObject", None), "ShowInner", True)
    _set_property(
        getattr(display_object, "ViewObject", None),
        "MaxFacesShowInner",
        1000000,
    )
    _set_property(getattr(display_object, "ViewObject", None), "BackfaceCulling", False)
    _set_property(getattr(display_object, "ViewObject", None), "LineWidth", 1.0)
    _set_property(getattr(display_object, "ViewObject", None), "PointSize", 3.0)
    for display_mode in ("Wireframe & Nodes", "Faces, Wireframe & Nodes"):
        try:
            display_object.ViewObject.DisplayMode = display_mode
            break
        except Exception:
            pass


def _update_active_sampled_element_views(controller, sample):
    assembly = getattr(controller, "assembly", None)
    for key, state in list(_sampled_element_view_states.items()):
        fem_part = state.get("fem_part")
        display_object = state.get("display_object")
        if not _sampled_element_state_is_valid(state):
            _sampled_element_view_states.pop(key, None)
            continue
        if FreeCADMbDFEMEmbedded._owning_mbd_assembly(fem_part) is not assembly:
            continue
        _set_property(
            display_object,
            "Placement",
            _sampled_elements_display_placement(fem_part),
        )


def _sampled_element_state_is_valid(state):
    fem_part = state.get("fem_part")
    display_object = state.get("display_object")
    return (
        fem_part is not None
        and display_object is not None
        and getattr(fem_part, "Document", None) is not None
        and getattr(display_object, "Document", None) is not None
    )


def _sampled_elements_display_placement(fem_part, sample=None):
    mesh_object = getattr(fem_part, "mesh", None)
    try:
        return App.Placement(mesh_object.Placement)
    except Exception:
        return App.Placement()


def _fem_part_placement_at_sample(fem_part, sample=None):
    mbd_part = getattr(fem_part, "mbdItem", None)
    if mbd_part is not None:
        if sample is not None and _has_sampled_placement(mbd_part):
            return FreeCADMbDFreeBodyDiagram._placement_at_sample(mbd_part, sample)
        try:
            return App.Placement(mbd_part.Placement)
        except Exception:
            pass

    try:
        return fem_part.getGlobalPlacement()
    except Exception:
        pass

    try:
        return App.Placement(fem_part.Placement)
    except Exception:
        return App.Placement()


def _has_sampled_placement(mbd_part):
    has_position = any(list(getattr(mbd_part, name, [])) for name in ("xs", "ys", "zs"))
    has_rotation = all(list(getattr(mbd_part, name, [])) for name in ("bryxs", "bryys", "bryzs"))
    return has_position or has_rotation


def _ensure_fem_part_diagram(fem_part, assembly):
    key = _diagram_key(fem_part)
    diagram = _diagrams.get(key)
    if diagram is None or not diagram.is_valid():
        if diagram is not None:
            diagram.remove()
        diagram = FEMPartDLOADDiagram(fem_part, assembly)
        _diagrams[key] = diagram
        created = True
    else:
        created = False
    diagram.update((diagram.current_frame, diagram.current_frame, 0.0, diagram.current_frame))
    return created


def _sampled_elements_fem_mesh(mesh_object, element_ids):
    import Fem

    source_mesh = mesh_object.FemMesh
    element_nodes = {}
    node_ids = set()
    for element_id in element_ids:
        nodes = list(source_mesh.getElementNodes(int(element_id)))
        element_nodes[int(element_id)] = nodes
        node_ids.update(int(node_id) for node_id in nodes)

    sampled_mesh = Fem.FemMesh()
    for node_id in sorted(node_ids):
        point = source_mesh.Nodes.get(node_id)
        if point is None:
            point = source_mesh.getNodeById(node_id)
        sampled_mesh.addNode(point.x, point.y, point.z, node_id)

    for element_id in element_ids:
        sampled_mesh.addVolume(element_nodes[int(element_id)], int(element_id))
    return sampled_mesh


def _get_property(target, name):
    try:
        if target is not None and hasattr(target, name):
            return getattr(target, name)
    except Exception:
        pass
    return None


def _set_property(target, name, value):
    try:
        if target is not None and hasattr(target, name):
            setattr(target, name, value)
    except Exception:
        pass


def _restore_property(target, name, state, key):
    if state.get(key) is not None:
        _set_property(target, name, state[key])


def _add_to_fem_part_group(fem_part, object_):
    try:
        fem_part.addObject(object_)
    except Exception:
        pass


def _remove_from_fem_part_group(fem_part, object_):
    try:
        fem_part.removeObject(object_)
    except Exception:
        pass


def _display_sample_size(fem_part):
    view_object = getattr(fem_part, "ViewObject", None)
    try:
        return int(getattr(view_object, "DLOADSampleSize"))
    except Exception:
        return _DEFAULT_DISPLAYED_ELEMENTS


def _sample_element_ids(element_ids, maximum):
    element_ids = list(element_ids)
    if maximum <= 0:
        return []
    if len(element_ids) <= maximum:
        return element_ids
    if maximum == 1:
        return [element_ids[0]]

    last = len(element_ids) - 1
    return [
        element_ids[int(round(index * last / (maximum - 1)))]
        for index in range(maximum)
    ]


def _fem_part_mesh_visible(fem_part):
    if not bool(getattr(fem_part, "Visibility", True)):
        return False

    mesh_object = getattr(fem_part, "mesh", None)
    if mesh_object is None:
        return False

    try:
        if fem_part.isElementVisible(mesh_object.Name) == 0:
            return False
    except Exception:
        pass

    view_object = getattr(mesh_object, "ViewObject", None)
    if view_object is not None:
        try:
            return bool(view_object.Visibility)
        except Exception:
            pass
    return True


def _fem_part_visible(fem_part):
    return bool(getattr(fem_part, "Visibility", True))


def _gravity_acceleration_global(assembly):
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

    rotation = FreeCADMbDFEMEmbedded._global_rotation(assembly)
    return rotation.multVec(App.Vector(gravity.x, gravity.y, gravity.z))


def _diagram_scale(fem_part, assembly):
    return prepare_diagram_scale(assembly)


def _scale_owner(assembly):
    fem_assembly = _fem_assembly_for_mbd_assembly(assembly)
    return fem_assembly if fem_assembly is not None else assembly


def _mbd_assembly_from_scale_source(source):
    if source is None:
        return None
    try:
        if source.isDerivedFrom("MbDFEM::MbDAssembly"):
            return source
    except Exception:
        pass
    try:
        if source.isDerivedFrom("MbDFEM::FEMAssembly"):
            return getattr(source, "mbdItem", None)
    except Exception:
        pass
    return None


def _fem_assembly_for_mbd_assembly(assembly):
    document = getattr(assembly, "Document", None)
    if document is None:
        return None
    for obj in document.Objects:
        try:
            if obj.isDerivedFrom("MbDFEM::FEMAssembly") and getattr(obj, "mbdItem", None) is assembly:
                return obj
        except Exception:
            pass
    return None


def _auto_scale_enabled(assembly):
    return FreeCADMbDFreeBodyDiagram._view_property_bool(
        assembly,
        "DLOADAutoScale",
        _DEFAULT_DLOAD_AUTO_SCALE,
    )


def _view_scale_multiplier(assembly):
    return FreeCADMbDFreeBodyDiagram._view_property_float(
        assembly,
        "DLOADScale",
        _DEFAULT_DLOAD_SCALE,
    )


def _assembly_auto_diagram_scale(assembly):
    diagonal = max(FreeCADMbDFreeBodyDiagram._motion_bounding_box_diagonal(assembly), 1.0)
    maximum = 0.0
    for fem_part in _assembly_fem_parts(assembly):
        for sample in FreeCADMbDFreeBodyDiagram._result_samples(assembly):
            for vector in _diagram_vectors_for_scale(fem_part, assembly, sample):
                maximum = max(maximum, vector.value.Length)
    if maximum <= _ZERO_TOLERANCE:
        return 1.0
    return (diagonal * _AUTO_SCALE_DIAGONAL_FRACTION) / maximum


def _assembly_fem_parts(assembly):
    document = getattr(assembly, "Document", None)
    if document is None:
        return []

    mbd_part_names = {
        getattr(part, "Name", None)
        for part in FreeCADMbDFreeBodyDiagram._assembly_parts(assembly)
    }
    fem_parts = []
    for obj in document.Objects:
        if not _is_fem_part(obj):
            continue
        if getattr(getattr(obj, "mbdItem", None), "Name", None) in mbd_part_names:
            fem_parts.append(obj)
    return fem_parts


def _diagram_vectors_for_scale(fem_part, assembly, sample):
    mbd_part = getattr(fem_part, "mbdItem", None)
    if mbd_part is None:
        return []

    placement = App.Placement(mbd_part.Placement)
    fem_part_placement = App.Placement(fem_part.Placement)
    velocity = getattr(mbd_part, "velocity", App.Vector())
    omega = getattr(mbd_part, "omega", App.Vector())
    acceleration = getattr(mbd_part, "acceleration", App.Vector())
    alpha = getattr(mbd_part, "alpha", App.Vector())
    try:
        mbd_part.Placement = FreeCADMbDFreeBodyDiagram._placement_at_sample(mbd_part, sample)
        mbd_part.velocity = (
            FreeCADMbDFreeBodyDiagram._sample_vector(mbd_part, ("vxs", "vys", "vzs"), sample)
            * FreeCADMbDFreeBodyDiagram._RESULT_LENGTH_TO_DOCUMENT_LENGTH
        )
        mbd_part.omega = FreeCADMbDFreeBodyDiagram._sample_vector(
            mbd_part,
            ("omexs", "omeys", "omezs"),
            sample,
        )
        mbd_part.acceleration = (
            FreeCADMbDFreeBodyDiagram._sample_vector(mbd_part, ("axs", "ays", "azs"), sample)
            * FreeCADMbDFreeBodyDiagram._RESULT_LENGTH_TO_DOCUMENT_LENGTH
        )
        mbd_part.alpha = FreeCADMbDFreeBodyDiagram._sample_vector(
            mbd_part,
            ("alpxs", "alpys", "alpzs"),
            sample,
        )
        fem_part.Placement = mbd_part.Placement
        return _diagram_vectors(fem_part, assembly, sample)
    finally:
        mbd_part.Placement = placement
        mbd_part.velocity = velocity
        mbd_part.omega = omega
        mbd_part.acceleration = acceleration
        mbd_part.alpha = alpha
        fem_part.Placement = fem_part_placement
