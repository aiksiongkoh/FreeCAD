# SPDX-License-Identifier: LGPL-2.1-or-later

"""Coin overlay arrows for MbDPart free-body diagrams."""

from math import acos, degrees, hypot

import FreeCAD as App


_POSITION_PROPERTIES = ("xs", "ys", "zs")
_BRYANT_PROPERTIES = ("bryxs", "bryys", "bryzs")
_FORCE_PROPERTIES = ("fxs", "fys", "fzs")
_TORQUE_PROPERTIES = ("txs", "tys", "tzs")
_ACCELERATION_PROPERTIES = ("axs", "ays", "azs")
_ALPHA_PROPERTIES = ("alpxs", "alpys", "alpzs")
_OMEGA_PROPERTIES = ("omexs", "omeys", "omezs")
_RESULT_LENGTH_TO_DOCUMENT_LENGTH = 1.0
_DOCUMENT_LENGTH_TO_SI_LENGTH = 0.001
_AXIS_CROSS_LINE_WIDTH = 1
_AXIS_CROSS_HEAD_LENGTH = 15.0
_AXIS_CROSS_HEAD_RADIUS = 2.5
_LOAD_ARROW_HEAD_LENGTH = 6.0
_LOAD_ARROW_HEAD_LINE_WIDTH = _AXIS_CROSS_LINE_WIDTH * 3
_LOAD_ARROW_DOT_DIAMETER = _AXIS_CROSS_LINE_WIDTH * 3
_GRAVITY_COLOR = (0.0, 0.85, 0.95)
_FORCE_COLOR = (0.90, 0.10, 0.08)
_TORQUE_COLOR = (0.05, 0.25, 0.95)
_DEFAULT_FREE_BODY_AUTO_SCALE = True
_DEFAULT_FREE_BODY_FORCE_SCALE = 1.0
_DEFAULT_FREE_BODY_TORQUE_SCALE = 1.0
_AUTO_SCALE_DIAGONAL_FRACTION = 0.1

_diagrams = {}
_prepared_auto_scales = {}


def install():
    """Register the MbDFEM free-body diagram GUI command."""
    import FreeCADGui as Gui

    Gui.addCommand("MbDFEM_FreeBodyDiagram", FreeBodyDiagramCommand())


def update_active_diagrams(controller, sample):
    """Refresh every visible diagram belonging to *controller*'s assembly."""
    if not _diagrams:
        return

    prepare_diagram_scales(controller.assembly)
    for key, diagram in list(_diagrams.items()):
        if diagram.assembly is controller.assembly:
            if not diagram.is_valid():
                _diagrams.pop(key, None)
                diagram.remove()
            else:
                diagram.update(sample)


def refresh_assembly_diagrams(document_name, assembly_name, force_scale_prepare=False):
    """Refresh visible diagrams for the named assembly after a property edit."""
    document = App.getDocument(document_name)
    assembly = document.getObject(assembly_name) if document is not None else None
    if assembly is None:
        return

    if force_scale_prepare:
        prepare_diagram_scales(assembly, force=True)
    for key, diagram in list(_diagrams.items()):
        if diagram.assembly is assembly:
            if not diagram.is_valid():
                _diagrams.pop(key, None)
                diagram.remove()
            else:
                frame = diagram.current_frame
                diagram.update((frame, frame, 0.0, frame))


def prepare_diagram_scales(assembly, force=False):
    """Prepare the assembly-wide FreeBodyDiagram auto scale used during animation."""
    if not _auto_scale_enabled(assembly):
        return _view_scale_multipliers(assembly)

    key = _assembly_key(assembly)
    if force or key not in _prepared_auto_scales:
        _prepared_auto_scales[key] = _assembly_auto_diagram_scales(assembly)

    return _scales_with_multipliers(assembly, _prepared_auto_scales[key])


def reset_diagram_scales(assembly=None):
    """Forget prepared FreeBodyDiagram scales."""
    if assembly is None:
        _prepared_auto_scales.clear()
        return
    _prepared_auto_scales.pop(_assembly_key(assembly), None)


def active_parts():
    """Return selected MbDPart objects, resolving selected children when possible."""
    import FreeCAD as App
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
        for part in _parts_from_object(obj):
            if part is not None and part.Name not in seen:
                parts.append(part)
                seen.add(part.Name)

    if parts:
        return parts

    try:
        selection = Gui.Selection.getSelectionEx(document.Name)
    except Exception:
        selection = []

    for selected in selection:
        for part in _parts_from_selection(selected):
            if part is not None and part.Name not in seen:
                parts.append(part)
                seen.add(part.Name)

    return parts


