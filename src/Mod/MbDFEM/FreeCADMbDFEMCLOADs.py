# SPDX-License-Identifier: LGPL-2.1-or-later

"""Coin overlay arrows for FEMPart concentrated loads."""

import FreeCAD as App

import os

import FreeCADMbDBackend
import FreeCADMbDFEMDLOADs
import FreeCADMbDFEMEmbedded
import FreeCADMbDFreeBodyDiagram


_CLOAD_COLOR = (0.85, 0.10, 0.85)
_ZERO_TOLERANCE = 1.0e-9
_DEFAULT_CLOAD_AUTO_SCALE = True
_DEFAULT_CLOAD_SCALE = 1.0
_AUTO_SCALE_DIAGONAL_FRACTION = 0.1
_diagrams = {}
_prepared_auto_scales = {}
_face_view_states = {}

_VOLUME_FACE_NODE_INDICES = {
    4: ((0, 1, 2), (0, 3, 1), (1, 3, 2), (2, 3, 0)),
    5: ((0, 1, 2, 3), (0, 4, 1), (1, 4, 2), (2, 4, 3), (3, 4, 0)),
    6: ((0, 1, 2), (3, 5, 4), (0, 3, 4, 1), (1, 4, 5, 2), (0, 2, 5, 3)),
    8: (
        (0, 1, 2, 3),
        (4, 7, 6, 5),
        (0, 4, 5, 1),
        (1, 5, 6, 2),
        (2, 6, 7, 3),
        (3, 7, 4, 0),
    ),
    10: ((0, 1, 2), (0, 3, 1), (1, 3, 2), (2, 3, 0)),
    13: ((0, 1, 2, 3), (0, 4, 1), (1, 4, 2), (2, 4, 3), (3, 4, 0)),
    15: ((0, 1, 2), (3, 5, 4), (0, 3, 4, 1), (1, 4, 5, 2), (0, 2, 5, 3)),
    20: (
        (0, 1, 2, 3),
        (4, 7, 6, 5),
        (0, 4, 5, 1),
        (1, 5, 6, 2),
        (2, 6, 7, 3),
        (3, 7, 4, 0),
    ),
}


def install():
    """Register the MbDFEM FEMPart CLOAD GUI command."""
    import FreeCADGui as Gui

    Gui.addCommand("MbDFEM_ShowFEMPartCLOADs", ShowCLOADsCommand())
    Gui.addCommand("MbDFEM_ShowFEMPartCLOADFaces", ShowCLOADFacesCommand())


def update_active_diagrams(controller, sample):
    """Refresh every visible FEMPart CLOAD diagram for *controller*'s assembly."""
    _update_active_face_views(controller, sample)
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
    """Refresh visible CLOAD diagrams for the named assembly after a property edit."""
    document = App.getDocument(document_name)
    source = document.getObject(assembly_name) if document is not None else None
    assembly = FreeCADMbDFEMDLOADs._mbd_assembly_from_scale_source(source)
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
    """Prepare the assembly-wide CLOAD auto scale used during animation."""
    scale_owner = FreeCADMbDFEMDLOADs._scale_owner(assembly)
    if not _auto_scale_enabled(scale_owner):
        return _view_scale_multiplier(scale_owner)

    key = FreeCADMbDFreeBodyDiagram._assembly_key(scale_owner)
    if force or key not in _prepared_auto_scales:
        _prepared_auto_scales[key] = _assembly_auto_diagram_scale(assembly)

    return _prepared_auto_scales[key] * _view_scale_multiplier(scale_owner)


def reset_diagram_scales(assembly=None):
    """Forget prepared CLOAD scales."""
    if assembly is None:
        _prepared_auto_scales.clear()
        return
    _prepared_auto_scales.pop(
        FreeCADMbDFreeBodyDiagram._assembly_key(FreeCADMbDFEMDLOADs._scale_owner(assembly)),
        None,
    )


