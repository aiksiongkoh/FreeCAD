# SPDX-License-Identifier: LGPL-2.1-or-later

"""Create the RealisticPendulum MbDFEM assembly setup.

Run from FreeCAD with:
    FreeCAD -c src/Mod/MbDFEM/Examples/CreateRealisticPendulumMbD.py
"""

import FreeCAD as App
import MbDFEM  # noqa: F401


DOCUMENT_PATH = (
    r"C:\Users\askoh\Documents\GitHub\aiksiongkoh\FreeCAD\feature-mbdfem"
    r"\data\examples\RealisticPendulum.FCStd"
)


def _activate_mbd_workbench():
    try:
        import FreeCADGui as Gui

        Gui.activateWorkbench("MbDFEMWorkbench")
    except Exception:
        pass


def _normalize(vector):
    normalized = App.Vector(vector.x, vector.y, vector.z)
    if normalized.Length != 0:
        normalized.normalize()
    return normalized


def _orthogonal_vector(vector):
    candidate = App.Vector(1, 0, 0) if abs(vector.x) < abs(vector.y) else App.Vector(0, 1, 0)
    return _normalize(vector.cross(candidate))


def _cylindrical_face_placement(face):
    surface = face.Surface
    z_axis = _normalize(surface.Axis)
    if z_axis.Length == 0:
        z_axis = App.Vector(0, 0, 1)

    axis_origin = getattr(surface, "Center", getattr(surface, "Location", App.Vector()))
    face_center = face.CenterOfGravity
    center = axis_origin + z_axis * ((face_center - axis_origin).dot(z_axis))

    x_axis = face_center - center
    if x_axis.Length == 0:
        x_axis = _orthogonal_vector(z_axis)
    else:
        x_axis = _normalize(x_axis)
    y_axis = _normalize(z_axis.cross(x_axis))
    x_axis = _normalize(y_axis.cross(z_axis))

    return App.Placement(center, App.Rotation(x_axis, y_axis, z_axis, "ZXY"))


def _source_feature(document, name):
    feature = document.getObject(name)
    if feature is None:
        raise RuntimeError(f"Missing source Part::Feature: {name}")
    if not feature.isDerivedFrom("Part::Feature"):
        raise RuntimeError(f"{name} is not a Part::Feature")
    return feature


def _create_mbd_part(document, assembly, source_name):
    source = _source_feature(document, source_name)
    part = document.addObject("MbDFEM::MbDPart", f"{source.Name}_MbDPart")
    shape = source.Shape.copy()
    shape.Placement = App.Placement()
    part.Label = source.Label
    part.Placement = source.Placement
    part.Shape = shape
    return part


def _create_face_marker(document, part, face_name):
    face = part.Shape.getElement(face_name)
    if getattr(face, "ShapeType", None) != "Face":
        raise RuntimeError(f"{part.Name}.{face_name} is not a face")
    if not hasattr(face, "Surface") or face.Surface.TypeId != "Part::GeomCylinder":
        raise RuntimeError(f"{part.Name}.{face_name} is not a cylindrical face")

    marker = document.addObject("MbDFEM::MbDMarker", "MbDMarker")
    marker.Geometry = (part, [face_name])
    marker.Label = f"MbDMarker ({part.Name}.{face_name})"
    marker.Placement = _cylindrical_face_placement(face)
    part.addMarker(marker)
    return marker


def _rotate_part_about_marker(part, marker, angle_degrees):
    pivot = part.Placement.multVec(marker.Placement.Base)
    axis = part.Placement.Rotation.multVec(marker.Placement.Rotation.multVec(App.Vector(0, 0, 1)))
    if axis.Length == 0:
        raise RuntimeError(f"{marker.Name} has no usable rotation axis")

    placement = App.Placement(part.Placement)
    placement.rotate(pivot, axis, angle_degrees, comp=True)
    part.Placement = placement


def create_realistic_pendulum_mbd(document_path=DOCUMENT_PATH):
    """Load RealisticPendulum.FCStd and create the requested MbDFEM objects."""
    _activate_mbd_workbench()

    document = App.openDocument(document_path)
    App.setActiveDocument(document.Name)

    document.openTransaction("Create RealisticPendulum MbD setup")
    try:
        assembly = document.addObject("MbDFEM::MbDAssembly", "MbDAssembly")
        assembly.ensureGravity()
        assembly.ensureSimulationParameters()
        assembly.ensureAnimationParameters()

        ceiling_bracket_part = _create_mbd_part(document, assembly, "CeilingBracket")
        pin_part = _create_mbd_part(document, assembly, "Pin")
        long_pendulum_part = _create_mbd_part(document, assembly, "LongPendulum")

        assembly.addFixedPart(ceiling_bracket_part)
        assembly.addFixedPart(pin_part)
        assembly.addPart(long_pendulum_part)

        pin_marker = _create_face_marker(document, pin_part, "Face1")
        long_pendulum_marker = _create_face_marker(document, long_pendulum_part, "Face4")
        _rotate_part_about_marker(long_pendulum_part, long_pendulum_marker, 90)

        joint = document.addObject("MbDFEM::MbDJoint", "MbDJoint")
        joint.markerI = pin_marker
        joint.markerJ = long_pendulum_marker
        joint.jointType = "Revolute"
        joint.Label = "Revolute MbDJoint"
        assembly.addJoint(joint)

        document.commitTransaction()
    except Exception:
        document.abortTransaction()
        raise

    document.recompute()

    try:
        import FreeCADGui as Gui

        Gui.Selection.clearSelection()
        Gui.Selection.addSelection(joint)
    except Exception:
        pass

    App.Console.PrintMessage(
        "Created MbDAssembly, MbDParts, face markers, and revolute joint in "
        f"{document.Name}.\n"
    )
    return document


if __name__ == "__main__":
    create_realistic_pendulum_mbd()