def _parts_from_object(obj):
    if _is_part(obj):
        return [obj]

    part = _part_containing_marker(obj)
    return [part] if part is not None else []


def _parts_from_selection(selected):
    obj = getattr(selected, "Object", None)
    if _is_part(obj):
        return [obj]

    sub_names = list(getattr(selected, "SubElementNames", []))
    if obj is not None and sub_names:
        for sub_name in sub_names:
            try:
                sub_object = obj.getSubObject(sub_name)
            except Exception:
                sub_object = None
            if _is_part(sub_object):
                return [sub_object]

    part = _part_containing_marker(obj)
    return [part] if part is not None else []


def _is_part(obj):
    try:
        return obj is not None and obj.isDerivedFrom("MbDFEM::MbDPart")
    except Exception:
        return False


def _is_marker(obj):
    try:
        return obj is not None and obj.isDerivedFrom("MbDFEM::MbDMarker")
    except Exception:
        return False


def _part_containing_marker(marker):
    if not _is_marker(marker) or marker.Document is None:
        return None

    for obj in marker.Document.Objects:
        try:
            if obj.isDerivedFrom("MbDFEM::MbDPart") and marker in obj.markers:
                return obj
        except Exception:
            pass
    return None


def _assembly_containing_part(part):
    if part is None or part.Document is None:
        return None

    for obj in part.Document.Objects:
        try:
            if obj.isDerivedFrom("MbDFEM::MbDAssembly"):
                if part in obj.parts or part in obj.fixedparts:
                    return obj
        except Exception:
            pass
    return None


def _diagram_key(part):
    return (part.Document.Name, part.Name)


def _toggle_part(part):
    key = _diagram_key(part)
    diagram = _diagrams.pop(key, None)
    if diagram is not None:
        diagram.remove()
        return False

    assembly = _assembly_containing_part(part)
    if assembly is None:
        App.Console.PrintError("MbDPart is not contained by an MbDAssembly.\n")
        return False

    diagram = None
    try:
        diagram = FreeBodyDiagram(part, assembly)
        diagram.update((diagram.current_frame, diagram.current_frame, 0.0, diagram.current_frame))
    except Exception as exc:
        if diagram is not None:
            diagram.remove()
        App.Console.PrintError(f"FreeBodyDiagram failed: {exc}\n")
        return False

    _diagrams[key] = diagram
    return True


class FreeBodyDiagramCommand:
    """Toggle a free-body diagram overlay for selected MbDPart objects."""

    def GetResources(self):
        return {
            "MenuText": "FreeBodyDiagram",
            "ToolTip": "Toggle force and torque arrows for the selected MbDPart",
        }

    def IsActive(self):
        return App.ActiveDocument is not None

    def Activated(self):
        parts = active_parts()
        if not parts:
            App.Console.PrintError("Select an MbDPart to toggle its FreeBodyDiagram.\n")
            return

        for part in parts:
            _toggle_part(part)


class FreeBodyDiagram:
    """Scene graph overlay tied to one MbDPart."""

    def __init__(self, part, assembly):
        from pivy import coin

        self.part = part
        self.assembly = assembly
        self._coin = coin
        self.current_frame = 0
        self.root = coin.SoSeparator()
        self.root.ref()
        self.arrows = []
        self._view = _active_view(part)
        self._scene_graph = self._view.getSceneGraph()
        self._scene_graph.addChild(self.root)

    def is_valid(self):
        return self.part.Document is not None and self.assembly.Document is not None

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
        vectors = _diagram_vectors(self.part, self.assembly, sample)
        force_scale, torque_scale = _prepared_diagram_scales(self.assembly)
        self._ensure_arrows(len(vectors))
        for arrow, vector in zip(self.arrows, vectors):
            scale = _scale_for_vector(vector.kind, force_scale, torque_scale)
            color = _color_for_vector(vector.kind)
            arrow.update(vector.origin, vector.value, scale, color)
        for arrow in self.arrows[len(vectors) :]:
            arrow.hide()

    def _ensure_arrows(self, count):
        while len(self.arrows) < count:
            arrow = _make_arrow(self._coin)
            self.arrows.append(arrow)
            self.root.addChild(arrow.root)