def _toggle_fem_part(fem_part):
    key = FreeCADMbDFEMDLOADs._diagram_key(fem_part)
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
        diagram = FEMPartCLOADDiagram(fem_part, assembly)
        diagram.update((diagram.current_frame, diagram.current_frame, 0.0, diagram.current_frame))
    except Exception as exc:
        if diagram is not None:
            diagram.remove()
        App.Console.PrintError(f"Show CLOADs failed: {exc}\n")
        return False

    _diagrams[key] = diagram
    return True


def _toggle_cload_faces(fem_part):
    key = FreeCADMbDFEMDLOADs._diagram_key(fem_part)
    state = _face_view_states.pop(key, None)
    if state is not None:
        _restore_cload_faces(state)
        return False

    _face_view_states[key] = _show_cload_faces(fem_part)
    return True


def _show_cload_faces(fem_part):
    import FreeCADGui as Gui

    mesh_object = getattr(fem_part, "mesh", None)
    if mesh_object is None:
        raise ValueError("Selected FEMPart has no mesh. Create the mesh first.")

    assembly = FreeCADMbDFEMEmbedded._owning_mbd_assembly(fem_part)
    if assembly is None:
        raise ValueError("FEMPart is not linked to an MbDPart in an MbDAssembly.")

    face_regions = _mbd_joint_cylindrical_face_regions(fem_part, assembly)
    if not face_regions:
        raise ValueError("Selected FEMPart has no joint cylindrical face mesh facets.")

    document = fem_part.Document
    display_object = document.addObject(
        "Fem::FemMeshObject",
        f"{fem_part.Name}_CLOADFaces",
    )
    display_object.Label = f"CLOAD Faces ({fem_part.Label})"
    try:
        _add_to_fem_part_group(fem_part, display_object)
        display_object.FemMesh = _cload_faces_fem_mesh(mesh_object, face_regions)
        _set_property(display_object, "Placement", _cload_faces_display_placement(fem_part))

        state = _capture_face_view_state(fem_part, mesh_object, display_object)
        _apply_face_view_state(state)

        created_diagram = _ensure_fem_part_diagram(
            fem_part,
            assembly,
            _current_animation_sample(assembly),
        )
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
        "MbDFEM Show CLOAD Faces: "
        f"{display_object.FemMesh.FaceCount} mesh facets displayed with CLOAD arrows.\n"
    )
    return state


def _restore_cload_faces(state):
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
        key = FreeCADMbDFEMDLOADs._diagram_key(fem_part)
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
    App.Console.PrintMessage("MbDFEM Show CLOAD Faces: restored previous view.\n")


def _capture_face_view_state(fem_part, mesh_object, display_object):
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


def _apply_face_view_state(state):
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
    for display_mode in ("Faces, Wireframe & Nodes", "Wireframe & Nodes"):
        try:
            display_object.ViewObject.DisplayMode = display_mode
            break
        except Exception:
            pass


def _ensure_fem_part_diagram(fem_part, assembly, sample=None):
    key = FreeCADMbDFEMDLOADs._diagram_key(fem_part)
    diagram = _diagrams.get(key)
    if diagram is None or not diagram.is_valid():
        if diagram is not None:
            diagram.remove()
        diagram = FEMPartCLOADDiagram(fem_part, assembly)
        _diagrams[key] = diagram
        created = True
    else:
        created = False
    if sample is None:
        sample = (diagram.current_frame, diagram.current_frame, 0.0, diagram.current_frame)
    diagram.update(sample)
    return created


class ShowCLOADsCommand:
    """Toggle concentrated-load arrows for selected FEMParts."""

    def GetResources(self):
        return {
            "MenuText": "Show CLOADs",
            "ToolTip": "Toggle concentrated-load arrows for the selected FEMPart",
        }

    def IsActive(self):
        return App.ActiveDocument is not None

    def Activated(self):
        fem_parts = FreeCADMbDFEMDLOADs.active_fem_parts()
        if not fem_parts:
            App.Console.PrintError("Select a FEMPart to toggle CLOAD arrows.\n")
            return

        for fem_part in fem_parts:
            _toggle_fem_part(fem_part)


