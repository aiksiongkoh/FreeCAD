# SPDX-License-Identifier: LGPL-2.1-or-later

"""Create the RealisticPendulum pin MbD setup and import solved ASMT results.

Run in FreeCAD's Python console from the repository directory:
    import runpy
    runpy.run_path("data/examples/RealisticPendulum/CreateRealisticPendulum2PinMbD.py", run_name="__main__")

By default, import the existing MbDFEM/Case001/MbDAssembly.solved.asmt file
under the document's project directory. Export and simulate separately to
generate results before running this script.
Pass solved_asmt_path to create_realistic_pendulum_mbd_asmt() to import an
existing solved ASMT file at another location.
"""

from pathlib import Path

import FreeCAD as App
import MbDFEM  # noqa: F401


DOCUMENT_PATH = str(Path(__file__).resolve().with_name("RealisticPendulum.FCStd"))


def _initialize_gui_console():
    """Keep Gui available to FreeCAD commands after runpy restores __main__."""
    if not App.GuiUp:
        return

    import FreeCADGui as Gui
    from PySide6 import QtCore

    Gui.doCommand("import FreeCADGui as Gui")
    # runpy uses a temporary __main__. Repeat in the console's restored
    # namespace once control returns to the GUI event loop.
    QtCore.QTimer.singleShot(0, lambda: Gui.doCommand("import FreeCADGui as Gui"))


def _activate_mbd_workbench():
    try:
        import FreeCADGui as Gui

        Gui.doCommand("import FreeCADGui as Gui")
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


def _mbd_part_shape(source):
    shape = source.Shape.copy()
    shape.Placement = App.Placement()
    solids = list(getattr(shape, "Solids", []))
    solid_count = len(solids)
    if solid_count == 1:
        return shape

    if not solids:
        raise RuntimeError(
            "MbDPart requires one connected solid.\n"
            f"Found ShapeType={shape.ShapeType}, Solids=0.\n"
            "Fuse the source shape into a single solid before creating the MbDPart."
        )

    fused = solids[0].fuse(solids[1:])
    if len(getattr(fused, "Solids", [])) != 1:
        raise RuntimeError(
            "MbDPart requires one connected solid.\n"
            f"Found ShapeType={shape.ShapeType}, Solids={solid_count}.\n"
            "Fuse the source shape into a single solid before creating the MbDPart."
        )

    App.Console.PrintWarning(
        f"MbDPart {source.Name}: source shape contained {solid_count} solids; "
        "fused them into one solid. The original Part::Feature is unchanged.\n"
    )
    return fused


def _create_mbd_part(document, assembly, source_name):
    source = _source_feature(document, source_name)
    part = document.addObject("MbDFEM::MbDPart", f"{source.Name}_MbDPart")
    part.Label = source.Label
    part.Placement = source.Placement
    part.Shape = _mbd_part_shape(source)
    return part


def _create_edge_marker(document, part, edge_name):
    """Create a part-local marker at a circular edge's center and axis."""
    edge = part.Shape.getElement(edge_name)
    if getattr(edge, "ShapeType", None) != "Edge":
        raise RuntimeError(f"{part.Name}.{edge_name} is not an edge")
    if not hasattr(edge, "Curve") or edge.Curve.TypeId != "Part::GeomCircle":
        raise RuntimeError(f"{part.Name}.{edge_name} is not a circular edge")

    center = edge.Curve.Location
    z_axis = _normalize(edge.Curve.Axis)
    x_axis = edge.valueAt(edge.FirstParameter) - center
    if x_axis.Length == 0:
        x_axis = _orthogonal_vector(z_axis)
    else:
        x_axis = _normalize(x_axis)
    y_axis = _normalize(z_axis.cross(x_axis))
    x_axis = _normalize(y_axis.cross(z_axis))
    placement = App.Placement(center, App.Rotation(x_axis, y_axis, z_axis, "ZXY"))

    marker = document.addObject("MbDFEM::MbDMarker", "MbDMarker")
    marker.Geometry = (part, [edge_name])
    marker.Label = f"MbDMarker ({part.Name}.{edge_name})"
    marker.Placement = placement
    part.addMarker(marker)
    return marker


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
        assembly.addPart(pin_part)
        assembly.addPart(long_pendulum_part)

        bracket_marker = _create_edge_marker(document, ceiling_bracket_part, "Edge30")
        pin_marker = _create_edge_marker(document, pin_part, "Edge5")
        pin_marker2 = _create_face_marker(document, pin_part, "Face1")
        long_pendulum_marker = _create_face_marker(document, long_pendulum_part, "Face8")
        _rotate_part_about_marker(long_pendulum_part, long_pendulum_marker, 90)

        joint = document.addObject("MbDFEM::MbDJoint", "MbDJoint")
        joint.markerI = bracket_marker
        joint.markerJ = pin_marker
        joint.jointType = "Fixed"
        joint.Label = "Fixed MbDJoint"
        assembly.addJoint(joint)


        joint = document.addObject("MbDFEM::MbDJoint", "MbDJoint")
        joint.markerI = pin_marker2
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
        "Created MbDAssembly, MbDParts, edge/face markers, and fixed/revolute joints in "
        f"{document.Name}.\n"
    )
    return document


def import_asmt_results(document, solved_asmt_path=None):
    """Import an existing solved ASMT file, using the default case path if omitted."""
    import FreeCADMbDBackend
    import FreeCADMbDResults

    assembly = document.getObject("MbDAssembly")
    if assembly is None or not assembly.isDerivedFrom("MbDFEM::MbDAssembly"):
        raise RuntimeError("The document has no MbDAssembly to import ASMT results into")

    App.setActiveDocument(document.Name)
    if solved_asmt_path is None:
        solved_asmt_path = FreeCADMbDBackend.default_asmt_path(assembly).with_suffix(".solved.asmt")
    solved_asmt_path = Path(solved_asmt_path)
    if not solved_asmt_path.is_file():
        raise FileNotFoundError(f"Solved ASMT file does not exist: {solved_asmt_path}")

    FreeCADMbDResults.import_results(assembly, solved_asmt_path)
    document.recompute()
    App.Console.PrintMessage(f"Imported ASMT results from {solved_asmt_path}.\n")
    return assembly


def create_realistic_pendulum_mbd_asmt(document_path=DOCUMENT_PATH, solved_asmt_path=None):
    """Create the pin setup and import existing solved ASMT results."""
    document = create_realistic_pendulum_mbd(document_path)
    import_asmt_results(document, solved_asmt_path)
    return document


if __name__ == "__main__":
    try:
        create_realistic_pendulum_mbd_asmt()
    finally:
        _initialize_gui_console()