def _make_arrow(coin, use_load_style=False, view=None):
    arrow = _Arrow.__new__(_Arrow)
    arrow._coin = coin
    arrow.use_load_style = use_load_style
    arrow._view = view
    arrow.root = coin.SoSeparator()
    arrow._node = None
    arrow.length = 0.0
    arrow.shaft_length = 0.0
    arrow.head_length = 0.0
    arrow.head_line_width = 0
    arrow.dot_diameter = 0
    arrow.color = _FORCE_COLOR
    return arrow


class _Arrow:
    def __init__(self, coin=None):
        if coin is None:
            import pivy.coin as coin
        made = _make_arrow(coin)
        self.__dict__.update(made.__dict__)

    def update(self, origin, vector, scale, color=_FORCE_COLOR):
        magnitude = vector.Length
        length = magnitude * scale
        if length <= 1.0e-9:
            self.hide()
            return

        direction = _vector_copy(vector)
        direction.normalize()
        rotation = _rotation_from_y_axis(direction)

        if self.use_load_style:
            head_length = _LOAD_ARROW_HEAD_LENGTH
            projected_length = _screen_vector_length(self._view, origin, direction, length)
            use_dot = projected_length < head_length
            model_head_length = _model_length_for_screen_pixels(
                self._view,
                origin,
                direction,
                length,
                head_length,
            )
            shaft_length = 0.0 if use_dot else max(length - model_head_length, 0.0)
            head_line_width = _LOAD_ARROW_HEAD_LINE_WIDTH
            dot_diameter = _LOAD_ARROW_DOT_DIAMETER if use_dot else 0

            self.length = length
            self.shaft_length = shaft_length
            self.head_length = 0.0 if use_dot else model_head_length
            self.head_line_width = head_line_width
            self.dot_diameter = dot_diameter
            self.color = color
            self._replace_node(
                _load_arrow_iv_text(
                    origin,
                    rotation,
                    shaft_length,
                    self.head_length,
                    head_line_width,
                    dot_diameter,
                    color,
                )
            )
            return

        head_length = _AXIS_CROSS_HEAD_LENGTH
        shaft_length = max(length - head_length, 0.0)
        head_radius = _AXIS_CROSS_HEAD_RADIUS

        self.length = length
        self.shaft_length = shaft_length
        self.head_length = head_length
        self.head_radius = head_radius
        self.color = color
        self._replace_node(
            _arrow_iv_text(origin, rotation, shaft_length, head_length, head_radius, color)
        )

    def hide(self):
        self.length = 0.0
        self._replace_node(None)

    def _replace_node(self, text):
        if self._node is not None:
            try:
                self.root.removeChild(self._node)
            except Exception:
                pass
            self._node = None

        if text is None:
            return

        data = text.encode("ascii")
        inp = self._coin.SoInput()
        inp.setBuffer(data)
        self._node = self._coin.SoDB.readAll(inp)
        if self._node is not None:
            self.root.addChild(self._node)


def _load_arrow_iv_text(
    origin,
    rotation,
    shaft_length,
    head_length,
    head_line_width,
    dot_diameter,
    color,
):
    axis, angle = _rotation_axis_angle(rotation)
    if dot_diameter:
        geometry = (
            f"  DrawStyle {{ pointSize {dot_diameter} }}\n"
            "  Coordinate3 {\n"
            "    point [ 0 0 0 ]\n"
            "  }\n"
            "  PointSet { numPoints 1 }\n"
        )
    else:
        shaft_geometry = ""
        if shaft_length > 0.0:
            shaft_geometry = (
                f"  DrawStyle {{ lineWidth {_AXIS_CROSS_LINE_WIDTH} }}\n"
                "  Coordinate3 {\n"
                f"    point [ 0 0 0, 0 {_ff(shaft_length)} 0 ]\n"
                "  }\n"
                "  LineSet { numVertices [ 2 ] }\n"
            )
        geometry = (
            shaft_geometry
            + f"  DrawStyle {{ lineWidth {head_line_width} }}\n"
            + "  Coordinate3 {\n"
            + f"    point [ 0 {_ff(shaft_length)} 0, 0 {_ff(shaft_length + head_length)} 0 ]\n"
            + "  }\n"
            + "  LineSet { numVertices [ 2 ] }\n"
        )
    return (
        "#Inventor V2.1 ascii\n"
        "Separator {\n"
        "  PickStyle { style UNPICKABLE }\n"
        "  LightModel { model BASE_COLOR }\n"
        "  Material {\n"
        f"    diffuseColor {_ff(color[0])} {_ff(color[1])} {_ff(color[2])}\n"
        "    transparency 0.05\n"
        "  }\n"
        "  Transform {\n"
        f"    translation {_ff(origin.x)} {_ff(origin.y)} {_ff(origin.z)}\n"
        f"    rotation {_ff(axis.x)} {_ff(axis.y)} {_ff(axis.z)} {_ff(angle)}\n"
        "  }\n"
        f"{geometry}"
        "}\n"
    )