class ShowCLOADFacesCommand:
    """Toggle joint CLOAD face facets and concentrated-load arrows."""

    def GetResources(self):
        return {
            "MenuText": "Show CLOAD Faces",
            "ToolTip": "Show joint CLOAD arrows and only the loaded mesh face facets",
        }

    def IsActive(self):
        return App.ActiveDocument is not None

    def Activated(self):
        fem_parts = FreeCADMbDFEMDLOADs.active_fem_parts()
        if not fem_parts:
            App.Console.PrintError("Select a FEMPart to toggle CLOAD faces.\n")
            return

        for fem_part in fem_parts:
            try:
                _toggle_cload_faces(fem_part)
            except Exception as exc:
                App.Console.PrintError(f"Show CLOAD Faces failed: {exc}\n")


class FEMPartCLOADDiagram:
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
        scale = _diagram_scale(self.fem_part, self.assembly, vectors)
        self._ensure_arrows(len(vectors))
        shape, placement = _arrow_body_geometry(self.fem_part, sample)
        for arrow, vector in zip(self.arrows, vectors):
            if vector.cylinder is not None:
                origin, arrow_scale = _cylindrical_cload_arrow(
                    vector.cylinder, placement, vector.origin, vector.value, scale)
            else:
                origin, arrow_scale = _outside_cload_arrow(
                    shape, placement, vector.origin, vector.value, scale)
            arrow.update(origin, vector.value, arrow_scale, _CLOAD_COLOR)
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


def _arrow_body_geometry(fem_part, sample):
    """Return the undeformed solid in the same local frame as the mesh nodes."""
    part = getattr(fem_part, "mbdItem", None)
    shape = getattr(part, "Shape", None)
    if shape is None or shape.isNull():
        return None, App.Placement()
    shape = shape.copy()
    shape.Placement = App.Placement()
    return shape, _mesh_placement_at_sample(fem_part, sample)


def _outside_cload_arrow(shape, placement, origin, value, scale):
    """Keep the force direction, anchoring either end on the body's surface.

    Choose the side with more space before the first obstruction. Keep the
    full scaled length even when the arrow crosses another surface; the user
    can reveal obscured portions with body transparency.
    """
    length = value.Length * scale
    if shape is None or length <= _ZERO_TOLERANCE:
        return origin, scale
    import Part

    inverse = placement.inverse()
    contact = inverse.multVec(origin)
    direction = inverse.Rotation.multVec(value)
    direction.normalize()
    tolerance = 1.0e-7
    # Curved mesh facets can place a node slightly beneath the CAD surface.
    if shape.isInside(contact, tolerance, False):
        _distance, closest, _info = shape.distToShape(Part.Vertex(contact))
        contact = closest[0][0]
    line = Part.Line(contact, contact + direction)
    cuts = [-length, 0.0, length]
    try:
        # Untrimmed surface intersections can add extra cuts, but cannot miss
        # a solid boundary. Midpoint classification handles the trimmed faces.
        for face in shape.Faces:
            points, _curves = face.Surface.intersect(line)
            cuts.extend(max(-length, min(length,
                        (App.Vector(p.X, p.Y, p.Z) - contact).dot(direction)))
                        for p in points)
    except (AttributeError, RuntimeError, TypeError):
        segment = Part.makeLine(contact - direction * length, contact + direction * length)
        cuts.extend(max(-length, min(length, (v.Point - contact).dot(direction)))
                    for v in shape.section(segment).Vertexes)
    cuts = sorted(set(cuts))
    available = {1: length, -1: length}
    for left, right in zip(cuts, cuts[1:]):
        if right - left <= tolerance:
            continue
        midpoint = (left + right) * 0.5
        if shape.isInside(contact + direction * midpoint, tolerance, False):
            sign = 1 if midpoint > 0 else -1
            available[sign] = min(available[sign], max(0.0, left if sign == 1 else -right))
    sign = 1 if available[1] >= available[-1] else -1
    tail = contact if sign == 1 else contact - direction * length
    return placement.multVec(tail), scale


def _cylindrical_cload_arrow(cylinder, placement, origin, value, scale):
    """Anchor using the contact cylinder alone, including at its end rims."""
    inverse = placement.inverse()
    contact = inverse.multVec(origin)
    relative = contact - cylinder["origin"]
    axis = cylinder["axis"]
    axial = axis * relative.dot(axis)
    radial = relative - axial
    if radial.Length <= 1.0e-12:
        return origin, scale
    radial.normalize()
    contact = cylinder["origin"] + axial + radial * cylinder["radius"]
    force = inverse.Rotation.multVec(value)
    radial_force = force.dot(radial)
    # Material is inside a pin cylinder and outside a hole cylinder.
    # Ignore end planes and shoulders; a tangent or axial force uses the tail.
    into_material = radial_force > 1.0e-12 if cylinder["role"] == "hole" else radial_force < -1.0e-12
    tail = contact - force * scale if into_material else contact
    return placement.multVec(tail), scale


def _cylindrical_node_geometry(fem_part, nodes):
    """Associate mesh nodes with the selected CylCylFacePair's local cylinder."""
    part = getattr(fem_part, "mbdItem", None)
    shape = getattr(part, "Shape", None)
    if shape is None or shape.isNull():
        return {}
    shape = shape.copy()
    shape.Placement = App.Placement()
    cylinders = {}
    for joint, _marker, _sign in FreeCADMbDFEMEmbedded._part_joints_for_fem_part(fem_part):
        for pair in FreeCADMbDFEMEmbedded._joint_face_pairs(joint):
            if pair.get("type") != "CylCyl":
                continue
            side = FreeCADMbDFEMEmbedded._face_pair_side_for_part(pair, part)
            if side is None:
                continue
            face = shape.Faces[int(pair["subName" + side][4:]) - 1]
            reference = FreeCADMbDFEMEmbedded._cylindrical_face_reference(face)
            if reference is None:
                continue
            reference["role"] = pair["role" + side]
            ids = FreeCADMbDFEMEmbedded._cylindrical_surface_node_ids(
                reference, nodes, reference["origin"], reference["axis"])
            for node in ids:
                cylinders[node] = reference
    return cylinders


class _DiagramVector:
    def __init__(self, origin, value, cylinder=None):
        self.origin = origin
        self.value = value
        self.cylinder = cylinder


def _diagram_vectors(fem_part, assembly, sample=None):
    if not _fem_part_visible(fem_part):
        return []

    vectors = []
    placement = _mesh_placement_at_sample(fem_part, sample)
    inp_vectors = _diagram_vectors_from_matching_inp(fem_part, sample, placement)
    if inp_vectors is not None:
        return inp_vectors

    loads = list(_mbd_joint_cylindrical_hole_loads(fem_part, assembly, sample))
    mesh_nodes = {}
    if any(load.get("nodes") is None for load in loads):
        mesh_nodes = FreeCADMbDFEMEmbedded._fem_mesh_nodes(getattr(fem_part, "mesh", None))
    for load in loads:
        mesh_nodes.update(load.get("nodes") or {})
    cylinders = _cylindrical_node_geometry(fem_part, mesh_nodes)
    for load in loads:
        nodes = load.get("nodes")
        if nodes is None:
            nodes = mesh_nodes
        components = load.get("cload_components")
        records_by_component = components.values() if components is not None else [load.get("cloads", [])]
        for records in records_by_component:
            component_vectors = {}
            for node_id, dof, value in records:
                vector = component_vectors.setdefault(node_id, App.Vector())
                vector[dof - 1] += value
            for node_id, vector in component_vectors.items():
                if node_id in nodes and vector.Length > _ZERO_TOLERANCE:
                    vectors.append(_DiagramVector(
                        _global_point(placement, nodes[node_id]),
                        _global_vector(placement, vector),
                        cylinders.get(node_id) if load.get("face_pair_type") == "CylCyl" else None,
                    ))
    return vectors