def _screen_vector_length(view, origin, direction, length):
    if view is None:
        return float("inf")

    try:
        tip = origin + direction * length
        start_px = view.getPointOnViewport(origin)
        tip_px = view.getPointOnViewport(tip)
        return hypot(float(tip_px[0]) - float(start_px[0]), float(tip_px[1]) - float(start_px[1]))
    except Exception:
        return float("inf")


def _model_length_for_screen_pixels(view, origin, direction, length, pixels):
    if view is None:
        return min(length, pixels)

    try:
        tip = origin + direction * length
        tip_px = view.getPointOnViewport(tip)
        low = 0.0
        high = length
        for _ in range(24):
            mid = (low + high) * 0.5
            tail = tip - direction * mid
            tail_px = view.getPointOnViewport(tail)
            screen_length = hypot(
                float(tip_px[0]) - float(tail_px[0]),
                float(tip_px[1]) - float(tail_px[1]),
            )
            if screen_length < pixels:
                low = mid
            else:
                high = mid
        return high
    except Exception:
        return min(length, pixels)


def _arrow_iv_text(origin, rotation, shaft_length, head_length, head_radius, color):
    axis, angle = _rotation_axis_angle(rotation)
    return (
        "#Inventor V2.1 ascii\n"
        "Separator {\n"
        "  PickStyle { style UNPICKABLE }\n"
        "  LightModel { model BASE_COLOR }\n"
        "  Material {\n"
        f"    diffuseColor {_ff(color[0])} {_ff(color[1])} {_ff(color[2])}\n"
        "    transparency 0.05\n"
        "  }\n"
        f"  DrawStyle {{ lineWidth {_AXIS_CROSS_LINE_WIDTH} }}\n"
        "  Transform {\n"
        f"    translation {_ff(origin.x)} {_ff(origin.y)} {_ff(origin.z)}\n"
        f"    rotation {_ff(axis.x)} {_ff(axis.y)} {_ff(axis.z)} {_ff(angle)}\n"
        "  }\n"
        "  Coordinate3 {\n"
        f"    point [ 0 0 0, 0 {_ff(shaft_length)} 0 ]\n"
        "  }\n"
        "  LineSet { numVertices [ 2 ] }\n"
        "  Separator {\n"
        f"    Transform {{ translation 0 {_ff(shaft_length + head_length * 0.5)} 0 }}\n"
        f"    Cone {{ bottomRadius {_ff(head_radius)} height {_ff(head_length)} }}\n"
        "  }\n"
        "}\n"
    )

def _color_for_vector(kind):
    if kind == "gravity":
        return _GRAVITY_COLOR
    if kind == "torque":
        return _TORQUE_COLOR
    return _FORCE_COLOR


def _scale_for_vector(kind, force_scale, torque_scale):
    return torque_scale if kind == "torque" else force_scale


def _rotation_axis_angle(rotation):
    axis = App.Vector(0, 1, 0)
    angle = 0.0
    try:
        axis = rotation.Axis
        angle = rotation.Angle
    except Exception:
        try:
            q = rotation.Q
            angle = 2.0 * acos(max(-1.0, min(1.0, float(q[3]))))
            s = (1.0 - float(q[3]) * float(q[3])) ** 0.5
            if s > 1.0e-12:
                axis = App.Vector(float(q[0]) / s, float(q[1]) / s, float(q[2]) / s)
        except Exception:
            pass
    return axis, angle


def _ff(value):
    return f"{float(value):.17g}"


class _DiagramVector:
    def __init__(self, kind, origin, value):
        self.kind = kind
        self.origin = origin
        self.value = value


def _active_view(part):
    import FreeCADGui as Gui

    if part.Document is None:
        raise RuntimeError("MbDPart has no document")
    gui_doc = Gui.getDocument(part.Document.Name)
    if gui_doc is None:
        raise RuntimeError(f"Document {part.Document.Name} has no GUI document")
    return gui_doc.ActiveView