def _diagram_vectors_from_matching_inp(fem_part, sample, placement):
    inp_file_name = _sample_inp_file_name(fem_part, sample)
    if not inp_file_name:
        return None

    try:
        with open(inp_file_name, "r", encoding="utf-8") as inp_file:
            content = inp_file.read()
    except OSError:
        return None

    mesh_object = getattr(fem_part, "mesh", None)
    nodes = FreeCADMbDFEMEmbedded._fem_mesh_nodes(mesh_object) if mesh_object is not None else {}
    if not nodes:
        return None

    mesh_signature = FreeCADMbDFEMEmbedded._fem_mesh_signature(mesh_object, nodes)
    if not mesh_signature:
        return None
    if not _matching_cload_frame_metadata(inp_file_name, mesh_signature):
        return None

    nodal_vectors, load_types = _cload_vectors_from_inp_content(content, separate=True, with_types=True)
    if not nodal_vectors:
        return None

    vectors = []
    cylinders = _cylindrical_node_geometry(fem_part, nodes)
    for key in sorted(nodal_vectors):
        node_id = key[1]
        if node_id not in nodes:
            return None
        local_vector = nodal_vectors[key]
        if local_vector.Length <= _ZERO_TOLERANCE:
            continue
        origin = _global_point(placement, nodes[node_id])
        vector = _global_vector(placement, local_vector)
        vectors.append(_DiagramVector(
            origin, vector, cylinders.get(node_id) if load_types[key] == "CylCyl" else None))
    return vectors


def _sample_inp_file_name(fem_part, sample):
    if sample is None:
        return None
    try:
        state_index = int(sample[3])
    except Exception:
        return None
    try:
        working_dir = FreeCADMbDBackend.default_calculix_working_dir(fem_part, state_index)
    except Exception:
        return None
    return str(working_dir / f"{FreeCADMbDBackend.CALCULIX_BASE_NAME}.inp")


def _matching_cload_frame_metadata(inp_file_name, mesh_signature):
    sidecar_file_name = FreeCADMbDFEMEmbedded._frame_metadata_sidecar_file_name_for_inp(
        inp_file_name
    )
    metadata = FreeCADMbDFEMEmbedded._read_frame_metadata_sidecar(sidecar_file_name)
    artifact = metadata.get("artifacts", {}).get(FreeCADMbDFEMEmbedded._MBD_CLOAD_ARTIFACT, {})
    if artifact.get("algorithm") != FreeCADMbDFEMEmbedded._MBD_CLOAD_ALGORITHM:
        return False
    if artifact.get("mesh_signature") != mesh_signature:
        return False
    source = artifact.get("source", "")
    return not source or source == os.path.basename(inp_file_name)


def _cload_vectors_from_inp_content(content, separate=False, with_types=False):
    markers = [
        FreeCADMbDFEMEmbedded._MBD_JOINT_CLOAD_MARKER.strip(),
        FreeCADMbDFEMEmbedded._MBD_LEGACY_JOINT_CYLINDER_LOAD_MARKER.strip(),
    ]
    marker_at = max(content.rfind(marker) for marker in markers)
    if marker_at < 0:
        return ({}, {}) if with_types else {}

    vectors = {}
    load_types = {}
    load_type = "CylCyl"
    component = 0
    in_cload = False
    for raw_line in content[marker_at:].splitlines():
        line = raw_line.strip()
        if line.startswith("** MbDFEM "):
            component += 1
            load_type = "AnnuAnnu" if "annular combined" in line else "CylCyl"
        if not line or line.startswith("**"):
            continue
        if line.startswith("*"):
            in_cload = line.upper().startswith("*CLOAD")
            if in_cload:
                component += 1
                load_type = "CylCyl"
            continue
        if not in_cload:
            continue
        fields = [field.strip() for field in line.split(",")]
        if len(fields) < 3:
            continue
        try:
            node_id = int(fields[0])
            dof = int(fields[1])
            value = float(fields[2])
        except ValueError:
            continue
        if dof < 1 or dof > 3:
            continue
        key = (component, node_id) if separate else node_id
        load_types[key] = load_type
        vector = vectors.setdefault(key, App.Vector())
        if dof == 1:
            vector.x += value
        elif dof == 2:
            vector.y += value
        else:
            vector.z += value
    return (vectors, load_types) if with_types else vectors


def _mbd_joint_cylindrical_hole_loads(fem_part, assembly, sample):
    mesh_object = getattr(fem_part, "mesh", None)
    nodes = FreeCADMbDFEMEmbedded._fem_mesh_nodes(mesh_object) if mesh_object is not None else {}
    mbd_part = getattr(fem_part, "mbdItem", None)
    if not nodes or assembly is None or mbd_part is None:
        return []

    loads = []
    for joint, _marker, _sign in FreeCADMbDFEMEmbedded._part_joints_for_fem_part(fem_part):
        for load in FreeCADMbDFEMEmbedded._joint_loads_for_fem_part(
            joint,
            mbd_part,
            nodes,
            sample=sample,
        ):
            load["nodes"] = nodes
            loads.append(load)
    return loads


def _update_active_face_views(controller, sample):
    assembly = getattr(controller, "assembly", None)
    for key, state in list(_face_view_states.items()):
        fem_part = state.get("fem_part")
        display_object = state.get("display_object")
        if not _face_view_state_is_valid(state):
            _face_view_states.pop(key, None)
            continue
        if FreeCADMbDFEMEmbedded._owning_mbd_assembly(fem_part) is not assembly:
            continue

        face_regions = _mbd_joint_cylindrical_face_regions(fem_part, assembly)
        try:
            display_object.FemMesh = _cload_faces_fem_mesh(
                state.get("mesh_object"),
                face_regions,
            )
        except Exception:
            pass
        _set_property(display_object, "Placement", _cload_faces_display_placement(fem_part))


def _face_view_state_is_valid(state):
    fem_part = state.get("fem_part")
    display_object = state.get("display_object")
    return (
        fem_part is not None
        and display_object is not None
        and getattr(fem_part, "Document", None) is not None
        and getattr(display_object, "Document", None) is not None
    )


def _cload_faces_display_placement(fem_part):
    mesh_object = getattr(fem_part, "mesh", None)
    try:
        return App.Placement(mesh_object.Placement)
    except Exception:
        return App.Placement()


def _mbd_joint_cylindrical_face_regions(fem_part, assembly):
    mesh_object = getattr(fem_part, "mesh", None)
    nodes = FreeCADMbDFEMEmbedded._fem_mesh_nodes(mesh_object) if mesh_object is not None else {}
    mbd_part = getattr(fem_part, "mbdItem", None)
    if not nodes or assembly is None or mbd_part is None:
        return []

    regions = []
    for joint, marker, sign in FreeCADMbDFEMEmbedded._part_joints_for_fem_part(fem_part):
        for face_pair in FreeCADMbDFEMEmbedded._joint_face_pairs(joint):
            if face_pair.get("type") not in ("CylCyl", "AnnuAnnu"):
                continue
            side = FreeCADMbDFEMEmbedded._face_pair_side_for_part(face_pair, mbd_part)
            if side is None:
                continue
            if face_pair.get("type") == "AnnuAnnu":
                import MbDFEM

                load = MbDFEM.annuAnnuFaceLoad(
                    face_pair["object"], mbd_part, list(sorted(nodes.items())),
                    App.Vector(), App.Vector(), App.Vector(),
                )
                node_ids = sorted(node for ids in load["force_quadrants"].values() for node in ids)
                if node_ids:
                    regions.append({"joint": joint, "face_pair": face_pair,
                                    "surface_node_ids": node_ids})
                continue
            reference = FreeCADMbDFEMEmbedded._cylindrical_face_reference(
                face_pair.get("face{}".format(side))
            )
            if reference is None:
                continue
            node_ids = FreeCADMbDFEMEmbedded._cylindrical_surface_node_ids(
                reference,
                nodes,
                reference["origin"],
                reference["axis"],
            )
            if not node_ids:
                continue
            regions.append(
                {
                    "joint": joint,
                    "face_pair": face_pair,
                    "surface_node_ids": node_ids,
                }
            )
    return regions