def _vector_copy(vector):
    return App.Vector(float(vector.x), float(vector.y), float(vector.z))


def _rotation_from_y_axis(direction):
    from math import acos

    y_axis = App.Vector(0, 1, 0)
    dot = max(-1.0, min(1.0, y_axis.dot(direction)))
    if dot > 1.0 - 1.0e-12:
        return App.Rotation()
    if dot < -1.0 + 1.0e-12:
        return App.Rotation(App.Vector(1, 0, 0), 180)

    axis = y_axis.cross(direction)
    axis.normalize()
    return App.Rotation(axis, degrees(acos(dot)))


def _diagram_vectors(part, assembly, sample):
    vectors = []
    mass_marker = part.getMassMarker() if hasattr(part, "getMassMarker") else None
    if mass_marker is not None:
        origin = part.getGlobalPlacement().multVec(mass_marker.Placement.Base)
        mass = float(getattr(mass_marker, "mass", 0.0))
        vectors.append(
            _DiagramVector("force", origin, _dalembert_force(part, mass_marker, mass, sample))
        )
        vectors.append(
            _DiagramVector("torque", origin, _dalembert_torque(part, mass_marker, sample))
        )
        vectors.append(_DiagramVector("gravity", origin, _gravity_force(assembly, mass)))

    for joint, marker, sign in _part_joints(part, assembly):
        origin = part.getGlobalPlacement().multVec(marker.Placement.Base)
        force = _sample_vector(joint, _FORCE_PROPERTIES, sample) * sign
        torque = _sample_vector(joint, _TORQUE_PROPERTIES, sample) * sign
        vectors.append(_DiagramVector("force", origin, force))
        vectors.append(_DiagramVector("torque", origin, torque))

    return vectors


def _dalembert_force(part, mass_marker, mass, sample):
    acceleration = (
        _sample_vector(part, _ACCELERATION_PROPERTIES, sample)
        * _DOCUMENT_LENGTH_TO_SI_LENGTH
    )
    alpha = _sample_vector(part, _ALPHA_PROPERTIES, sample)
    omega = _sample_vector(part, _OMEGA_PROPERTIES, sample)
    radius = (
        part.getGlobalPlacement().Rotation.multVec(mass_marker.Placement.Base)
        * _DOCUMENT_LENGTH_TO_SI_LENGTH
    )
    com_acceleration = acceleration + alpha.cross(radius) + omega.cross(omega.cross(radius))
    return com_acceleration * (-mass)


def _dalembert_torque(part, mass_marker, sample):
    inertias = getattr(mass_marker, "principalInertias", App.Vector())
    alpha = _sample_vector(part, _ALPHA_PROPERTIES, sample)
    omega = _sample_vector(part, _OMEGA_PROPERTIES, sample)
    rotation = part.getGlobalPlacement().Rotation.multiply(mass_marker.Placement.Rotation)
    inertia_alpha = _inertia_vector(rotation, inertias, alpha)
    angular_momentum = _inertia_vector(rotation, inertias, omega)
    return (inertia_alpha + omega.cross(angular_momentum)) * -1.0


def _inertia_vector(rotation, inertias, vector):
    axes = (
        rotation.multVec(App.Vector(1, 0, 0)),
        rotation.multVec(App.Vector(0, 1, 0)),
        rotation.multVec(App.Vector(0, 0, 1)),
    )
    moments = (float(inertias.x), float(inertias.y), float(inertias.z))
    result = App.Vector()
    for axis, moment in zip(axes, moments):
        result += axis * (moment * vector.dot(axis))
    return result


def _gravity_force(assembly, mass):
    gravity = None
    try:
        gravity = assembly.getGravity()
    except Exception:
        gravity = getattr(assembly, "gravity", None)
    value = getattr(gravity, "gravity", App.Vector(0, 0, -9810.0))
    return App.Vector(value.x, value.y, value.z) * _DOCUMENT_LENGTH_TO_SI_LENGTH * mass


def _part_joints(part, assembly):
    result = []
    for joint in _assembly_joints(assembly):
        marker_i = getattr(joint, "markerI", None)
        marker_j = getattr(joint, "markerJ", None)
        if _marker_belongs_to_part(marker_i, part):
            result.append((joint, marker_i, 1.0))
        if _marker_belongs_to_part(marker_j, part):
            result.append((joint, marker_j, -1.0))
    return result


def _marker_belongs_to_part(marker, part):
    if marker is None:
        return False
    try:
        if marker in part.markers:
            return True
    except Exception:
        pass
    try:
        return marker.getParentGeoFeatureGroup() is part
    except Exception:
        return False


def _assembly_joints(assembly):
    joints = []
    seen = set()

    def add(joint):
        try:
            is_joint = joint is not None and joint.isDerivedFrom("MbDFEM::MbDJoint")
        except Exception:
            is_joint = False
        if is_joint and joint.Name not in seen:
            joints.append(joint)
            seen.add(joint.Name)

    for joint in list(getattr(assembly, "joints", [])):
        add(joint)

    document = getattr(assembly, "Document", None)
    if document is not None:
        for obj in document.Objects:
            add(obj)

    return joints


def _diagram_scales(part, assembly):
    return prepare_diagram_scales(assembly)


def _prepared_diagram_scales(assembly):
    return prepare_diagram_scales(assembly)


def _assembly_key(assembly):
    document = getattr(assembly, "Document", None)
    document_name = getattr(document, "Name", None)
    name = getattr(assembly, "Name", None)
    if document_name is not None and name is not None:
        return document_name, name
    return id(assembly)


def _effective_diagram_scales(assembly):
    if not _auto_scale_enabled(assembly):
        return _view_scale_multipliers(assembly)

    return _scales_with_multipliers(assembly, _assembly_auto_diagram_scales(assembly))


def _auto_scale_enabled(assembly):
    return _view_property_bool(
        assembly,
        "FreeBodyDiagramAutoScale",
        _DEFAULT_FREE_BODY_AUTO_SCALE,
    )


def _view_scale_multipliers(assembly):
    force_scale = _view_property_float(
        assembly,
        "FreeBodyDiagramForceScale",
        _DEFAULT_FREE_BODY_FORCE_SCALE,
    )
    torque_scale = _view_property_float(
        assembly,
        "FreeBodyDiagramTorqueScale",
        _DEFAULT_FREE_BODY_TORQUE_SCALE,
    )
    return force_scale, torque_scale

def _scales_with_multipliers(assembly, auto_scales):
    force_scale, torque_scale = _view_scale_multipliers(assembly)
    auto_force_scale, auto_torque_scale = auto_scales
    return auto_force_scale * force_scale, auto_torque_scale * torque_scale


def _assembly_auto_diagram_scales(assembly):
    diagonal = max(_motion_bounding_box_diagonal(assembly), 1.0)
    max_force = 0.0
    max_torque = 0.0
    for sample in _result_samples(assembly):
        for part in _assembly_parts(assembly):
            for vector in _diagram_vectors_for_scale(part, assembly, sample):
                if vector.kind != "torque":
                    max_force = max(max_force, vector.value.Length)
                else:
                    max_torque = max(max_torque, vector.value.Length)
    return _scale_for(max_force, diagonal), _scale_for(max_torque, diagonal)


def _scale_for(maximum, diagonal):
    return (diagonal * _AUTO_SCALE_DIAGONAL_FRACTION) / maximum if maximum > 1.0e-12 else 1.0


def _view_property_bool(obj, name, default):
    view_object = getattr(obj, "ViewObject", None)
    try:
        return bool(getattr(view_object, name))
    except Exception:
        return default


def _view_property_float(obj, name, default):
    view_object = getattr(obj, "ViewObject", None)
    try:
        return max(0.0, float(getattr(view_object, name)))
    except Exception:
        return default


def _assembly_parts(assembly):
    parts = []
    seen = set()
    for part in list(getattr(assembly, "fixedparts", [])) + list(getattr(assembly, "parts", [])):
        if part is not None and getattr(part, "Name", None) not in seen:
            parts.append(part)
            seen.add(part.Name)
    return parts