def _marker_cylindrical_surface_node_ids(marker, nodes):
    reference = FreeCADMbDFEMEmbedded._marker_cylindrical_reference(marker)
    if reference is None:
        return []
    try:
        origin = App.Vector(marker.Placement.Base)
        z_axis = marker.Placement.Rotation.multVec(App.Vector(0, 0, 1))
    except Exception:
        return []
    return FreeCADMbDFEMEmbedded._cylindrical_surface_node_ids(
        reference,
        nodes,
        origin,
        z_axis,
    )


def _cload_faces_fem_mesh(mesh_object, face_regions):
    import Fem

    source_mesh = mesh_object.FemMesh
    face_node_lists = []
    seen_faces = set()
    for face_region in face_regions:
        surface_node_ids = _face_region_surface_node_ids(face_region)
        for face_nodes in _mesh_surface_face_node_lists(source_mesh, surface_node_ids):
            key = tuple(sorted(face_nodes))
            if key in seen_faces:
                continue
            seen_faces.add(key)
            face_node_lists.append(face_nodes)

    if not face_node_lists:
        raise ValueError("No mesh facets found for active joint CLOAD faces.")

    display_mesh = Fem.FemMesh()
    node_ids = sorted({node_id for face_nodes in face_node_lists for node_id in face_nodes})
    for node_id in node_ids:
        point = source_mesh.Nodes.get(node_id)
        if point is None:
            point = source_mesh.getNodeById(node_id)
        display_mesh.addNode(point.x, point.y, point.z, node_id)

    for face_id, face_nodes in enumerate(face_node_lists, start=1):
        display_mesh.addFace(face_nodes, face_id)
    return display_mesh


def _face_region_surface_node_ids(face_region):
    if "surface_node_ids" in face_region:
        return {int(node_id) for node_id in face_region.get("surface_node_ids", [])}

    node_ids = set()
    for octant_node_ids in face_region.get("octants", {}).values():
        node_ids.update(int(node_id) for node_id in octant_node_ids)
    return node_ids


def _mesh_surface_face_node_lists(source_mesh, surface_node_ids):
    surface_node_ids = {int(node_id) for node_id in surface_node_ids}
    if not surface_node_ids:
        return []

    face_node_lists = []
    for face_id in getattr(source_mesh, "Faces", ()):
        face_nodes = [int(node_id) for node_id in source_mesh.getElementNodes(int(face_id))]
        if _face_is_on_surface(face_nodes, surface_node_ids):
            face_node_lists.append(face_nodes)

    if face_node_lists:
        return face_node_lists

    return _volume_boundary_face_node_lists(source_mesh, surface_node_ids)


def _volume_boundary_face_node_lists(source_mesh, surface_node_ids):
    faces = {}
    for volume_id in getattr(source_mesh, "Volumes", ()):
        volume_nodes = [int(node_id) for node_id in source_mesh.getElementNodes(int(volume_id))]
        face_definitions = _VOLUME_FACE_NODE_INDICES.get(len(volume_nodes), ())
        for face_definition in face_definitions:
            face_nodes = [volume_nodes[index] for index in face_definition]
            key = tuple(sorted(face_nodes))
            count, stored_nodes = faces.get(key, (0, face_nodes))
            faces[key] = (count + 1, stored_nodes)

    return [
        face_nodes
        for count, face_nodes in faces.values()
        if count == 1 and _face_is_on_surface(face_nodes, surface_node_ids)
    ]


def _face_is_on_surface(face_nodes, surface_node_ids):
    return all(int(node_id) in surface_node_ids for node_id in face_nodes)


def _fem_part_visible(fem_part):
    return bool(getattr(fem_part, "Visibility", True))