def _diagram_vectors_for_scale(part, assembly, sample):
    placement = App.Placement(part.Placement)
    velocity = getattr(part, "velocity", App.Vector())
    omega = getattr(part, "omega", App.Vector())
    acceleration = getattr(part, "acceleration", App.Vector())
    alpha = getattr(part, "alpha", App.Vector())
    try:
        part.Placement = _placement_at_sample(part, sample)
        part.velocity = (
            _sample_vector(part, ("vxs", "vys", "vzs"), sample)
            * _RESULT_LENGTH_TO_DOCUMENT_LENGTH
        )
        part.omega = _sample_vector(part, _OMEGA_PROPERTIES, sample)
        part.acceleration = (
            _sample_vector(part, _ACCELERATION_PROPERTIES, sample)
            * _RESULT_LENGTH_TO_DOCUMENT_LENGTH
        )
        part.alpha = _sample_vector(part, _ALPHA_PROPERTIES, sample)
        return _diagram_vectors(part, assembly, sample)
    finally:
        part.Placement = placement
        part.velocity = velocity
        part.omega = omega
        part.acceleration = acceleration
        part.alpha = alpha


def _motion_bounding_box_diagonal(assembly):
    points = []
    parts = list(getattr(assembly, "fixedparts", [])) + list(getattr(assembly, "parts", []))
    samples = _result_samples(assembly)
    for part in parts:
        if not hasattr(part, "Shape"):
            continue
        sample_list = samples if any(list(getattr(part, name, [])) for name in _POSITION_PROPERTIES) else [None]
        for sample in sample_list:
            placement = _placement_at_sample(part, sample) if sample is not None else part.Placement
            points.extend(_bound_box_points(part.Shape.BoundBox, placement))

    if not points:
        return 1.0

    xmin = min(point.x for point in points)
    xmax = max(point.x for point in points)
    ymin = min(point.y for point in points)
    ymax = max(point.y for point in points)
    zmin = min(point.z for point in points)
    zmax = max(point.z for point in points)
    return App.Vector(xmax - xmin, ymax - ymin, zmax - zmin).Length


def _bound_box_points(bound_box, placement):
    corners = []
    for x in (bound_box.XMin, bound_box.XMax):
        for y in (bound_box.YMin, bound_box.YMax):
            for z in (bound_box.ZMin, bound_box.ZMax):
                corners.append(placement.multVec(App.Vector(x, y, z)))
    return corners


def _result_samples(assembly):
    count = _source_frame_count(assembly)
    if count == 0:
        return [(0, 0, 0.0, 0)]
    return [(index, index, 0.0, index) for index in range(count)]


def _source_frame_count(assembly):
    counts = []
    for part in list(getattr(assembly, "parts", [])) + list(getattr(assembly, "fixedparts", [])):
        for name in _POSITION_PROPERTIES:
            values = list(getattr(part, name, []))
            if values:
                counts.append(len(values))
    times = list(getattr(assembly, "times", []))
    if times:
        counts.append(len(times))
    return min(counts) if counts else 0


def _placement_at_sample(part, sample):
    if sample is None or not any(list(getattr(part, name, [])) for name in _POSITION_PROPERTIES):
        return App.Placement(part.Placement)

    placement = App.Placement(part.Placement)
    placement.Base = (
        _sample_vector(part, _POSITION_PROPERTIES, sample)
        * _RESULT_LENGTH_TO_DOCUMENT_LENGTH
    )
    rotation = _rotation_at_sample(part, sample)
    if rotation is not None:
        placement.Rotation = rotation
    return placement


def _rotation_at_sample(part, sample):
    series = [list(getattr(part, name, [])) for name in _BRYANT_PROPERTIES]
    if not all(series):
        return None

    lower, upper, ratio = sample[:3]
    lower_rotation = _rotation_from_bryant(series, lower)
    if lower == upper:
        return lower_rotation
    upper_rotation = _rotation_from_bryant(series, upper)
    return lower_rotation.slerp(upper_rotation, ratio)


def _rotation_from_bryant(series, index):
    angles = []
    for values in series:
        clamped = max(0, min(index, len(values) - 1))
        angles.append(degrees(float(values[clamped])))

    x_angle, y_angle, z_angle = angles
    return (
        App.Rotation(App.Vector(0, 0, 1), z_angle)
        .multiply(App.Rotation(App.Vector(0, 1, 0), y_angle))
        .multiply(App.Rotation(App.Vector(1, 0, 0), x_angle))
    )


def _sample_vector(obj, names, sample):
    return App.Vector(*(_sample_value(list(getattr(obj, name, [])), sample) for name in names))


def _sample_value(values, sample):
    if not values:
        return 0.0
    lower, upper, ratio = sample[:3]
    lower = max(0, min(lower, len(values) - 1))
    upper = max(0, min(upper, len(values) - 1))
    if lower == upper:
        return float(values[lower])
    return float(values[lower]) + (float(values[upper]) - float(values[lower])) * ratio