def _mesh_placement_at_sample(fem_part, sample):
    mbd_part = getattr(fem_part, "mbdItem", None)
    if mbd_part is not None and sample is not None and _has_sampled_placement(mbd_part):
        return FreeCADMbDFreeBodyDiagram._placement_at_sample(mbd_part, sample)

    mesh_object = getattr(fem_part, "mesh", None)
    try:
        return FreeCADMbDFreeBodyDiagram._global_placement(mesh_object)
    except Exception:
        pass

    try:
        return FreeCADMbDFreeBodyDiagram._global_placement(fem_part)
    except Exception:
        return App.Placement(fem_part.Placement)


def _current_animation_sample(assembly):
    try:
        parameters = assembly.getAnimationParameters()
    except Exception:
        parameters = None
    try:
        frame = int(getattr(parameters, "currentFrame"))
    except Exception:
        frame = 0
    return (frame, frame, 0.0, frame)


def _has_sampled_placement(mbd_part):
    has_position = any(list(getattr(mbd_part, name, [])) for name in ("xs", "ys", "zs"))
    has_rotation = all(list(getattr(mbd_part, name, [])) for name in ("bryxs", "bryys", "bryzs"))
    return has_position or has_rotation


def _global_point(placement, point):
    return placement.multVec(App.Vector(point.x, point.y, point.z))


def _global_vector(placement, vector):
    return placement.Rotation.multVec(App.Vector(vector.x, vector.y, vector.z))


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


def _diagram_scale(fem_part, assembly, vectors=None):
    scale_owner = FreeCADMbDFEMDLOADs._scale_owner(assembly)
    if not _auto_scale_enabled(scale_owner):
        return _view_scale_multiplier(scale_owner)

    key = FreeCADMbDFreeBodyDiagram._assembly_key(scale_owner)
    if key in _prepared_auto_scales:
        return prepare_diagram_scale(assembly)

    maximum = max((vector.value.Length for vector in vectors or ()), default=0.0)
    if maximum <= _ZERO_TOLERANCE:
        return _view_scale_multiplier(scale_owner)

    diagonal = max(_current_bounding_box_diagonal(assembly), 1.0)
    return (
        diagonal
        * _AUTO_SCALE_DIAGONAL_FRACTION
        / maximum
        * _view_scale_multiplier(scale_owner)
    )


def _auto_scale_enabled(assembly):
    return FreeCADMbDFreeBodyDiagram._view_property_bool(
        assembly,
        "CLOADAutoScale",
        _DEFAULT_CLOAD_AUTO_SCALE,
    )


def _view_scale_multiplier(assembly):
    return FreeCADMbDFreeBodyDiagram._view_property_float(
        assembly,
        "CLOADScale",
        _DEFAULT_CLOAD_SCALE,
    )


def _current_bounding_box_diagonal(assembly):
    points = []
    for part in FreeCADMbDFreeBodyDiagram._assembly_parts(assembly):
        if not hasattr(part, "Shape"):
            continue
        points.extend(
            FreeCADMbDFreeBodyDiagram._bound_box_points(
                part.Shape.BoundBox,
                part.Placement,
            )
        )

    if not points:
        return 1.0

    xmin = min(point.x for point in points)
    xmax = max(point.x for point in points)
    ymin = min(point.y for point in points)
    ymax = max(point.y for point in points)
    zmin = min(point.z for point in points)
    zmax = max(point.z for point in points)
    return App.Vector(xmax - xmin, ymax - ymin, zmax - zmin).Length


def _assembly_auto_diagram_scale(assembly):
    diagonal = max(FreeCADMbDFreeBodyDiagram._motion_bounding_box_diagonal(assembly), 1.0)
    maximum = 0.0
    for fem_part in FreeCADMbDFEMDLOADs._assembly_fem_parts(assembly):
        for sample in FreeCADMbDFreeBodyDiagram._result_samples(assembly):
            for vector in _diagram_vectors_for_scale(fem_part, assembly, sample):
                maximum = max(maximum, vector.value.Length)
    if maximum <= _ZERO_TOLERANCE:
        return 1.0
    return (diagonal * _AUTO_SCALE_DIAGONAL_FRACTION) / maximum


def _diagram_vectors_for_scale(fem_part, assembly, sample):
    return _diagram_vectors(fem_part, assembly, sample)
