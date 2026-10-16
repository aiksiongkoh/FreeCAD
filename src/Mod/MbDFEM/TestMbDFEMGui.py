# SPDX-License-Identifier: LGPL-2.1-or-later

import sys
import tempfile
import unittest
from pathlib import Path

import FreeCAD as App
import MbDFEM  # noqa: F401


def _require_gui():
    if not App.GuiUp:
        raise unittest.SkipTest("GUI tests require FreeCAD GUI mode")

    try:
        import FreeCADGui as Gui
        import MbDFEMGui  # noqa: F401
    except Exception as exc:
        raise unittest.SkipTest("MbDFEMGui not available") from exc

    setup_without_gui = getattr(Gui, "setupWithoutGUI", None)
    if callable(setup_without_gui):
        setup_without_gui()

    return Gui


class MbDFEMGuiViewProviderTest(unittest.TestCase):
    def setUp(self):
        self.Gui = _require_gui()
        self.document = App.newDocument("MbDFEMGuiViewProviderTest")
        self.Gui.setActiveDocument(self.document.Name)

    def tearDown(self):
        if getattr(self, "document", None) is not None:
            self.Gui.Selection.clearSelection()
            if App.getDocument(self.document.Name):
                App.closeDocument(self.document.Name)

    def test_ground_faces_command_converts_selected_faces(self):
        import FreeCADMbDGroundFaces
        import Part

        assembly = self.document.addObject("MbDFEM::MbDAssembly", "Assembly")
        part = self.document.addObject("MbDFEM::MbDPart", "Part")
        part.Shape = Part.makeBox(10, 20, 30)
        part.Label = "Ground support"
        assembly.addPart(part)
        part.ViewObject.ShapeColor = (0.2, 0.4, 0.6)
        part.ViewObject.Transparency = 35
        command = FreeCADMbDGroundFaces.GroundFacesCommand()
        self.Gui.Selection.clearSelection()
        self.assertFalse(command.IsActive())
        self.Gui.Selection.addSelection(part, "Edge1")
        self.assertFalse(command.IsActive())
        self.Gui.Selection.clearSelection()
        self.Gui.Selection.addSelection(part, "Face1")
        self.Gui.Selection.addSelection(part, "Face2")
        self.assertTrue(command.IsActive())
        self.assertIn("MbDFEM_GroundFaces", self.Gui.listCommands())
        self.Gui.runCommand("MbDFEM_GroundFaces")
        self.Gui.updateGui()
        ground = assembly.fixedparts[0]
        self.assertEqual(ground.TypeId, "MbDFEM::MbDGroundPart")
        self.assertEqual(ground.Label, "Ground support")
        self.assertEqual(ground.ViewObject.Transparency, 35)
        self.assertEqual(ground.groundFaces, [(ground, ("Face1", "Face2"))])
        self.assertEqual(self.Gui.Selection.getSelection(), [ground])
        self.assertIsNone(self.document.getObject(ground.Name + "_Face1"))
        self.assertNotIn(ground, ground.OutList)
        self.assertNotIn("Invalid", ground.State)
        # Test the tree-qualified selection path as well as a direct 3D pick.
        self.Gui.Selection.clearSelection()
        self.Gui.Selection.addSelection(assembly, f"{assembly.getFixedPartsFolder().Name}.{ground.Name}.Face3")
        self.assertTrue(command.IsActive())
        command.Activated()
        self.assertEqual(ground.groundFaces, [(ground, ("Face1", "Face2", "Face3"))])

    def test_view_providers_expose_expected_children_and_child_root(self):
        assembly = self.document.addObject("MbDFEM::MbDAssembly", "Assembly")
        part = self.document.addObject("MbDFEM::MbDPart", "Part")
        marker = self.document.addObject("MbDFEM::MbDMarker", "Marker")
        mass_marker = part.ensureMassMarker()
        gravity = assembly.ensureGravity()
        simulation_parameters = assembly.ensureSimulationParameters()
        animation_parameters = assembly.ensureAnimationParameters()

        assembly.addPart(part)
        part.addMarker(marker)
        self.document.recompute()
        self.Gui.updateGui()

        assembly_children = assembly.ViewObject.claimChildren()
        assembly_children_3d = assembly.ViewObject.claimChildren3D()
        part_children = part.ViewObject.claimChildren()
        part_children_3d = part.ViewObject.claimChildren3D()

        self.assertIn(gravity, assembly_children)
        self.assertIn(simulation_parameters, assembly_children)
        self.assertIn(animation_parameters, assembly_children)
        self.assertIn(part, assembly_children_3d)
        self.assertIn(mass_marker, part_children)
        self.assertIn(part.getMarkersFolder(), part_children)
        self.assertLess(part_children.index(mass_marker), part_children.index(part.getMarkersFolder()))
        self.assertNotIn(marker, part_children)
        self.assertEqual(part.getMarkersFolder().Group, [marker])
        self.assertIn(marker, part_children_3d)
        self.assertIn(mass_marker, part_children_3d)
        self.assertIsNotNone(part.ViewObject.getChildRoot())

    def test_marker_always_uses_axis_triad_representation(self):
        assembly = self.document.addObject("MbDFEM::MbDAssembly", "Assembly")
        part = self.document.addObject("MbDFEM::MbDPart", "Part")
        marker = self.document.addObject("MbDFEM::MbDMarker", "Marker")

        assembly.addPart(part)
        part.addMarker(marker)
        self.document.recompute()
        self.Gui.updateGui()

        self.assertNotIn("AxisTriad", assembly.ViewObject.PropertiesList)
        self.assertNotIn("AxisTriad", part.ViewObject.PropertiesList)
        self.assertNotIn("AxisTriad", marker.ViewObject.PropertiesList)
        self.assertTrue(marker.ViewObject.Visibility)

    def test_marker_command_uses_part_local_face_placement(self):
        import InitGui
        import Part

        class SelectionCandidate:
            pass

        part = self.document.addObject("MbDFEM::MbDPart", "Part")
        part.Shape = Part.makeCylinder(2, 10)
        part.Placement = App.Placement(
            App.Vector(10, 20, 30),
            App.Rotation(App.Vector(0, 0, 1), 90),
        )
        self.document.recompute()

        face_index, face = next(
            (index, face)
            for index, face in enumerate(part.Shape.Faces, start=1)
            if getattr(face.Surface, "TypeId", None) == "Part::GeomCylinder"
        )
        transformed_face = face.copy().transformShape(part.getGlobalPlacement().toMatrix(), True)
        selected = SelectionCandidate()
        selected.Object = part
        selected.SubElementNames = [f"Face{face_index}"]
        selected.SubObjects = [transformed_face]

        command = InitGui.CreateMbDMarkerCommand()
        expected_local = command._reference_placement(face)
        selected_part, sub_name, selected_element = command._selection_from_candidate(selected)
        actual_local = command._reference_placement(selected_element)

        self.assertIs(selected_part, part)
        self.assertEqual(sub_name, f"Face{face_index}")
        self.assertLess((actual_local.Base - expected_local.Base).Length, 1e-7)
        for axis in (App.Vector(1, 0, 0), App.Vector(0, 1, 0), App.Vector(0, 0, 1)):
            actual_axis = actual_local.Rotation.multVec(axis)
            expected_axis = expected_local.Rotation.multVec(axis)
            self.assertLess((actual_axis - expected_axis).Length, 1e-7)

    def test_assembly_drop_normalizes_part_feature_shape_placement(self):
        import Part

        assembly = self.document.addObject("MbDFEM::MbDAssembly", "Assembly")
        source = self.document.addObject("Part::Feature", "Source")
        source.Shape = Part.makeCylinder(8, 20)
        source.Placement = App.Placement(
            App.Vector(10, 0, 0),
            App.Rotation(App.Vector(0, 1, 0), 40),
        )
        self.document.recompute()
        self.assertGreater(abs(source.Shape.Placement.Rotation.Angle), 1e-9)

        assembly.ViewObject.dropObject(source)
        self.document.recompute()

        part = next(
            obj for obj in self.document.Objects if obj.TypeId == "MbDFEM::MbDPart"
        )
        self.assertTrue(part.Placement.isSame(source.Placement, 1e-9))
        self.assertLess(part.Shape.Placement.Base.Length, 1e-9)
        self.assertLess(abs(part.Shape.Placement.Rotation.Angle), 1e-9)
        marker = part.getMassMarker()
        self.assertIsNotNone(marker)
        self.assertLess((marker.Placement.Base - App.Vector(0, 0, 10)).Length, 1e-9)

    def test_solve_command_resolves_active_assembly_without_module_global_helper(self):
        import InitGui

        assembly = self.document.addObject("MbDFEM::MbDAssembly", "Assembly")
        self.document.recompute()
        self.Gui.Selection.clearSelection()
        self.Gui.Selection.addSelection(assembly)
        command = InitGui.SolveMbDAssemblyCommand()

        self.assertIs(command.activeAssembly(), assembly)
        self.assertNotIn("_active_mbdfem_assembly", InitGui.SolveMbDAssemblyCommand.Activated.__code__.co_names)
        self.assertNotIn("_active_mbd_assembly", InitGui.SolveMbDAssemblyCommand.Activated.__code__.co_names)

    def test_fem_assembly_command_links_top_level_mbd_assembly(self):
        import InitGui
        import Part

        assembly = self.document.addObject("MbDFEM::MbDAssembly", "Assembly")
        subassembly = self.document.addObject("MbDFEM::MbDAssembly", "Subassembly")
        fixed_part = self.document.addObject("MbDFEM::MbDPart", "FixedPart")
        moving_part = self.document.addObject("MbDFEM::MbDPart", "MovingPart")
        joint = self.document.addObject("MbDFEM::MbDJoint", "Joint")
        assembly.Placement = App.Placement(
            App.Vector(10, 20, 30),
            App.Rotation(App.Vector(0, 1, 0), 40),
        )
        fixed_part.Shape = Part.makeBox(1, 2, 3)
        fixed_part.Placement = App.Placement(
            App.Vector(100, 0, 0),
            App.Rotation(App.Vector(0, 0, 1), 30),
        )
        fixed_marker = fixed_part.ensureMassMarker()
        moving_part.Shape = Part.makeBox(4, 5, 6)
        moving_part.Placement = App.Placement(
            App.Vector(0, 200, 0),
            App.Rotation(App.Vector(1, 0, 0), 20),
        )
        moving_marker = moving_part.ensureMassMarker()
        joint.markerI = fixed_marker
        joint.markerJ = moving_marker
        assembly.addAssembly(subassembly)
        assembly.addFixedPart(fixed_part)
        assembly.addPart(moving_part)
        assembly.addJoint(joint)
        self.document.recompute()
        self.Gui.Selection.clearSelection()
        self.Gui.Selection.addSelection(subassembly)
        self.Gui.getDocument(self.document).ActiveView.setActiveObject("part", assembly)

        command = InitGui.CreateFEMAssemblyCommand()
        command.Activated()

        fem_assembly = next(
            obj for obj in self.document.Objects if obj.TypeId == "MbDFEM::FEMAssembly"
        )
        self.assertIs(fem_assembly.mbdItem, assembly)
        self.assertTrue(fem_assembly.Placement.isSame(assembly.Placement, 1e-7))
        self.assertEqual(fem_assembly.ViewObject.TypeId, "MbDFEMGui::ViewProviderFEMAssembly")
        self.assertTrue(fem_assembly.ViewObject.isDerivedFrom("Gui::ViewProviderGeometryObject"))
        self.assertTrue(fem_assembly.ViewObject.DLOADAutoScale)
        self.assertEqual(fem_assembly.ViewObject.DLOADScale, 1.0)
        self.assertTrue(fem_assembly.Visibility)
        self.assertTrue(fem_assembly.ViewObject.Visibility)
        self.assertTrue(fem_assembly.ViewObject.isShow())
        self.assertIsNotNone(fem_assembly.Origin)
        self.assertFalse(fem_assembly.Origin.ViewObject.ShowInTree)
        fem_assembly.Origin.ViewObject.ShowInTree = True
        fem_children = fem_assembly.ViewObject.claimChildren()
        self.assertEqual(
            fem_children[:2],
            [fem_assembly.femParameters, fem_assembly.animationParameters],
        )
        fem_folders = fem_children[2:]
        self.assertFalse(fem_assembly.Origin.ViewObject.ShowInTree)
        fem_assembly.Origin.ViewObject.ShowInTree = True
        self.assertEqual(
            fem_assembly.ViewObject.claimChildren3D(),
            [*fem_assembly.parts, *fem_assembly.joints],
        )
        self.assertFalse(fem_assembly.Origin.ViewObject.ShowInTree)
        self.assertEqual(
            [folder.Label for folder in fem_folders],
            ["Parts", "Joints", "Motions", "Actions"],
        )
        self.assertTrue(all(folder.TypeId.startswith("MbDFEM::FEM") for folder in fem_folders))
        self.assertTrue(all(assembly not in folder.InList for folder in fem_folders))
        self.assertEqual(fem_assembly.Group[2:6], fem_folders)
        fem_parts = fem_folders[0].Group
        self.assertEqual([fem_part.TypeId for fem_part in fem_parts], ["MbDFEM::FEMPart"] * 2)
        self.assertEqual([fem_part.mbdItem for fem_part in fem_parts], [fixed_part, moving_part])
        for fem_part, mbd_part in zip(fem_parts, [fixed_part, moving_part]):
            self.assertTrue(fem_part.Placement.isSame(mbd_part.Placement, 1e-7))
            self.assertEqual(len(fem_part.Shape.Solids), len(mbd_part.Shape.Solids))
            fem_box = fem_part.Shape.BoundBox
            mbd_box = mbd_part.Shape.BoundBox
            for fem_value, mbd_value in zip(
                (fem_box.XMin, fem_box.XMax, fem_box.YMin, fem_box.YMax, fem_box.ZMin, fem_box.ZMax),
                (mbd_box.XMin, mbd_box.XMax, mbd_box.YMin, mbd_box.YMax, mbd_box.ZMin, mbd_box.ZMax),
            ):
                self.assertAlmostEqual(fem_value, mbd_value)
            import FreeCADMbDFEMEmbedded

            material = FreeCADMbDFEMEmbedded._fem_part_material_object(fem_part, create=False)
            self.assertIsNotNone(material)
            self.assertFalse(hasattr(fem_part, "material"))
            self.assertEqual(material.TypeId, "App::MaterialObjectPython")
            self.assertEqual(material.Category, "Solid")
            self.assertEqual(material.Material, mbd_part.getMassMarker().material)
            self.assertEqual(material.References, [])
            self.assertIn(material, fem_part.Group)
            self.assertNotIn(material, fem_assembly.Group)
            self.assertIsNotNone(fem_part.mesh)
            self.assertIn(fem_part.mesh, fem_part.Group)
            self.assertIsNotNone(fem_part.solver)
            self.assertEqual(fem_part.solver.TypeId, "Fem::FemSolverObjectPython")
            self.assertTrue(fem_part.solver.isDerivedFrom("Fem::FemSolverObjectPython"))
            self.assertIn(fem_part.solver, fem_part.Group)
            self.assertTrue(fem_part.solver.ViewObject.doubleClicked())

            dialog = self.Gui.Control.activeDialog()
            self.assertIsInstance(dialog, FreeCADMbDFEMEmbedded.FEMPartSolverTaskPanel)
            self.assertTrue(dialog.reject())
            self.assertIsNone(self.Gui.Control.activeDialog())
            from femtaskpanels import task_solver_ccxtools

            stock_dialog = task_solver_ccxtools._TaskPanel(fem_part.solver)
            self.Gui.Control.showDialog(stock_dialog)
            self.assertTrue(stock_dialog.reject())
            self.assertIsNone(self.Gui.Control.activeDialog())
            from femviewprovider import view_material_common

            view_material_common.VPMaterialCommon(material.ViewObject)
            material.References = [(fem_part, ("Solid1",))]
            InitGui.refresh_embedded_fem_part_view_providers(self.document)
            self.assertIsInstance(
                material.ViewObject.Proxy,
                InitGui.EmbeddedFEMPartMaterialViewProvider,
            )
            self.assertEqual(material.References, [])
            self.assertTrue(material.ViewObject.doubleClicked())
            dialog = self.Gui.Control.activeDialog()
            try:
                self.assertIsInstance(dialog, InitGui.EmbeddedFEMPartMaterialTaskPanel)
                self.assertEqual(dialog.form, [dialog.parameterWidget])
                self.assertFalse(hasattr(dialog.parameterWidget, "chbu_allow_edit"))
                self.assertFalse(hasattr(dialog.parameterWidget, "wgt_material_tree"))
                from PySide import QtWidgets

                for field in dialog.parameterWidget.findChildren(QtWidgets.QLineEdit):
                    self.assertTrue(field.isReadOnly())
            finally:
                if dialog is not None:
                    self.Gui.Control.closeDialog()
            fem_part.Origin.ViewObject.ShowInTree = True
            self.assertEqual(
                fem_part.ViewObject.claimChildren(),
                [material, fem_part.mesh, fem_part.solver, *fem_part.joints],
            )
            self.assertFalse(fem_part.Origin.ViewObject.ShowInTree)
            fem_part.Origin.ViewObject.ShowInTree = True
            self.assertEqual(fem_part.ViewObject.claimChildren3D(), [fem_part.mesh])
            self.assertFalse(fem_part.Origin.ViewObject.ShowInTree)
        self.assertEqual(fem_assembly.parts, fem_parts)
        first_fem_part = fem_parts[0]
        self.assertEqual(first_fem_part.ViewObject.claimChildren3D(), [first_fem_part.mesh])
        fem_assembly.Visibility = False
        self.assertEqual(fem_assembly.ViewObject.claimChildren3D(), [*fem_assembly.parts, *fem_assembly.joints])
        self.assertTrue(first_fem_part.ViewObject.canAddToSceneGraph())
        self.assertEqual(first_fem_part.isElementVisible(first_fem_part.mesh.Name), 0)
        self.assertEqual(first_fem_part.ViewObject.claimChildren3D(), [first_fem_part.mesh])
        fem_assembly.Visibility = True
        self.assertEqual(first_fem_part.isElementVisible(first_fem_part.mesh.Name), 1)
        self.assertEqual(first_fem_part.ViewObject.claimChildren3D(), [first_fem_part.mesh])
        parts_folder = fem_assembly.getPartsFolder()
        self.assertEqual(parts_folder.setElementVisible(first_fem_part.Name, False), 0)
        self.assertFalse(first_fem_part.Visibility)
        self.assertEqual(first_fem_part.ViewObject.claimChildren3D(), [first_fem_part.mesh])
        self.assertEqual(parts_folder.isElementVisible(first_fem_part.Name), 0)
        self.assertEqual(parts_folder.setElementVisible(first_fem_part.Name, True), 1)
        self.assertTrue(first_fem_part.Visibility)
        self.assertEqual(first_fem_part.ViewObject.claimChildren3D(), [first_fem_part.mesh])
        self.Gui.Selection.clearSelection()
        self.Gui.Selection.addSelection(
            self.document.Name,
            fem_assembly.Name,
            f"{first_fem_part.Name}.",
        )
        self.Gui.runCommand("Std_ToggleVisibility", 0)
        self.assertFalse(first_fem_part.Visibility)
        self.assertTrue(first_fem_part.ViewObject.canAddToSceneGraph())
        self.assertEqual(first_fem_part.ViewObject.claimChildren3D(), [first_fem_part.mesh])
        self.Gui.runCommand("Std_ToggleVisibility", 0)
        self.assertTrue(first_fem_part.Visibility)
        self.assertTrue(first_fem_part.ViewObject.canAddToSceneGraph())
        self.assertEqual(first_fem_part.ViewObject.claimChildren3D(), [first_fem_part.mesh])
        assembly.Placement = App.Placement(
            App.Vector(300, 400, 500),
            App.Rotation(App.Vector(1, 0, 0), 55),
        )
        self.document.recompute()
        self.assertTrue(fem_assembly.Placement.isSame(assembly.Placement, 1e-7))
        moving_part.Placement = App.Placement(
            App.Vector(700, 800, 900),
            App.Rotation(App.Vector(0, 0, 1), 70),
        )
        self.document.recompute()
        self.assertTrue(fem_parts[1].Placement.isSame(moving_part.Placement, 1e-7))
        fem_joints = fem_folders[1].Group
        self.assertEqual([fem_joint.TypeId for fem_joint in fem_joints], ["MbDFEM::FEMJoint"])
        self.assertEqual([fem_joint.mbdItem for fem_joint in fem_joints], [joint])
        self.assertEqual(fem_assembly.joints, fem_joints)
        for fem_part in fem_parts:
            self.assertEqual(fem_part.joints, fem_joints)
        self.assertEqual(fem_assembly.ViewObject.claimChildren3D(), [*fem_parts, *fem_joints])
        for fem_item in [*fem_parts, *fem_joints]:
            self.assertIn(fem_item, fem_assembly.Group)
        self.assertNotIn(assembly, fem_assembly.InList)
        self.assertEqual(fem_assembly.Label, "FEMAssembly")
        self.assertEqual(self.Gui.Selection.getSelection(), [fem_assembly])

    def test_fem_part_material_panel_formats_material_quantities_for_display(self):
        import FreeCADMbDFEMEmbedded

        material = {
            "Name": "CalculiX-Steel",
            "Density": "7.9e-06 kg/mm^3",
            "YoungsModulus": "2.1e+08 kg/(mm*s^2)",
            "PoissonRatio": "0.3",
            "ThermalConductivity": "43000 mm*kg/(s^3*K)",
            "ThermalExpansionCoefficient": "1.2e-05 1/K",
            "SpecificHeat": "5.9e+08 mm^2/(s^2*K)",
        }

        expected = {
            "Density": ("kg/m^3", 7900.0),
            "YoungsModulus": ("MPa", 210000.0),
            "ThermalConductivity": ("W/m/K", 43.0),
            "ThermalExpansionCoefficient": ("1/K", 1.2e-05),
            "SpecificHeat": ("J/kg/K", 590.0),
        }

        for key, (unit, expected_value) in expected.items():
            display = FreeCADMbDFEMEmbedded._material_value(material, key)
            self.assertIn(unit, display)
            self.assertAlmostEqual(
                App.Units.Quantity(display).getValueAs(unit).Value,
                expected_value,
            )

        self.assertEqual(
            FreeCADMbDFEMEmbedded._material_value(material, "PoissonRatio"),
            "0.3",
        )

    def test_fem_part_create_mesh_command_uses_fem_part_shape(self):
        import InitGui
        import Part

        mbd_part = self.document.addObject("MbDFEM::MbDPart", "MbDPart")
        mbd_part.Shape = Part.makeBox(10, 20, 30)
        mbd_part.Placement = App.Placement(
            App.Vector(10, 20, 30),
            App.Rotation(App.Vector(0, 1, 0), 40),
        )
        fem_part = self.document.addObject("MbDFEM::FEMPart", "FEMPart")
        fem_part.mbdItem = mbd_part
        fem_part.Shape = Part.makeBox(1, 2, 3)
        fem_part.Placement = App.Placement(
            App.Vector(40, 50, 60),
            App.Rotation(App.Vector(1, 0, 0), 15),
        )
        self.document.recompute()
        self.assertEqual(fem_part.ViewObject.TypeId, "MbDFEMGui::ViewProviderFEMPart")
        self.assertTrue(fem_part.ViewObject.isDerivedFrom("Gui::ViewProviderGeometryObject"))
        self.assertIsNotNone(fem_part.Origin)
        self.assertFalse(fem_part.Origin.ViewObject.ShowInTree)
        fem_part.Origin.ViewObject.ShowInTree = True
        self.assertEqual(fem_part.ViewObject.claimChildren(), [])
        self.assertFalse(fem_part.Origin.ViewObject.ShowInTree)
        self.Gui.Selection.clearSelection()
        self.Gui.Selection.addSelection(fem_part)

        command = InitGui.CreateFEMPartMeshCommand()
        self.assertTrue(command.IsActive())
        self.assertNotIn(
            "_selected_fem_part",
            InitGui.CreateFEMPartMeshCommand.Activated.__code__.co_names,
        )
        self.assertNotIn(
            "_create_fem_part_mesh",
            InitGui.CreateFEMPartMeshCommand.createMesh.__code__.co_names,
        )
        self.assertNotIn(
            "_make_mesh_shape_proxy",
            InitGui.CreateFEMPartMeshCommand._make_mesh_shape_proxy.__code__.co_names,
        )
        self.assertNotIn(
            "_remove_from_owner_groups",
            InitGui.CreateFEMPartMeshCommand._remove_from_owner_groups.__code__.co_names,
        )
        command.Activated()

        self.assertIsNotNone(fem_part.mesh)
        self.assertEqual(fem_part.mesh.TypeId, "Fem::FemMeshShapeBaseObjectPython")
        self.assertIsNot(fem_part.mesh.Shape, mbd_part)
        self.assertEqual(fem_part.mesh.Shape.TypeId, "Part::Feature")
        self.assertEqual(fem_part.mesh.Shape.Label, "Mesh Shape (FEMPart)")
        self.assertEqual(
            len(fem_part.mesh.Shape.Shape.Solids),
            len(fem_part.Shape.Solids),
        )
        self.assertTrue(fem_part.mesh.Shape.Placement.isSame(App.Placement(), 1e-7))
        self.assertTrue(fem_part.mesh.Placement.isSame(App.Placement(), 1e-7))
        self.assertTrue(fem_part.mesh.getGlobalPlacement().isSame(fem_part.Placement, 1e-7))
        self.assertEqual(fem_part.ViewObject.claimChildren3D(), [fem_part.mesh])
        cload_faces = self.document.addObject("Fem::FemMeshObject", fem_part.Name + "_CLOADFaces")
        dload_elements = self.document.addObject("Fem::FemMeshObject", fem_part.Name + "_DLOADElements")
        fem_part.addObject(cload_faces)
        fem_part.addObject(dload_elements)
        self.assertEqual(
            fem_part.ViewObject.claimChildren()[:3],
            [fem_part.mesh, cload_faces, dload_elements],
        )
        self.assertEqual(
            fem_part.ViewObject.claimChildren3D(),
            [fem_part.mesh, cload_faces, dload_elements],
        )
        fem_part.removeObject(cload_faces)
        fem_part.removeObject(dload_elements)
        fem_part.Visibility = False
        self.assertTrue(fem_part.ViewObject.canAddToSceneGraph())
        self.assertEqual(fem_part.isElementVisible(fem_part.mesh.Name), 0)
        self.assertEqual(fem_part.ViewObject.claimChildren3D(), [fem_part.mesh])
        fem_part.Visibility = True
        self.assertTrue(fem_part.ViewObject.canAddToSceneGraph())
        self.assertEqual(fem_part.isElementVisible(fem_part.mesh.Name), 1)
        self.assertEqual(fem_part.ViewObject.claimChildren3D(), [fem_part.mesh])
        fem_part.setElementVisible(fem_part.mesh.Name, False)
        self.assertEqual(fem_part.isElementVisible(fem_part.mesh.Name), 0)
        self.assertEqual(fem_part.ViewObject.claimChildren3D(), [])
        fem_part.setElementVisible(fem_part.mesh.Name, True)
        self.assertEqual(fem_part.isElementVisible(fem_part.mesh.Name), 1)
        self.assertEqual(fem_part.ViewObject.claimChildren3D(), [fem_part.mesh])
        self.assertFalse(fem_part.mesh.Shape.ViewObject.Visibility)
        self.assertFalse(fem_part.mesh.Shape.ViewObject.ShowInTree)
        self.assertEqual(fem_part.mesh.ElementOrder, "2nd")
        self.assertEqual(fem_part.mesh.SecondOrderLinear, False)
        self.assertIn(fem_part.mesh, fem_part.Group)

        import ObjectsFem

        stale_shape_proxy = self.document.addObject("Part::Feature", fem_part.Name + "_MeshShape")
        stale_shape_proxy.Label = f"Mesh Shape ({fem_part.Label})"
        stale_shape_proxy.Shape = fem_part.Shape.copy()
        stale_mesh = ObjectsFem.makeMeshGmsh(self.document, fem_part.Name + "_Mesh")
        stale_mesh.Label = f"Mesh ({fem_part.Label})"
        stale_mesh.Shape = stale_shape_proxy
        self.assertNotIn(stale_mesh, fem_part.Group)
        old_mesh = fem_part.mesh
        old_mesh_name = old_mesh.Name
        old_shape_proxy_name = old_mesh.Shape.Name
        stale_mesh_name = stale_mesh.Name
        stale_shape_proxy_name = stale_shape_proxy.Name
        self.Gui.Selection.clearSelection()
        self.Gui.Selection.addSelection(fem_part)
        command.Activated()
        self.assertIsNot(fem_part.mesh, old_mesh)
        self.assertIsNone(self.document.getObject(old_mesh_name))
        self.assertIsNone(self.document.getObject(old_shape_proxy_name))
        self.assertIsNone(self.document.getObject(stale_mesh_name))
        self.assertIsNone(self.document.getObject(stale_shape_proxy_name))
        self.assertEqual(
            [
                child
                for child in fem_part.Group
                if child.TypeId == "Fem::FemMeshShapeBaseObjectPython"
            ],
            [fem_part.mesh],
        )

        import FreeCADMbDFEMEmbedded

        ccx_results_mesh = ObjectsFem.makeMeshResult(self.document, "CCX_Results_Mesh")
        ccx_results = ObjectsFem.makeResultMechanical(self.document, "CCX_Results")
        pipeline_results = self.document.addObject("Fem::FemPostPipeline", "Pipeline_CCX_Results")
        ccx_results.Mesh = ccx_results_mesh
        fem_part.results = [ccx_results]
        fem_part.visual = pipeline_results
        fem_part.addObject(ccx_results)
        fem_part.addObject(pipeline_results)
        self.assertNotIn(ccx_results_mesh, fem_part.Group)
        FreeCADMbDFEMEmbedded.refresh_view_providers(self.document)
        self.assertFalse(ccx_results_mesh.ViewObject.Visibility)
        self.assertFalse(ccx_results_mesh.ViewObject.ShowInTree)
        results_folder = fem_part.getResultsFolder()
        self.assertIsNotNone(results_folder)
        self.assertIn(results_folder, fem_part.Group)
        self.assertIn(ccx_results, results_folder.Group)
        self.assertIn(pipeline_results, fem_part.Group)
        self.assertFalse(pipeline_results.ViewObject.ShowInTree)
        fem_part.Origin.ViewObject.ShowInTree = True
        self.assertEqual(
            fem_part.ViewObject.claimChildren(),
            [fem_part.mesh, results_folder],
        )
        self.assertFalse(fem_part.Origin.ViewObject.ShowInTree)
        self.assertEqual(results_folder.ViewObject.claimChildren(), [ccx_results])
        self.assertIs(fem_part.getSubObject(f"{fem_part.mesh.Name}."), fem_part.mesh)
        self.assertIs(fem_part.getSubObject(f"{results_folder.Name}."), results_folder)
        self.assertIs(fem_part.getSubObject(f"{ccx_results.Name}."), ccx_results)
        self.assertIs(fem_part.getSubObject(f"{pipeline_results.Name}."), pipeline_results)
        self.assertEqual(ccx_results.ViewObject.Proxy.claimChildren(), [ccx_results_mesh])
        fem_part.Origin.ViewObject.ShowInTree = True
        self.assertEqual(fem_part.ViewObject.claimChildren3D(), [fem_part.mesh, pipeline_results])
        self.assertFalse(fem_part.Origin.ViewObject.ShowInTree)
        self.assertIn(fem_part.mesh.Shape, fem_part.mesh.ViewObject.Proxy.claimChildren())
        self.assertEqual(self.Gui.Selection.getSelection(), [fem_part.mesh])

    def test_results_folder_double_click_opens_state_solver_panel(self):
        import FreeCADMbDFEMResultsPanel

        assembly = self.document.addObject("MbDFEM::MbDAssembly", "Assembly")
        part = self.document.addObject("MbDFEM::MbDPart", "Part")
        fem_part = self.document.addObject("MbDFEM::FEMPart", "FEMPart")
        assembly.addPart(part)
        fem_part.mbdItem = part
        mesh = self.document.addObject("Fem::FemMeshObjectPython", "Mesh")
        pipeline = self.document.addObject("Fem::FemPostPipeline", "Pipeline_CCX_Results")
        fem_part.mesh = mesh
        fem_part.visual = pipeline
        assembly.times = [0.0, 0.25]
        part.xs = [0.0, 1000.0]
        part.ys = [0.0, 2000.0]
        part.zs = [0.0, 3000.0]

        folder = fem_part.ensureResultsFolder()
        self.document.recompute()
        self.Gui.updateGui()

        self.assertTrue(folder.ViewObject.doubleClicked())
        dialog = self.Gui.Control.activeDialog()

        try:
            self.assertIsInstance(dialog, FreeCADMbDFEMResultsPanel.FEMResultsTaskPanel)
            self.assertIs(dialog.results_folder, folder)
            self.assertIs(dialog.fem_part, fem_part)
            dialog.state_spin.setValue(1)
            self.assertEqual(part.Placement.Base, App.Vector(1000.0, 2000.0, 3000.0))
            self.assertEqual(fem_part.Placement.Base, App.Vector(1000.0, 2000.0, 3000.0))
            self.assertEqual(fem_part.ViewObject.claimChildren3D(), [mesh, pipeline])
            self.assertTrue(mesh.Placement.isSame(App.Placement(), 1e-7))
            self.assertTrue(mesh.getGlobalPlacement().isSame(fem_part.Placement, 1e-7))
            self.assertTrue(pipeline.Placement.isSame(App.Placement(), 1e-7))
            self.assertTrue(pipeline.getGlobalPlacement().isSame(fem_part.Placement, 1e-7))
        finally:
            if self.Gui.Control.activeDialog() is not None:
                self.Gui.Control.closeDialog()

    def test_results_panel_assigns_calculix_results_by_state_index(self):
        import FreeCADMbDFEMResultsPanel

        fem_part = self.document.addObject("MbDFEM::FEMPart", "FEMPart")
        result_0 = self.document.addObject("Fem::FemResultObjectPython", "CCX_Results_0")
        result_1 = self.document.addObject("Fem::FemResultObjectPython", "CCX_Results_1")
        replacement = self.document.addObject("Fem::FemResultObjectPython", "CCX_Results_Replacement")

        FreeCADMbDFEMResultsPanel._assign_result_for_state(fem_part, 0, result_0)
        FreeCADMbDFEMResultsPanel._assign_result_for_state(fem_part, 1, result_1)
        FreeCADMbDFEMResultsPanel._assign_result_for_state(
            fem_part,
            2,
            result_1,
        )
        FreeCADMbDFEMResultsPanel._assign_result_for_state(
            fem_part,
            0,
            replacement,
        )

        self.assertEqual(fem_part.results, [replacement, result_1])
        self.assertEqual(fem_part.getResultsFolder().Group, [replacement, result_1])
        self.assertEqual(replacement.MbDFEMStateIndex, 0)
        self.assertEqual(result_1.MbDFEMStateIndex, 2)

    def test_results_panel_solve_state_applies_mbd_state_and_assigns_result(self):
        import FreeCADMbDFEMResultsPanel

        assembly = self.document.addObject("MbDFEM::MbDAssembly", "Assembly")
        part = self.document.addObject("MbDFEM::MbDPart", "Part")
        fem_part = self.document.addObject("MbDFEM::FEMPart", "FEMPart")
        solver = self.document.addObject("Fem::FemSolverObjectPython", "Calculix")
        result = self.document.addObject("Fem::FemResultObjectPython", "CCX_Results")
        assembly.addPart(part)
        fem_part.mbdItem = part
        fem_part.solver = solver
        assembly.times = [0.0, 0.25]
        part.xs = [0.0, 1000.0]
        part.ys = [0.0, 2000.0]
        part.zs = [0.0, 3000.0]

        def runner(runner_fem_part, state_index):
            self.assertIs(runner_fem_part, fem_part)
            self.assertEqual(state_index, 1)
            return result

        assigned = FreeCADMbDFEMResultsPanel.solve_fem_part_state(fem_part, 1, runner=runner)

        self.assertIs(assigned, result)
        self.assertEqual(fem_part.results, [result])
        self.assertEqual(fem_part.getResultsFolder().Group, [result])
        self.assertEqual(result.MbDFEMStateIndex, 1)
        self.assertAlmostEqual(result.MbDFEMStateTime, 0.25)
        self.assertEqual(part.Placement.Base, App.Vector(1000.0, 2000.0, 3000.0))
        self.assertEqual(fem_part.Placement.Base, App.Vector(1000.0, 2000.0, 3000.0))

    def test_results_panel_solve_state_uses_frame_calculix_directory(self):
        import FreeCADMbDBackend
        import FreeCADMbDFEMEmbedded
        import FreeCADMbDFEMResultsPanel

        with tempfile.TemporaryDirectory() as directory:
            self.document.saveAs(str(Path(directory) / "MyAssembly.FCStd"))

            assembly = self.document.addObject("MbDFEM::MbDAssembly", "Assembly")
            part = self.document.addObject("MbDFEM::MbDPart", "MbDPart001")
            fem_part = self.document.addObject("MbDFEM::FEMPart", "FEMPart")
            solver = self.document.addObject("Fem::FemSolverObjectPython", "Calculix")
            assembly.addPart(part)
            fem_part.mbdItem = part
            fem_part.solver = solver
            assembly.times = [0.0, 0.25]
            part.xs = [0.0, 1000.0]
            part.ys = [0.0, 2000.0]
            part.zs = [0.0, 3000.0]

            calls = {}

            class FakeCcxTools:
                def __init__(self, tool_fem_part, tool_solver):
                    self.fem_part = tool_fem_part
                    self.solver = tool_solver

                def setup_working_dir(self, working_dir):
                    calls["working_dir"] = working_dir

                def set_base_name(self, base_name):
                    calls["base_name"] = base_name

                def setup_ccx(self):
                    calls["setup_ccx"] = True

                def run(self):
                    result = self.fem_part.Document.addObject(
                        "Fem::FemResultObjectPython",
                        "CCX_Results",
                    )
                    self.fem_part.results = [result]
                    return True

            original_tools = FreeCADMbDFEMEmbedded.FEMPartCcxTools
            try:
                FreeCADMbDFEMEmbedded.FEMPartCcxTools = FakeCcxTools
                FreeCADMbDFEMResultsPanel.solve_fem_part_state(fem_part, 1)
            finally:
                FreeCADMbDFEMEmbedded.FEMPartCcxTools = original_tools

            self.assertEqual(
                calls["working_dir"],
                str(
                    Path(directory)
                    / "MyAssembly"
                    / "MbDFEM"
                    / "Case001"
                    / "MbDPart001"
                    / "Frame000001"
                ),
            )
            self.assertEqual(calls["base_name"], FreeCADMbDBackend.CALCULIX_BASE_NAME)

    def test_results_panel_import_state_reuses_frame_calculix_result(self):
        import FreeCADMbDBackend
        import FreeCADMbDFEMEmbedded
        import FreeCADMbDFEMResultsPanel

        with tempfile.TemporaryDirectory() as directory:
            self.document.saveAs(str(Path(directory) / "MyAssembly.FCStd"))

            assembly = self.document.addObject("MbDFEM::MbDAssembly", "Assembly")
            part = self.document.addObject("MbDFEM::MbDPart", "MbDPart001")
            fem_part = self.document.addObject("MbDFEM::FEMPart", "FEMPart")
            solver = self.document.addObject("Fem::FemSolverObjectPython", "Calculix")
            assembly.addPart(part)
            fem_part.mbdItem = part
            fem_part.solver = solver
            assembly.times = [0.0, 0.25]
            part.xs = [0.0, 1000.0]
            part.ys = [0.0, 2000.0]
            part.zs = [0.0, 3000.0]

            working_dir = (
                Path(directory)
                / "MyAssembly"
                / "MbDFEM"
                / "Case001"
                / "MbDPart001"
                / "Frame000001"
            )
            working_dir.mkdir(parents=True)
            (working_dir / "calculix.inp").write_text("", encoding="utf-8")
            (working_dir / "calculix.frd").write_text("", encoding="utf-8")
            calls = {}

            class FakeCcxTools:
                def __init__(self, tool_fem_part, tool_solver):
                    self.fem_part = tool_fem_part
                    self.solver = tool_solver
                    self.inp_file_name = ""

                def setup_working_dir(self, working_dir):
                    calls["working_dir"] = working_dir

                def set_base_name(self, base_name):
                    calls["base_name"] = base_name

                def setup_ccx(self):
                    calls["setup_ccx"] = True

                def load_results_ccxfrd(self):
                    calls["inp_file_name"] = self.inp_file_name
                    result = self.fem_part.Document.addObject(
                        "Fem::FemResultObjectPython",
                        "CCX_ImportedResults",
                    )
                    self.fem_part.results = [result]

            original_tools = FreeCADMbDFEMEmbedded.FEMPartCcxTools
            try:
                FreeCADMbDFEMEmbedded.FEMPartCcxTools = FakeCcxTools
                result = FreeCADMbDFEMResultsPanel.import_fem_part_state(fem_part, 1)
            finally:
                FreeCADMbDFEMEmbedded.FEMPartCcxTools = original_tools

            self.assertEqual(calls["working_dir"], str(working_dir))
            self.assertEqual(calls["base_name"], FreeCADMbDBackend.CALCULIX_BASE_NAME)
            self.assertEqual(calls["inp_file_name"], str(working_dir / "calculix.inp"))
            self.assertNotIn("setup_ccx", calls)
            self.assertEqual(result.MbDFEMStateIndex, 1)
            self.assertAlmostEqual(result.MbDFEMStateTime, 0.25)
            self.assertEqual(fem_part.results, [result])

    def test_calculix_task_panel_restores_values_after_close(self):
        import FreeCADMbDBackend
        import FreeCADMbDFEMEmbedded

        with tempfile.TemporaryDirectory() as directory:
            self.document.saveAs(str(Path(directory) / "PanelState.FCStd"))

            assembly = self.document.addObject("MbDFEM::MbDAssembly", "Assembly")
            part = self.document.addObject("MbDFEM::MbDPart", "MbDPart001")
            fem_part = self.document.addObject("MbDFEM::FEMPart", "FEMPart")
            solver = self.document.addObject("Fem::FemSolverObjectPython", "Calculix")
            assembly.addPart(part)
            fem_part.mbdItem = part
            fem_part.solver = solver
            assembly.times = [0.0, 0.25, 0.5, 0.75]
            part.xs = [0.0, 1000.0, 2000.0, 3000.0]
            part.ys = [0.0, 0.0, 0.0, 0.0]
            part.zs = [0.0, 0.0, 0.0, 0.0]

            class FakeCcxTools:
                def __init__(self, tool_fem_part, tool_solver):
                    self.fem_part = tool_fem_part
                    self.solver = tool_solver
                    self.working_dir = ""
                    self.base_name = ""
                    self.ccx_binary = "ccx"

                def setup_working_dir(self, working_dir, create=False):
                    self.working_dir = working_dir

                def set_base_name(self, base_name):
                    self.base_name = base_name

                def setup_ccx(self):
                    pass

            original_tools = FreeCADMbDFEMEmbedded.FEMPartCcxTools
            try:
                FreeCADMbDFEMEmbedded.FEMPartCcxTools = FakeCcxTools

                panel = FreeCADMbDFEMEmbedded.FEMPartSolverTaskPanel(fem_part, solver)
                panel.state_spin.lineEdit().setText("2")
                panel.solve_start_state_spin.lineEdit().setText("1")
                panel.solve_end_state_spin.lineEdit().setText("3")
                self.assertEqual(panel.import_state_button.text(), "Import states")
                self.assertEqual(panel.start_importing_button.text(), "Start Importing")
                self.assertEqual(panel.stop_importing_button.text(), "Stop Importing")
                self.assertTrue(panel.accept())

                reopened = FreeCADMbDFEMEmbedded.FEMPartSolverTaskPanel(fem_part, solver)
                try:
                    self.assertEqual(reopened.state_spin.value(), 2)
                    self.assertEqual(reopened.solve_state_spin.value(), 2)
                    self.assertEqual(reopened.solve_slider.value(), 2)
                    self.assertEqual(reopened.solve_start_state_spin.value(), 1)
                    self.assertEqual(reopened.solve_end_state_spin.value(), 3)
                    self.assertEqual(
                        reopened.fea.working_dir,
                        str(
                            Path(directory)
                            / "PanelState"
                            / "MbDFEM"
                            / "Case001"
                            / "MbDPart001"
                            / "Frame000002"
                        ),
                    )
                    self.assertEqual(reopened.fea.base_name, FreeCADMbDBackend.CALCULIX_BASE_NAME)
                finally:
                    reopened.reject()
            finally:
                FreeCADMbDFEMEmbedded.FEMPartCcxTools = original_tools

    def test_calculix_task_panel_cancel_does_not_save_values(self):
        import FreeCADMbDFEMEmbedded

        assembly = self.document.addObject("MbDFEM::MbDAssembly", "Assembly")
        part = self.document.addObject("MbDFEM::MbDPart", "MbDPart001")
        fem_part = self.document.addObject("MbDFEM::FEMPart", "FEMPart")
        solver = self.document.addObject("Fem::FemSolverObjectPython", "Calculix")
        assembly.addPart(part)
        fem_part.mbdItem = part
        fem_part.solver = solver
        assembly.times = [0.0, 0.25, 0.5, 0.75]
        part.xs = [0.0, 1000.0, 2000.0, 3000.0]
        part.ys = [0.0, 0.0, 0.0, 0.0]
        part.zs = [0.0, 0.0, 0.0, 0.0]

        class FakeCcxTools:
            def __init__(self, tool_fem_part, tool_solver):
                self.fem_part = tool_fem_part
                self.solver = tool_solver
                self.working_dir = ""
                self.base_name = ""
                self.ccx_binary = "ccx"

            def setup_working_dir(self, working_dir, create=False):
                self.working_dir = working_dir

            def set_base_name(self, base_name):
                self.base_name = base_name

            def setup_ccx(self):
                pass

        original_tools = FreeCADMbDFEMEmbedded.FEMPartCcxTools
        try:
            FreeCADMbDFEMEmbedded.FEMPartCcxTools = FakeCcxTools

            FreeCADMbDFEMEmbedded._set_solver_panel_state(fem_part, "current", 1)
            FreeCADMbDFEMEmbedded._set_solver_panel_state(fem_part, "start", 1)
            FreeCADMbDFEMEmbedded._set_solver_panel_state(fem_part, "end", 1)
            panel = FreeCADMbDFEMEmbedded.FEMPartSolverTaskPanel(fem_part, solver)
            self.Gui.Control.showDialog(panel)
            panel.state_spin.lineEdit().setText("2")
            panel.solve_start_state_spin.lineEdit().setText("1")
            panel.solve_end_state_spin.lineEdit().setText("3")

            self.assertTrue(panel.reject())

            reopened = FreeCADMbDFEMEmbedded.FEMPartSolverTaskPanel(fem_part, solver)
            try:
                self.assertEqual(reopened.state_spin.value(), 1)
                self.assertEqual(reopened.solve_state_spin.value(), 1)
                self.assertEqual(reopened.solve_slider.value(), 1)
                self.assertEqual(reopened.solve_start_state_spin.value(), 1)
                self.assertEqual(reopened.solve_end_state_spin.value(), 1)
            finally:
                reopened.reject()
        finally:
            FreeCADMbDFEMEmbedded.FEMPartCcxTools = original_tools

    def test_calculix_task_panel_reports_to_report_view_without_output_block(self):
        import FreeCADMbDFEMEmbedded

        assembly = self.document.addObject("MbDFEM::MbDAssembly", "Assembly")
        part = self.document.addObject("MbDFEM::MbDPart", "MbDPart001")
        fem_part = self.document.addObject("MbDFEM::FEMPart", "FEMPart")
        solver = self.document.addObject("Fem::FemSolverObjectPython", "Calculix")
        assembly.addPart(part)
        fem_part.mbdItem = part
        fem_part.solver = solver

        class FakeCcxTools:
            def __init__(self, tool_fem_part, tool_solver):
                self.fem_part = tool_fem_part
                self.solver = tool_solver
                self.working_dir = ""
                self.base_name = ""
                self.ccx_binary = "ccx"

            def setup_working_dir(self, working_dir, create=False):
                self.working_dir = working_dir

            def set_base_name(self, base_name):
                self.base_name = base_name

            def setup_ccx(self):
                pass

        messages = []
        original_tools = FreeCADMbDFEMEmbedded.FEMPartCcxTools
        original_print_message = App.Console.PrintMessage
        try:
            FreeCADMbDFEMEmbedded.FEMPartCcxTools = FakeCcxTools
            App.Console.PrintMessage = lambda message: messages.append(message)

            panel = FreeCADMbDFEMEmbedded.FEMPartSolverTaskPanel(fem_part, solver)
            try:
                self.assertFalse(hasattr(panel, "log"))

                panel.femConsoleMessage("Report view message")

                self.assertIn("Report view message\n", messages)
                self.assertEqual(panel.fem_console_message, "Report view message\n")
            finally:
                panel.reject()
        finally:
            App.Console.PrintMessage = original_print_message
            FreeCADMbDFEMEmbedded.FEMPartCcxTools = original_tools

    def test_mesh_task_panel_reports_to_report_view_without_output_block(self):
        import ObjectsFem
        import FreeCADMbDFEMEmbedded
        from femtaskpanels import task_mesh_gmsh

        mesh = ObjectsFem.makeMeshGmsh(self.document, "MbDFEMMesh")
        messages = []
        original_print_message = App.Console.PrintMessage
        try:
            App.Console.PrintMessage = lambda message: messages.append(message)
            FreeCADMbDFEMEmbedded.install_mesh_task_panel_report_view_override()
            panel = task_mesh_gmsh._TaskPanel(mesh)
            try:
                self.assertTrue(panel.form.te_output.isHidden())

                panel.write_log("Mesh report message\n", None)

                self.assertIn("Mesh report message\n", messages)
            finally:
                panel.reject()
        finally:
            App.Console.PrintMessage = original_print_message

    def test_calculix_task_panel_restores_saved_range_without_reordering(self):
        import FreeCADMbDFEMEmbedded

        assembly = self.document.addObject("MbDFEM::MbDAssembly", "Assembly")
        part = self.document.addObject("MbDFEM::MbDPart", "MbDPart001")
        fem_part = self.document.addObject("MbDFEM::FEMPart", "FEMPart")
        solver = self.document.addObject("Fem::FemSolverObjectPython", "Calculix")
        assembly.addPart(part)
        fem_part.mbdItem = part
        fem_part.solver = solver
        assembly.times = [0.0, 0.25, 0.5, 0.75, 1.0]
        part.xs = [0.0, 1000.0, 2000.0, 3000.0, 4000.0]
        part.ys = [0.0, 0.0, 0.0, 0.0, 0.0]
        part.zs = [0.0, 0.0, 0.0, 0.0, 0.0]

        class FakeCcxTools:
            def __init__(self, tool_fem_part, tool_solver):
                self.fem_part = tool_fem_part
                self.solver = tool_solver
                self.working_dir = ""
                self.base_name = ""
                self.ccx_binary = "ccx"

            def setup_working_dir(self, working_dir, create=False):
                self.working_dir = working_dir

            def set_base_name(self, base_name):
                self.base_name = base_name

            def setup_ccx(self):
                pass

        original_tools = FreeCADMbDFEMEmbedded.FEMPartCcxTools
        try:
            FreeCADMbDFEMEmbedded.FEMPartCcxTools = FakeCcxTools
            FreeCADMbDFEMEmbedded._set_solver_panel_state(fem_part, "current", 2)
            FreeCADMbDFEMEmbedded._set_solver_panel_state(fem_part, "start", 4)
            FreeCADMbDFEMEmbedded._set_solver_panel_state(fem_part, "end", 2)

            panel = FreeCADMbDFEMEmbedded.FEMPartSolverTaskPanel(fem_part, solver)
            try:
                self.assertEqual(panel.state_spin.value(), 2)
                self.assertEqual(panel.solve_start_state_spin.value(), 4)
                self.assertEqual(panel.solve_end_state_spin.value(), 2)
            finally:
                panel.reject()
        finally:
            FreeCADMbDFEMEmbedded.FEMPartCcxTools = original_tools

    def test_calculix_task_panel_importing_saves_finished_state_and_range(self):
        import FreeCADMbDFEMEmbedded
        import FreeCADMbDFEMResultsPanel

        assembly = self.document.addObject("MbDFEM::MbDAssembly", "Assembly")
        part = self.document.addObject("MbDFEM::MbDPart", "MbDPart001")
        fem_part = self.document.addObject("MbDFEM::FEMPart", "FEMPart")
        solver = self.document.addObject("Fem::FemSolverObjectPython", "Calculix")
        assembly.addPart(part)
        fem_part.mbdItem = part
        fem_part.solver = solver
        assembly.times = [0.0, 0.25, 0.5, 0.75]
        part.xs = [0.0, 1000.0, 2000.0, 3000.0]
        part.ys = [0.0, 0.0, 0.0, 0.0]
        part.zs = [0.0, 0.0, 0.0, 0.0]

        class FakeCcxTools:
            def __init__(self, tool_fem_part, tool_solver):
                self.fem_part = tool_fem_part
                self.solver = tool_solver
                self.working_dir = ""
                self.base_name = ""
                self.ccx_binary = "ccx"

            def setup_working_dir(self, working_dir, create=False):
                self.working_dir = working_dir

            def set_base_name(self, base_name):
                self.base_name = base_name

            def setup_ccx(self):
                pass

        class FakeResult:
            def __init__(self, label):
                self.Label = label

        imported = []

        def import_state(import_fem_part, state_index):
            self.assertIs(import_fem_part, fem_part)
            imported.append(state_index)
            return FakeResult(f"State {state_index}")

        original_tools = FreeCADMbDFEMEmbedded.FEMPartCcxTools
        original_import_state = FreeCADMbDFEMResultsPanel.import_fem_part_state
        try:
            FreeCADMbDFEMEmbedded.FEMPartCcxTools = FakeCcxTools
            FreeCADMbDFEMResultsPanel.import_fem_part_state = import_state

            panel = FreeCADMbDFEMEmbedded.FEMPartSolverTaskPanel(fem_part, solver)
            panel.solve_start_state_spin.lineEdit().setText("1")
            panel.solve_end_state_spin.lineEdit().setText("2")
            self.assertTrue(panel._start_importing())
            self.assertEqual(imported, [1, 2])
            self.assertFalse(hasattr(fem_part, "MbDFEMSolverPanelCurrentState"))
            self.assertFalse(hasattr(fem_part, "MbDFEMSolverPanelStartState"))
            self.assertFalse(hasattr(fem_part, "MbDFEMSolverPanelEndState"))
            self.assertTrue(panel.accept())
            self.assertEqual(fem_part.MbDFEMSolverPanelCurrentState, 2)
            self.assertEqual(fem_part.MbDFEMSolverPanelStartState, 1)
            self.assertEqual(fem_part.MbDFEMSolverPanelEndState, 2)

            reopened = FreeCADMbDFEMEmbedded.FEMPartSolverTaskPanel(fem_part, solver)
            try:
                self.assertEqual(reopened.state_spin.value(), 2)
                self.assertEqual(reopened.solve_state_spin.value(), 2)
                self.assertEqual(reopened.solve_slider.value(), 2)
                self.assertEqual(reopened.solve_start_state_spin.value(), 1)
                self.assertEqual(reopened.solve_end_state_spin.value(), 2)
            finally:
                reopened.reject()
        finally:
            FreeCADMbDFEMResultsPanel.import_fem_part_state = original_import_state
            FreeCADMbDFEMEmbedded.FEMPartCcxTools = original_tools

    def test_calculix_task_panel_defaults_to_latest_imported_state(self):
        import FreeCADMbDFEMEmbedded
        import FreeCADMbDFEMResultsPanel

        assembly = self.document.addObject("MbDFEM::MbDAssembly", "Assembly")
        part = self.document.addObject("MbDFEM::MbDPart", "MbDPart001")
        fem_part = self.document.addObject("MbDFEM::FEMPart", "FEMPart")
        solver = self.document.addObject("Fem::FemSolverObjectPython", "Calculix")
        assembly.addPart(part)
        fem_part.mbdItem = part
        fem_part.solver = solver
        assembly.times = [0.0, 0.25, 0.5, 0.75]
        part.xs = [0.0, 1000.0, 2000.0, 3000.0]
        part.ys = [0.0, 0.0, 0.0, 0.0]
        part.zs = [0.0, 0.0, 0.0, 0.0]

        for state_index in (0, 1, 2):
            result = self.document.addObject(
                "Fem::FemResultObjectPython",
                f"CCX_Results_{state_index}",
            )
            FreeCADMbDFEMResultsPanel._assign_result_for_state(
                fem_part,
                state_index,
                result,
            )

        class FakeCcxTools:
            def __init__(self, tool_fem_part, tool_solver):
                self.fem_part = tool_fem_part
                self.solver = tool_solver
                self.working_dir = ""
                self.base_name = ""
                self.ccx_binary = "ccx"

            def setup_working_dir(self, working_dir, create=False):
                self.working_dir = working_dir

            def set_base_name(self, base_name):
                self.base_name = base_name

            def setup_ccx(self):
                pass

        original_tools = FreeCADMbDFEMEmbedded.FEMPartCcxTools
        try:
            FreeCADMbDFEMEmbedded.FEMPartCcxTools = FakeCcxTools

            panel = FreeCADMbDFEMEmbedded.FEMPartSolverTaskPanel(fem_part, solver)
            try:
                self.assertEqual(panel.state_spin.value(), 2)
                self.assertEqual(panel.solve_state_spin.value(), 2)
                self.assertEqual(panel.solve_slider.value(), 2)
                self.assertEqual(panel.solve_start_state_spin.value(), 0)
                self.assertEqual(panel.solve_end_state_spin.value(), 2)
            finally:
                panel.reject()
        finally:
            FreeCADMbDFEMEmbedded.FEMPartCcxTools = original_tools

    def test_results_panel_interval_controls_and_playback_use_state_results(self):
        import FreeCADMbDFEMResultsPanel

        assembly = self.document.addObject("MbDFEM::MbDAssembly", "Assembly")
        part = self.document.addObject("MbDFEM::MbDPart", "Part")
        fem_part = self.document.addObject("MbDFEM::FEMPart", "FEMPart")
        result_1 = self.document.addObject("Fem::FemResultObjectPython", "CCX_Results_1")
        result_2 = self.document.addObject("Fem::FemResultObjectPython", "CCX_Results_2")
        assembly.addPart(part)
        fem_part.mbdItem = part
        assembly.times = [0.0, 0.25, 0.5]
        part.xs = [0.0, 1000.0, 2000.0]
        part.ys = [0.0, 2000.0, 4000.0]
        part.zs = [0.0, 3000.0, 6000.0]
        folder = fem_part.ensureResultsFolder()
        FreeCADMbDFEMResultsPanel._assign_result_for_state(fem_part, 2, result_2)
        FreeCADMbDFEMResultsPanel._assign_result_for_state(fem_part, 1, result_1)
        self.document.recompute()
        self.Gui.updateGui()

        panel = FreeCADMbDFEMResultsPanel.FEMResultsTaskPanel(folder)
        loaded_results = []
        original_ensure_pipeline = FreeCADMbDFEMResultsPanel._ensure_visual_pipeline

        def ensure_pipeline(runner_fem_part, result, preferred_field=None):
            self.assertIs(runner_fem_part, fem_part)
            self.assertIn(preferred_field, ("von Mises Stress", "Displacement Magnitude"))
            loaded_results.append(result)
            return pipeline

        pipeline = self.document.addObject("Fem::FemPostPipeline", "Pipeline_CCX_Results")
        fem_part.visual = pipeline
        FreeCADMbDFEMResultsPanel._ensure_visual_pipeline = ensure_pipeline
        try:
            self.assertEqual(panel.start_state_spin.value(), 1)
            self.assertEqual(panel.end_state_spin.value(), 2)
            panel.start_state_spin.setValue(1)
            panel.end_state_spin.setValue(2)
            self.assertEqual(panel._interval_indices(), [1, 2])
            self.assertEqual(panel.start_state_count_label.text(), "/ 2")
            self.assertEqual(panel.end_state_count_label.text(), "/ 2")
            self.assertEqual(panel.start_time_label.text(), "0.25 s")
            self.assertEqual(panel.end_time_label.text(), "0.5 s")

            panel._set_state(1)
            self.assertIs(loaded_results[-1], result_1)
            self.assertFalse(result_1.ViewObject.Visibility)
            self.assertFalse(result_2.ViewObject.Visibility)
            self.assertTrue(pipeline.ViewObject.Visibility)
            self.assertEqual(part.Placement.Base, App.Vector(1000.0, 2000.0, 3000.0))

            panel._play_results()
            self.assertTrue(panel._playing)
            panel._play_next_state()
            self.assertEqual(panel.state_spin.value(), 2)
            self.assertIs(loaded_results[-1], result_2)
            self.assertFalse(result_1.ViewObject.Visibility)
            self.assertFalse(result_2.ViewObject.Visibility)
            self.assertTrue(pipeline.ViewObject.Visibility)
            panel._stop_playback()
            self.assertFalse(panel._playing)
        finally:
            FreeCADMbDFEMResultsPanel._ensure_visual_pipeline = original_ensure_pipeline
            panel.reject()

    def test_results_visibility_and_display_options_survive_state_changes(self):
        from unittest.mock import patch
        import re
        import Fem
        from femobjects import result_mechanical
        import FreeCADMbDFEMResultsPanel as Results

        assembly = self.document.addObject("MbDFEM::MbDAssembly", "Assembly")
        part = self.document.addObject("MbDFEM::MbDPart", "Part")
        assembly.addPart(part)
        assembly.times = [0.0, 0.25]
        part.xs = [0.0, 1000.0]
        part.ys = part.zs = [0.0, 0.0]
        fem_part = self.document.addObject("MbDFEM::FEMPart", "FEMPart")
        fem_part.mbdItem = part
        mesh = Fem.FemMesh()
        for xyz in ((0, 0, 0), (10, 0, 0), (0, 10, 0), (0, 0, 10)):
            mesh.addNode(*xyz)
        mesh.addVolume([1, 2, 3, 4])
        original_mesh = self.document.addObject("Fem::FemMeshObject", "OriginalMesh")
        original_mesh.FemMesh = mesh
        fem_part.mesh = original_mesh
        original_mesh.ViewObject.Visibility = True
        for index in range(2):
            result = self.document.addObject("Fem::FemResultObjectPython", f"Result{index}")
            result_mechanical.ResultMechanical(result)
            result.Mesh = self.document.addObject("Fem::FemMeshObject", f"ResultMesh{index}")
            result.Mesh.FemMesh = mesh
            result.NodeNumbers = [1, 2, 3, 4]
            result.vonMises = [1.0, 2.0, 3.0, 4.0]
            Results._assign_result_for_state(fem_part, index, result)
        folder = fem_part.ensureResultsFolder()
        self.document.recompute()
        # The embedded solver creates an ordinary FEM pipeline before the
        # results task panel is opened. Exercise that adoption path too.
        legacy = self.document.addObject("Fem::FemPostPipeline", "SolverPipeline")
        legacy.load(Results._result_for_state(fem_part, 0))
        Results.FreeCADMbDFEMEmbedded.FEMPartAnalysisAdapter(fem_part).addObject(legacy)
        self.assertIs(fem_part.visual, legacy)
        with patch.object(Results.FreeCADMbDBackend, "fem_files_freshness_warning", return_value=""):
            panel = Results.FEMResultsTaskPanel(folder)
        panel._suppress_fem_freshness_warning = True

        try:
            panel._show_state(0)
            view = fem_part.visual.ViewObject
            self.assertEqual(view.TypeId, "MbDFEMGui::ViewProviderFEMPostPipeline")
            self.assertIs(fem_part.visual.MbDFEMSourcePipeline, legacy)
            self.assertFalse(legacy.ViewObject.Visibility)
            self.assertEqual(str(view.Field), "von Mises Stress")

            def material_binding():
                # Inspect the native scene serialization without borrowing
                # Coin nodes across the Pivy wrapper's ownership boundary.
                match = re.search(r"MaterialBinding\s*\{\s*value\s+(\w+)", view.toString())
                self.assertIsNotNone(match)
                return match.group(1)

            selected_field = str(view.Field)
            self.assertEqual(material_binding(), "PER_VERTEX_INDEXED")
            self.assertTrue(folder.ViewObject.isVisible())
            self.assertTrue(view.Visibility)
            self.assertTrue(view.ShowColorContour)

            from PySide.QtGui import QImage

            active_view = self.Gui.getDocument(self.document.Name).activeView()
            active_view.viewAxonometric()
            active_view.fitAll()

            def rendered_image():
                self.Gui.updateGui()
                with tempfile.TemporaryDirectory() as directory:
                    image_path = str(Path(directory) / "display.png")
                    active_view.saveImage(image_path, 640, 480, "White")
                    image = QImage(image_path)
                    self.assertFalse(image.isNull())
                    return image

            def legend_region(image):
                # Camera animations can still move the model between frames.
                # Inspect the legend separately, below the navigation cube.
                return image.copy(
                    3 * image.width() // 4,
                    image.height() // 3,
                    image.width() // 4,
                    2 * image.height() // 3,
                )

            with_legend = rendered_image()
            panel.legend_checkbox.setChecked(False)
            self.assertFalse(view.ShowLegend)
            self.assertTrue(view.ShowColorContour)
            without_legend = rendered_image()
            self.assertNotEqual(legend_region(with_legend), legend_region(without_legend))
            panel.legend_checkbox.setChecked(True)
            self.assertEqual(legend_region(with_legend), legend_region(rendered_image()))
            panel.legend_checkbox.setChecked(False)
            panel.contour_checkbox.setChecked(False)
            self.assertFalse(panel.legend_checkbox.isEnabled())
            self.assertFalse(view.ShowColorContour)
            self.assertEqual(str(view.Field), selected_field)
            self.assertEqual(material_binding(), "OVERALL")
            self.assertNotEqual(without_legend, rendered_image())
            view.updateColorBars()
            self.assertEqual(material_binding(), "OVERALL")

            # Ordinary FEM pipelines must retain their original interface.
            ordinary = self.document.addObject("Fem::FemPostPipeline", "OrdinaryPipeline")
            self.assertNotIn("ShowColorContour", ordinary.ViewObject.PropertiesList)
            self.assertNotIn("ShowLegend", ordinary.ViewObject.PropertiesList)
            ordinary.ViewObject.hide()
            self.Gui.updateGui()
            self.assertEqual(material_binding(), "OVERALL")

            # Exercise the same command as Space in the tree.
            self.Gui.Selection.clearSelection()
            self.Gui.Selection.addSelection(folder)
            self.Gui.runCommand("Std_ToggleVisibility", 0)
            self.assertFalse(folder.ViewObject.isVisible())
            self.assertFalse(view.Visibility)
            panel._show_state(1)
            panel.start_state_spin.setValue(0)
            panel._play_results()
            panel._play_next_state()
            panel._stop_playback()
            self.Gui.updateGui()  # Includes deferred color-bar refreshes.
            self.assertFalse(view.Visibility)
            self.assertFalse(view.ShowColorContour)
            self.assertFalse(view.ShowLegend)

            self.Gui.runCommand("Std_ToggleVisibility", 0)
            self.assertTrue(folder.ViewObject.isVisible())
            self.assertTrue(view.Visibility)
            self.assertFalse(view.ShowColorContour)
            panel.contour_checkbox.setChecked(True)
            self.assertTrue(panel.legend_checkbox.isEnabled())
            self.assertFalse(panel.legend_checkbox.isChecked())
            self.assertTrue(view.ShowColorContour)
            self.assertTrue(original_mesh.ViewObject.Visibility)
            self.assertEqual(material_binding(), "PER_VERTEX_INDEXED")
            panel.hide_results_button.click()
            self.assertFalse(view.Visibility)
        finally:
            panel.reject()

        with patch.object(Results.FreeCADMbDBackend, "fem_files_freshness_warning", return_value=""):
            reopened = Results.FEMResultsTaskPanel(folder)
        reopened._suppress_fem_freshness_warning = True
        try:
            self.assertTrue(reopened.contour_checkbox.isChecked())
            self.assertFalse(reopened.legend_checkbox.isChecked())
            self.assertFalse(fem_part.visual.ViewObject.Visibility)
        finally:
            reopened.reject()

        with tempfile.TemporaryDirectory() as directory:
            path = str(Path(directory) / "ResultsDisplay.FCStd")
            part_name = fem_part.Name
            self.document.recompute()
            self.document.saveAs(path)
            App.closeDocument(self.document.Name)
            self.document = App.openDocument(path)
            restored = self.document.getObject(part_name)
            self.assertEqual(restored.visual.ViewObject.TypeId,
                             "MbDFEMGui::ViewProviderFEMPostPipeline")
            restored_folder = restored.getResultsFolder()
            self.assertFalse(restored_folder.ViewObject.isVisible())
            self.assertFalse(restored.visual.ViewObject.Visibility)
            self.assertTrue(restored_folder.ViewObject.ShowColorContour)
            self.assertFalse(restored_folder.ViewObject.ShowLegend)
            restored_folder.ViewObject.show()
            self.assertTrue(restored.visual.ViewObject.Visibility)
            self.assertFalse(restored.visual.ViewObject.ShowLegend)

    def _make_fem_animation_model(self):
        import Fem
        from femobjects import result_mechanical
        import FreeCADMbDFEMResultsPanel as Results

        mbd = self.document.addObject("MbDFEM::MbDAssembly", "Assembly")
        mbd.ensureAnimationParameters()
        mbd.times = [0.0, 0.1, 0.2, 0.3]
        fem = self.document.addObject("MbDFEM::FEMAssembly", "FEMAssembly")
        fem.mbdItem = mbd
        parts = []
        for body in range(3):
            motion = self.document.addObject("MbDFEM::MbDPart", f"Body{body}")
            mbd.addPart(motion)
            motion.xs = [100 * body + 10 * (body + 1) * state for state in range(4)]
            motion.ys = motion.zs = [0.0] * 4
            motion.bryxs = motion.bryys = [0.0] * 4
            motion.bryzs = [0.0, 0.1, 0.2, 0.3]
            part = self.document.addObject("MbDFEM::FEMPart", f"FEMBody{body}")
            part.mbdItem = motion
            part.ensureResultsFolder()
            mesh = Fem.FemMesh()
            size = 10 * (body + 1)
            for xyz in ((0, 0, 0), (size, 0, 0), (0, size, 0), (0, 0, size)):
                mesh.addNode(*xyz)
            mesh.addVolume([1, 2, 3, 4])
            for state in range(4):
                result = self.document.addObject("Fem::FemResultObjectPython", f"Result{body}_{state}")
                result_mechanical.ResultMechanical(result)
                result.Mesh = self.document.addObject("Fem::FemMeshObject", f"Mesh{body}_{state}")
                result.Mesh.FemMesh = mesh
                result.NodeNumbers = [1, 2, 3, 4]
                result.vonMises = [(body + 1) * (state + 1) * node for node in range(1, 5)]
                result.DisplacementVectors = [App.Vector(0, 0, state * 0.01)] * 4
                result.DisplacementLengths = [state * 0.01] * 4
                Results._assign_result_for_state(part, state, result)
            parts.append(part)
        for part in parts:
            fem.addObject(part)
        fem.parts = parts
        self.document.recompute()
        return fem, parts

    def test_fem_assembly_creates_parameter_tree_children_before_panels_open(self):
        fem = self.document.addObject("MbDFEM::FEMAssembly", "FEMAssembly")
        simulation = fem.femParameters
        animation = fem.animationParameters
        self.assertEqual(simulation.TypeId, "MbDFEM::FEMSimulationParameters")
        self.assertEqual(animation.TypeId, "MbDFEM::FEMAnimationParameters")
        self.assertEqual(simulation.Label, "SimulationParameters")
        self.assertEqual(animation.Label, "AnimationParameters")
        self.assertFalse(simulation.settingsInitialized)
        self.assertFalse(animation.settingsInitialized)
        self.assertIn(simulation, fem.Group)
        self.assertIn(animation, fem.Group)
        self.assertEqual(fem.ViewObject.claimChildren()[:2], [simulation, animation])
        self.document.recompute()
        self.assertIs(fem.femParameters, simulation)
        self.assertIs(fem.animationParameters, animation)
        self.assertEqual(len([obj for obj in self.document.Objects
                              if obj.TypeId in (simulation.TypeId, animation.TypeId)]), 2)

    def test_fem_assembly_restores_missing_parameter_tree_children_without_duplicates(self):
        fem = self.document.addObject("MbDFEM::FEMAssembly", "FEMAssembly")
        name = fem.Name
        old_parameters = [fem.femParameters.Name, fem.animationParameters.Name]
        fem.femParameters = None
        fem.animationParameters = None
        for parameter in old_parameters:
            self.document.removeObject(parameter)
        # Represent an older file saved before either panel had been opened.
        self.assertIsNone(fem.femParameters)
        self.assertIsNone(fem.animationParameters)
        with tempfile.TemporaryDirectory() as directory:
            path = str(Path(directory) / "OldFEMAssembly.FCStd")
            self.document.saveAs(path)
            App.closeDocument(self.document.Name)
            self.document = App.openDocument(path)
            restored = self.document.getObject(name)
            simulation = restored.femParameters
            animation = restored.animationParameters
            self.assertEqual(simulation.TypeId, "MbDFEM::FEMSimulationParameters")
            self.assertEqual(animation.TypeId, "MbDFEM::FEMAnimationParameters")
            self.assertEqual(restored.ViewObject.claimChildren()[:2], [simulation, animation])
            self.assertIn(simulation, restored.Group)
            self.assertIn(animation, restored.Group)
            simulation.startState = animation.startFrame = 10
            simulation.endState = animation.endFrame = 40
            simulation.settingsInitialized = animation.settingsInitialized = True
            parameter_names = [simulation.Name, animation.Name]
            self.document.save()
            App.closeDocument(self.document.Name)
            self.document = App.openDocument(path)
            restored = self.document.getObject(name)
            self.assertEqual([restored.femParameters.Name, restored.animationParameters.Name], parameter_names)
            self.assertEqual(restored.femParameters.endState, 40)
            self.assertEqual(restored.animationParameters.endFrame, 40)
            self.assertEqual(len([obj for obj in self.document.Objects if obj.TypeId in
                                  ("MbDFEM::FEMSimulationParameters", "MbDFEM::FEMAnimationParameters")]), 2)

    def _wait_fem_simulation(self, panel, timeout=10000):
        from time import monotonic
        from PySide import QtCore, QtWidgets

        deadline = monotonic() + timeout / 1000
        while panel._running and monotonic() < deadline:
            QtWidgets.QApplication.processEvents(QtCore.QEventLoop.AllEvents, 20)
        self.assertFalse(panel._running, panel.status_label.text())

    def test_fem_simulation_queue_uses_one_pose_per_state_and_current_results(self):
        from unittest.mock import patch
        import FreeCADMbDFEMSimulation as Simulation
        import FreeCADMbDFEMResultsPanel as Results

        fem, parts = self._make_fem_animation_model()
        controller = Simulation.FEMSimulationController(fem)
        jobs = controller.jobs(parts[:2], [1, 2])
        self.assertEqual(jobs, [(parts[0], 1), (parts[1], 1), (parts[0], 2), (parts[1], 2)])
        with patch.object(controller.motion, "setFrame", wraps=controller.motion.setFrame) as move:
            for part, state in jobs:
                controller.apply_state(state)
                self.assertEqual(part.Placement.Base, part.mbdItem.Placement.Base)
            self.assertEqual(move.call_count, 2)
        with patch.object(Simulation.Backend, "fem_files_freshness_warning", return_value=""):
            self.assertEqual(controller.jobs(parts[:2], [1, 2], True), [])
            Results._result_for_state(parts[1], 2).MbDFEMStateTime = 9.0
            self.assertEqual(controller.jobs(parts[:2], [1, 2], True), [(parts[1], 2)])
        with patch.object(Simulation.Backend, "fem_files_freshness_warning", return_value="Stale"):
            self.assertEqual(controller.jobs(parts[:2], [1], True), [(parts[0], 1), (parts[1], 1)])
        with self.assertRaises(ValueError):
            controller.jobs([], [1])
        with self.assertRaises(ValueError):
            controller.jobs(parts, [4])
        foreign = self.document.addObject("MbDFEM::FEMPart", "Foreign")
        with self.assertRaises(ValueError):
            controller.jobs([foreign], [1])

    def test_fem_simulation_write_queue_stops_between_jobs(self):
        from unittest.mock import patch
        import FreeCADMbDFEMSimulation as Simulation

        fem, parts = self._make_fem_animation_model()
        panel = Simulation.FEMSimulationTaskPanel(fem)
        written = []

        def write(part, state, **kwargs):
            written.append((part, state))
            panel._stop()

        try:
            panel.first_spin.setValue(1)
            panel.last_spin.setValue(2)
            with patch.object(panel.controller, "tools", side_effect=write):
                panel._start("write")
                self._wait_fem_simulation(panel)
            self.assertEqual(written, [(parts[0], 1)])
            self.assertEqual(panel._succeeded, 1)
            self.assertIn("5 pending", panel.status_label.text())
            self.assertTrue(panel.action_buttons[0].isEnabled())
        finally:
            panel.reject()

    def test_fem_simulation_import_queue_retains_success_and_failure_policy(self):
        from unittest.mock import patch
        import FreeCADMbDFEMSimulation as Simulation

        fem, parts = self._make_fem_animation_model()
        panel = Simulation.FEMSimulationTaskPanel(fem)
        imported = []

        def import_result(part, state):
            if part == parts[1]:
                raise RuntimeError("Missing FRD")
            imported.append((part, state))

        try:
            panel.first_spin.setValue(1)
            panel.last_spin.setValue(2)
            panel.missing_check.setChecked(False)
            with patch.object(panel, "_import_result", side_effect=import_result):
                panel._start("import")
                self._wait_fem_simulation(panel)
                self.assertEqual(panel._succeeded, 4)
                self.assertEqual(panel._failures, 2)
                self.assertEqual(imported, [(parts[0], 1), (parts[2], 1), (parts[0], 2), (parts[2], 2)])
                panel.continue_check.setChecked(False)
                panel._start("import")
                self._wait_fem_simulation(panel)
                self.assertEqual(panel._succeeded, 1)
                self.assertEqual(panel._failures, 1)
                self.assertIn("4 pending", panel.status_label.text())
        finally:
            panel.reject()

    def test_fem_simulation_settings_save_pending_edits_and_reopen(self):
        import FreeCADMbDFEMSimulation as Simulation

        fem, parts = self._make_fem_animation_model()
        panel = Simulation.FEMSimulationTaskPanel(fem)
        try:
            settings = fem.femParameters
            self.assertEqual(settings.TypeId, "MbDFEM::FEMSimulationParameters")
            self.assertIn(settings, fem.Group)
            self.assertIn(settings, fem.ViewObject.claimChildren())
            panel.body_checks[1][1].setChecked(False)
            panel.missing_check.setChecked(False)
            panel.continue_check.setChecked(False)
            panel.current_spin.setValue(2)
            panel.first_spin.lineEdit().setText("0")
            panel.last_spin.lineEdit().setText("2")
            name = fem.Name
            selected = [parts[0].Name, parts[2].Name]
            with tempfile.TemporaryDirectory() as directory:
                path = str(Path(directory) / "AssemblySimulation.FCStd")
                self.document.saveAs(path)
                self.assertEqual(settings.startState, 0)
                self.assertEqual(settings.endState, 2)
                panel.reject()
                App.closeDocument(self.document.Name)
                self.document = App.openDocument(path)
                restored = self.document.getObject(name)
                reopened = Simulation.FEMSimulationTaskPanel(restored)
                try:
                    self.assertEqual([part.Name for part in restored.femParameters.selectedParts], selected)
                    self.assertEqual(reopened.current_spin.value(), 2)
                    self.assertEqual(reopened.first_spin.value(), 0)
                    self.assertEqual(reopened.last_spin.value(), 2)
                    self.assertFalse(reopened.missing_check.isChecked())
                    self.assertFalse(reopened.continue_check.isChecked())
                    self.assertFalse(reopened._running)
                    for part, check in reopened.body_checks:
                        check.setChecked(False)
                    reopened.accept()
                    empty = Simulation.FEMSimulationTaskPanel(restored)
                    try:
                        self.assertFalse(any(check.isChecked() for part, check in empty.body_checks))
                    finally:
                        empty.reject()
                finally:
                    reopened.reject()
        finally:
            if panel._observing:
                panel.reject()

    def test_fem_workbench_context_menu_without_init_module_globals(self):
        from unittest.mock import patch

        fem, parts = self._make_fem_animation_model()
        self.Gui.Selection.clearSelection()
        self.Gui.Selection.addSelection(parts[0])
        workbench = self.Gui.getWorkbench("MbDFEMWorkbench")
        menus = []
        with patch.object(workbench, "appendContextMenu", side_effect=lambda *args: menus.append(args)):
            # FreeCAD executes InitGui.py as a script and clears its startup globals.
            with patch.dict(workbench.ContextMenu.__globals__, {}, clear=True):
                workbench.ContextMenu("Tree")
        self.assertEqual(menus, [("MbDFEM", ["MbDFEM_AnimateFEMResults", "MbDFEM_SimulateFEMAssembly"])])
        self.Gui.Selection.clearSelection()
        with patch.object(workbench, "appendContextMenu") as append:
            with patch.dict(workbench.ContextMenu.__globals__, {}, clear=True):
                workbench.ContextMenu("Tree")
            append.assert_called_once()

    def test_fem_simulation_command_and_parameters_open_owner(self):
        from unittest.mock import patch
        import FreeCADMbDFEMSimulation as Simulation

        fem, parts = self._make_fem_animation_model()
        settings = Simulation.ensure_simulation_parameters(fem)
        self.document.recompute()
        self.Gui.Selection.clearSelection()
        self.Gui.Selection.addSelection(settings)
        self.assertIs(Simulation.SimulateFEMAssemblyCommand.active_assembly(), fem)
        self.assertIn("MbDFEM_SimulateFEMAssembly", self.Gui.listCommands())
        with patch.object(Simulation, "show_simulation_task_panel") as show:
            self.assertTrue(settings.ViewObject.doubleClicked())
            show.assert_called_once_with(fem)
            show.reset_mock()
            self.Gui.runCommand("MbDFEM_SimulateFEMAssembly", 0)
            show.assert_called_once_with(fem)

    def test_fem_simulation_process_failure_keeps_existing_results(self):
        from types import SimpleNamespace
        from unittest.mock import patch
        import FreeCADMbDFEMSimulation as Simulation
        import FreeCADMbDFEMResultsPanel as Results

        fem, parts = self._make_fem_animation_model()
        panel = Simulation.FEMSimulationTaskPanel(fem)
        before = Results._result_for_state(parts[0], 1)
        try:
            panel.body_checks[1][1].setChecked(False)
            panel.body_checks[2][1].setChecked(False)
            panel.missing_check.setChecked(False)
            panel.current_spin.setValue(1)
            with tempfile.TemporaryDirectory() as directory:
                inp = Path(directory) / "calculix.inp"
                inp.write_text("unused", encoding="utf-8")
                inp.with_suffix(".frd").write_text("old result", encoding="utf-8")
                tools = SimpleNamespace(
                    inp_file_name=str(inp), ccx_binary=str(Path(directory) / "missing-ccx"),
                    ccx_binary_present=True, setup_ccx=lambda: None,
                    ccx_prefs=App.ParamGet("User parameter:BaseApp/Preferences/Mod/Fem/Ccx"),
                )
                with patch.object(panel.controller, "tools", return_value=tools):
                    panel._start("solve", current=True)
                    self._wait_fem_simulation(panel)
                self.assertEqual(panel._failures, 1)
                self.assertEqual(panel._succeeded, 0)
                self.assertIs(Results._result_for_state(parts[0], 1), before)
                self.assertEqual(inp.with_suffix(".frd").read_text(), "old result")
        finally:
            panel.reject()

    def test_fem_simulation_document_close_detaches_observer(self):
        import FreeCADMbDFEMSimulation as Simulation

        fem, parts = self._make_fem_animation_model()
        panel = Simulation.FEMSimulationTaskPanel(fem)
        panel.missing_check.setChecked(False)
        panel._start("import")
        name = self.document.Name
        App.closeDocument(name)
        self.document = App.newDocument(name)
        self.assertTrue(panel._closed)
        self.assertFalse(panel._observing)
        self.assertFalse(panel._timer.isActive())
        with tempfile.TemporaryDirectory() as directory:
            self.document.saveAs(str(Path(directory) / "Replacement.FCStd"))

    def test_fem_simulation_real_calculix_solves_two_parts_and_two_states(self):
        import shutil
        from unittest.mock import patch
        import ObjectsFem
        import FreeCADMbDFEMSimulation as Simulation
        import FreeCADMbDFEMResultsPanel as Results

        ccx = Path(App.getHomePath()) / "bin" / ("ccx.exe" if sys.platform == "win32" else "ccx")
        if not ccx.is_file():
            found = shutil.which("ccx")
            if not found:
                self.skipTest("CalculiX executable not available")
            ccx = Path(found)
        fem, parts = self._make_fem_animation_model()
        for part in parts[:2]:
            part.mesh = Results._result_for_state(part, 0).Mesh
            import Fem

            mesh = Fem.FemMesh()
            for number, point in part.mesh.FemMesh.Nodes.items():
                mesh.addNode(point.x, point.y, point.z, number)
            # FreeCAD exports the tetrahedron using its own node-order convention.
            mesh.addVolume([1, 3, 2, 4])
            part.mesh.FemMesh = mesh
            part.solver = ObjectsFem.makeSolverCalculiXCcxTools(self.document, part.Name + "Solver")
            part.addObject(part.solver)
            material = ObjectsFem.makeMaterialSolid(self.document, part.Name + "Material")
            material.Material = {"Name": "Steel", "YoungsModulus": "210000 MPa",
                                 "PoissonRatio": "0.3", "Density": "7850 kg/m^3"}
            part.addObject(material)
        self.document.recompute()
        panel = Simulation.FEMSimulationTaskPanel(fem)
        panel.body_checks[2][1].setChecked(False)
        panel.missing_check.setChecked(False)
        panel.first_spin.setValue(1)
        panel.last_spin.setValue(2)
        old = {part.Name: Results._result_for_state(part, 1).Name for part in parts[:2]}
        prefs = App.ParamGet("User parameter:BaseApp/Preferences/Mod/Fem/Ccx")
        binary = prefs.GetString("ccxBinaryPath", "")
        prefs.SetString("ccxBinaryPath", str(ccx))
        try:
            with tempfile.TemporaryDirectory() as directory:
                def working_dir(part, state):
                    path = Path(directory) / part.Name / f"Frame{state:06d}"
                    path.mkdir(parents=True, exist_ok=True)
                    return path

                with patch.object(Simulation.Backend, "default_calculix_working_dir", side_effect=working_dir):
                    panel._start("solve")
                    self._wait_fem_simulation(panel, timeout=60000)
                    if panel._failures:
                        for log in Path(directory).rglob("calculix.log"):
                            App.Console.PrintError(f"{log}:\n{log.read_text(errors='replace')}\n")
                    self.assertEqual(panel._failures, 0, panel.status_label.text())
                    self.assertEqual(panel._succeeded, 4)
                    for part in parts[:2]:
                        self.assertNotEqual(Results._result_for_state(part, 1).Name, old[part.Name])
                        for state in (1, 2):
                            result = Results._result_for_state(part, state)
                            self.assertEqual(result.MbDFEMStateIndex, state)
                            self.assertAlmostEqual(result.MbDFEMStateTime, fem.mbdItem.times[state])
                            self.assertTrue(result.NodeNumbers)
                            self.assertTrue(working_dir(part, state).joinpath("calculix.frd").is_file())
                            self.assertTrue(working_dir(part, state).joinpath("calculix.log").is_file())
                    panel._start("import")
                    self._wait_fem_simulation(panel)
                    self.assertEqual(panel._failures, 0)
                    self.assertEqual(panel._succeeded, 4)
                    launch = panel._launch

                    def stop_after_launch(*args):
                        launch(*args)
                        self.assertFalse(panel.accept())
                        self.assertTrue(panel._stop_requested)

                    with patch.object(panel, "_launch", side_effect=stop_after_launch):
                        panel._start("solve")
                        self._wait_fem_simulation(panel, timeout=60000)
                    self.assertEqual(panel._succeeded, 1)
                    self.assertEqual(panel._failures, 0)
                    self.assertIn("3 pending", panel.status_label.text())
        finally:
            prefs.SetString("ccxBinaryPath", binary)
            if panel._running:
                panel._shutdown()
            else:
                panel.reject()

    def test_fem_assembly_animation_updates_three_independent_pipelines(self):
        from unittest.mock import patch
        import FreeCADMbDFEMAnimation as Animation
        import FreeCADMbDFEMResultsPanel as Results

        fem, parts = self._make_fem_animation_model()
        controller = Animation.FEMAnimationController(fem)
        # Explicit state metadata must win over result-list order.
        parts[0].results = list(reversed(parts[0].results))
        controller.set_parts(parts)
        self.assertEqual(controller.states, [0, 1, 2, 3])
        controller.prepare_display("von Mises Stress", True, 1, 3)
        with patch.object(controller.motion, "setFrame", wraps=controller.motion.setFrame) as motion:
            with patch.object(Results, "_ensure_visual_pipeline", wraps=Results._ensure_visual_pipeline) as load:
                controller.show_state(2)
                motion.assert_called_once_with(2)
                self.assertEqual(len(load.call_args_list), 3)
                for body, call in enumerate(load.call_args_list):
                    self.assertIs(call.args[0], parts[body])
                    self.assertEqual(call.args[1].MbDFEMStateIndex, 2)
        visuals = [part.visual for part in parts]
        self.assertEqual(len({visual.Name for visual in visuals}), 3)
        for body, part in enumerate(parts):
            self.assertAlmostEqual(part.Placement.Base.x, 100 * body + 20 * (body + 1))
            self.assertTrue(part.Placement.isSame(part.mbdItem.Placement, 1e-9))
            self.assertTrue(part.visual.Placement.isSame(App.Placement(), 1e-9))
            self.assertTrue(part.visual.getGlobalPlacement().isSame(part.Placement, 1e-9))
            self.assertTrue(part.visual.ViewObject.Visibility)
            self.assertEqual(str(part.visual.ViewObject.Field), "von Mises Stress")
            self.assertAlmostEqual(part.visual.ViewObject.FixedColorBarMinimum, 2e6)
            self.assertAlmostEqual(part.visual.ViewObject.FixedColorBarMaximum, 48e6)
            self.assertFalse(any(result.ViewObject.Visibility for result in part.results))
        controller.show_state(1)
        self.assertEqual([part.visual for part in parts], visuals)
        controller.prepare_display("von Mises Stress", False, 1, 3)
        parts[1].getResultsFolder().ViewObject.Visibility = False
        controller.show_state(3)
        self.assertTrue(parts[0].visual.ViewObject.Visibility)
        self.assertFalse(parts[1].visual.ViewObject.Visibility)
        self.assertTrue(parts[2].visual.ViewObject.Visibility)
        self.assertAlmostEqual(parts[0].visual.ViewObject.FixedColorBarMaximum, 16e6)
        self.assertAlmostEqual(parts[2].visual.ViewObject.FixedColorBarMaximum, 48e6)

    def test_fem_assembly_animation_rejects_missing_and_mismatched_states(self):
        from unittest.mock import patch
        import FreeCADMbDFEMAnimation as Animation

        fem, parts = self._make_fem_animation_model()
        parts[1].results = [result for result in parts[1].results if result.MbDFEMStateIndex != 1]
        controller = Animation.FEMAnimationController(fem)
        controller.set_parts(parts)
        self.assertEqual(controller.states, [0, 2, 3])
        self.assertEqual(controller.interval_states(1, 2), [2])
        with patch.object(controller.motion, "setFrame") as motion:
            with self.assertRaisesRegex(ValueError, "every selected body"):
                controller.show_state(1)
            motion.assert_not_called()
        controller.set_parts([parts[0], parts[2]])
        self.assertEqual(controller.states, [0, 1, 2, 3])
        parts[2].results[2].MbDFEMStateTime = 0.25
        with self.assertRaisesRegex(ValueError, "different simulation time"):
            controller.set_parts(parts)
        parts[2].results[2].MbDFEMStateTime = 0.2
        other = self.document.addObject("MbDFEM::MbDAssembly", "OtherAssembly")
        other_part = self.document.addObject("MbDFEM::MbDPart", "OtherBody")
        other.addPart(other_part)
        parts[2].mbdItem = other_part
        with self.assertRaisesRegex(ValueError, "MbD timeline"):
            controller.set_parts(parts)

    def test_fem_assembly_animation_panel_scrubs_loops_and_stops_together(self):
        from unittest.mock import patch
        import FreeCADMbDFEMAnimation as Animation

        fem, parts = self._make_fem_animation_model()
        panel = Animation.FEMAnimationTaskPanel(fem)
        try:
            self.assertEqual(len(panel.controller.parts), 3)
            panel.first_spin.setValue(0)
            panel.frame_spin.setValue(0)
            panel._toggle_playback(True)
            start = panel._last_tick
            with patch.object(Animation, "monotonic", return_value=start + 2.1 / 30):
                panel._tick()
            self.assertEqual(panel.controller.current_frame, 2)
            self.assertEqual(panel.frame_spin.value(), 2)
            self.assertTrue(panel._playing)
            with patch.object(Animation, "monotonic", return_value=start + 4.1 / 30):
                panel._tick()
            self.assertEqual(panel.controller.current_frame, 0)
            panel.loop_check.setChecked(False)
            with patch.object(Animation, "monotonic", return_value=start + 8.1 / 30):
                panel._tick()
            self.assertEqual(panel.controller.current_frame, 3)
            self.assertFalse(panel._playing)
            self.assertFalse(panel._timer.isActive())
            panel._step(-1)
            self.assertEqual(panel.controller.current_frame, 2)
            parts[2].results = [result for result in parts[2].results if result.MbDFEMStateIndex != 1]
            panel._configure()
            self.assertEqual(panel.controller.states, [0, 2, 3])
            panel.slider.setValue(1)
            self.assertEqual(panel.controller.current_frame, 2)
            panel.body_checks[2][1].setChecked(False)
            self.assertEqual(panel.controller.states, [0, 1, 2, 3])
            for part, check in panel.body_checks:
                check.setChecked(False)
            self.assertFalse(panel.play_button.isEnabled())
            self.assertEqual(panel.controller.states, [])
        finally:
            panel.reject()

    def test_fem_animation_signed_fractional_rate_reverses_and_zero_pauses(self):
        from unittest.mock import patch
        import FreeCADMbDFEMAnimation as Animation

        fem, _ = self._make_fem_animation_model()
        panel = Animation.FEMAnimationTaskPanel(fem)
        try:
            panel.first_spin.setValue(0)
            panel.loop_check.setChecked(False)
            panel.frame_spin.setValue(0)
            panel.rate_spin.setValue(-0.5)
            panel._toggle_playback(True)
            self.assertEqual(panel.controller.current_frame, 3)
            start = panel._last_tick
            with patch.object(Animation, "monotonic", return_value=start + 2.1):
                panel._tick()
            self.assertEqual(panel.controller.current_frame, 2)
            with patch.object(Animation, "monotonic", return_value=start + 6.1):
                panel._tick()
            self.assertEqual(panel.controller.current_frame, 0)
            self.assertFalse(panel._playing)
            panel.rate_spin.setValue(0.5)
            panel._toggle_playback(True)
            self.assertTrue(panel._timer.isActive())
            panel.rate_spin.setValue(0.0)
            self.assertFalse(panel._playing)
            self.assertFalse(panel._timer.isActive())
            panel._toggle_playback(True)
            self.assertFalse(panel._playing)
        finally:
            panel.reject()

    def test_fem_assembly_animation_command_opens_shared_panel(self):
        from unittest.mock import patch
        import FreeCADMbDFEMAnimation as Animation

        fem, parts = self._make_fem_animation_model()
        self.Gui.Selection.clearSelection()
        self.Gui.Selection.addSelection(fem)
        command = Animation.AnimateFEMResultsCommand()
        self.assertIn("MbDFEM_AnimateFEMResults", self.Gui.listCommands())
        self.assertTrue(command.IsActive())
        self.assertIs(command.active_assembly(), fem)
        opened = []
        show = Animation.show_animation_task_panel

        def open_panel(assembly):
            panel = show(assembly)
            opened.append(panel)
            return panel

        try:
            with patch.object(Animation, "show_animation_task_panel", side_effect=open_panel):
                self.Gui.runCommand("MbDFEM_AnimateFEMResults", 0)
            self.assertTrue(self.Gui.Control.activeDialog())
            self.assertEqual(len(opened), 1)
            panel = opened[0]
            self.assertIsInstance(panel, Animation.FEMAnimationTaskPanel)
            self.assertEqual(panel.controller.parts, parts)
            panel._toggle_playback(True)
            self.assertTrue(panel._timer.isActive())
            self.Gui.Control.closeDialog()
            self.assertTrue(panel._closed)
            self.assertFalse(panel._playing)
        finally:
            if self.Gui.Control.activeDialog() is not None:
                self.Gui.Control.closeDialog()

    def test_fem_animation_settings_survive_save_reopen_with_pending_edits(self):
        import FreeCADMbDFEMAnimation as Animation

        fem, parts = self._make_fem_animation_model()
        self.assertEqual(fem.animationParameters.TypeId, "MbDFEM::FEMAnimationParameters")
        self.assertFalse(fem.animationParameters.settingsInitialized)
        panel = Animation.FEMAnimationTaskPanel(fem)
        parameters = fem.animationParameters
        self.assertEqual(parameters.TypeId, "MbDFEM::FEMAnimationParameters")
        self.assertIs(Animation.ensure_animation_parameters(fem), parameters)
        self.assertIn(parameters, fem.Group)
        self.assertIn(parameters, fem.ViewObject.claimChildren())
        selected_names = [parts[0].Name, parts[2].Name]
        try:
            panel.body_checks[1][1].setChecked(False)
            panel.first_spin.setValue(0)
            panel.frame_spin.setValue(1)
            panel.field_combo.setCurrentIndex(panel.field_combo.findData("Displacement Magnitude"))
            panel.shared_check.setChecked(False)
            panel.loop_check.setChecked(False)
            # Save while the task panel is open, without committing the editors first.
            panel.last_spin.lineEdit().setText("2")
            panel.rate_spin.lineEdit().setText("-47.25")
            with tempfile.TemporaryDirectory() as directory:
                filename = str(Path(directory) / "FEMAnimationSettings.FCStd")
                name = fem.Name
                self.document.saveAs(filename)
                self.assertEqual(parameters.endFrame, 2)
                self.assertEqual(parameters.updateRate, -47.25)
                panel.reject()
                self.assertFalse(panel._observing)
                App.closeDocument(self.document.Name)
                self.document = App.openDocument(filename)
                restored = self.document.getObject(name)
                settings = restored.animationParameters
                self.assertEqual(settings.TypeId, "MbDFEM::FEMAnimationParameters")
                self.assertEqual([part.Name for part in settings.selectedParts], selected_names)
                self.assertEqual(settings.currentFrame, 1)
                self.assertEqual(settings.startFrame, 0)
                self.assertEqual(settings.endFrame, 2)
                self.assertEqual(settings.updateRate, -47.25)
                self.assertEqual(settings.fieldName, "Displacement Magnitude")
                self.assertFalse(settings.sharedColorScale)
                self.assertFalse(settings.loop)
                reopened = Animation.FEMAnimationTaskPanel(restored)
                try:
                    self.assertEqual([part.Name for part in reopened.controller.parts], selected_names)
                    self.assertEqual(reopened.frame_spin.value(), 1)
                    self.assertEqual(reopened.first_spin.value(), 0)
                    self.assertEqual(reopened.last_spin.value(), 2)
                    self.assertEqual(reopened.rate_spin.value(), -47.25)
                    self.assertEqual(reopened.field_combo.currentData(), "Displacement Magnitude")
                    self.assertFalse(reopened.shared_check.isChecked())
                    self.assertFalse(reopened.loop_check.isChecked())
                    self.assertFalse(reopened._playing)
                finally:
                    reopened.reject()
        finally:
            if panel._observing:
                panel.reject()

    def test_fem_animation_settings_preserve_empty_selection_and_pending_close_edits(self):
        import FreeCADMbDFEMAnimation as Animation

        fem, parts = self._make_fem_animation_model()
        panel = Animation.FEMAnimationTaskPanel(fem)
        for part, check in panel.body_checks:
            check.setChecked(False)
        panel.first_spin.lineEdit().setText("2")
        panel.rate_spin.lineEdit().setText("61")
        panel.accept()
        self.assertEqual(fem.animationParameters.selectedParts, [])
        self.assertEqual(fem.animationParameters.startFrame, 2)
        self.assertEqual(fem.animationParameters.updateRate, 61)
        reopened = Animation.FEMAnimationTaskPanel(fem)
        try:
            self.assertFalse(any(check.isChecked() for part, check in reopened.body_checks))
            self.assertEqual(reopened.controller.parts, [])
            self.assertFalse(reopened.play_button.isEnabled())
            self.assertEqual(reopened.first_spin.value(), 2)
            self.assertEqual(reopened.rate_spin.value(), 61)
        finally:
            reopened.reject()

    def test_fem_animation_parameters_double_click_opens_owner_panel(self):
        from unittest.mock import patch
        import FreeCADMbDFEMAnimation as Animation

        fem, parts = self._make_fem_animation_model()
        settings = Animation.ensure_animation_parameters(fem)
        self.document.recompute()
        with patch.object(Animation, "show_animation_task_panel") as show:
            self.assertTrue(settings.ViewObject.doubleClicked())
            show.assert_called_once_with(fem)
        self.Gui.Selection.clearSelection()
        self.Gui.Selection.addSelection(settings)
        self.assertIs(Animation.AnimateFEMResultsCommand.active_assembly(), fem)

    def test_fem_animation_observer_detaches_when_document_closes(self):
        import FreeCADMbDFEMAnimation as Animation

        fem, parts = self._make_fem_animation_model()
        panel = Animation.FEMAnimationTaskPanel(fem)
        panel._toggle_playback(True)
        name = self.document.Name
        App.closeDocument(name)
        # Reuse the document name so stale observers would receive its save event.
        self.document = App.newDocument(name)
        self.assertFalse(panel._observing)
        self.assertFalse(panel._playing)
        self.assertFalse(panel._timer.isActive())
        with tempfile.TemporaryDirectory() as directory:
            self.document.saveAs(str(Path(directory) / "Replacement.FCStd"))

    def test_results_task_panel_labels_active_stress_field_with_units(self):
        import FreeCADMbDFEMResultsPanel
        from PySide import QtWidgets

        assembly = self.document.addObject("MbDFEM::MbDAssembly", "Assembly")
        part = self.document.addObject("MbDFEM::MbDPart", "Part")
        fem_part = self.document.addObject("MbDFEM::FEMPart", "FEMPart")
        assembly.addPart(part)
        fem_part.mbdItem = part
        assembly.times = [0.0, 0.25]
        part.xs = [0.0, 1000.0]
        folder = fem_part.ensureResultsFolder()
        self.document.recompute()
        self.Gui.updateGui()

        panel = FreeCADMbDFEMResultsPanel.FEMResultsTaskPanel(folder)
        try:
            self.assertEqual(panel.field_label.text(), "Field: von Mises Stress [Pa]")
        finally:
            panel.reject()

        combo = QtWidgets.QComboBox()
        combo.setObjectName("Field")
        combo.addItems(["None", "Displacement Magnitude", "von Mises Stress"])

        FreeCADMbDFEMResultsPanel._decorate_pipeline_field_combo(combo)

        self.assertEqual(combo.itemText(0), "None")
        self.assertEqual(combo.itemText(1), "Displacement Magnitude [m]")
        self.assertEqual(combo.itemText(2), "von Mises Stress [Pa]")
        combo.setCurrentIndex(2)
        self.assertEqual(
            FreeCADMbDFEMResultsPanel._pipeline_field_combo_value(combo),
            "von Mises Stress",
        )

    def test_results_task_panel_close_saves_pending_spinbox_edits(self):
        import FreeCADMbDFEMResultsPanel

        assembly = self.document.addObject("MbDFEM::MbDAssembly", "Assembly")
        part = self.document.addObject("MbDFEM::MbDPart", "Part")
        fem_part = self.document.addObject("MbDFEM::FEMPart", "FEMPart")
        assembly.addPart(part)
        fem_part.mbdItem = part
        assembly.times = [0.0, 0.25, 0.5, 0.75]
        part.xs = [0.0, 1000.0, 2000.0, 3000.0]
        part.ys = [0.0, 0.0, 0.0, 0.0]
        part.zs = [0.0, 0.0, 0.0, 0.0]
        folder = fem_part.ensureResultsFolder()
        self.document.recompute()
        self.Gui.updateGui()

        panel = FreeCADMbDFEMResultsPanel.FEMResultsTaskPanel(folder)
        panel.state_spin.lineEdit().setText("2")
        panel.start_state_spin.lineEdit().setText("1")
        panel.end_state_spin.lineEdit().setText("3")
        self.assertTrue(panel.reject())

        self.assertEqual(fem_part.MbDFEMResultsPanelCurrentState, 2)
        self.assertEqual(fem_part.MbDFEMResultsPanelStartState, 1)
        self.assertEqual(fem_part.MbDFEMResultsPanelEndState, 3)

        reopened = FreeCADMbDFEMResultsPanel.FEMResultsTaskPanel(folder)
        try:
            self.assertEqual(reopened.state_spin.value(), 2)
            self.assertEqual(reopened.slider.value(), 2)
            self.assertEqual(reopened.start_state_spin.value(), 1)
            self.assertEqual(reopened.end_state_spin.value(), 3)
            self.assertEqual(part.Placement.Base, App.Vector(2000.0, 0.0, 0.0))

            reopened.state_spin.lineEdit().setText("1")
            reopened.start_state_spin.lineEdit().setText("0")
            reopened.end_state_spin.lineEdit().setText("2")
            self.assertTrue(reopened.reject())
            self.assertEqual(fem_part.MbDFEMResultsPanelCurrentState, 1)
            self.assertEqual(fem_part.MbDFEMResultsPanelStartState, 0)
            self.assertEqual(fem_part.MbDFEMResultsPanelEndState, 2)
        finally:
            reopened.reject()

    def test_animation_parameters_open_task_panel_only_on_double_click(self):
        import FreeCADMbDAnimationPanel

        assembly = self.document.addObject("MbDFEM::MbDAssembly", "Assembly")
        animation_parameters = assembly.ensureAnimationParameters()
        self.document.recompute()
        self.Gui.updateGui()

        self.assertEqual(
            animation_parameters.ViewObject.TypeId,
            "MbDFEMGui::ViewProviderMbDAnimationParameters",
        )
        self.assertIs(
            FreeCADMbDAnimationPanel.owning_assembly(animation_parameters),
            assembly,
        )

        self.Gui.Selection.addSelection(animation_parameters)
        self.Gui.updateGui()
        self.assertIsNone(self.Gui.Control.activeDialog())

        self.assertTrue(animation_parameters.ViewObject.doubleClicked())
        dialog = self.Gui.Control.activeDialog()
        try:
            self.assertIsInstance(dialog, FreeCADMbDAnimationPanel.AnimationTaskPanel)
            self.assertIs(dialog.animation_parameters, animation_parameters)
            self.assertIs(dialog.assembly, assembly)
        finally:
            if dialog is not None:
                self.Gui.Control.closeDialog()

    def test_animation_task_panel_accept_saves_pending_spinbox_edits(self):
        import FreeCADMbDAnimationPanel

        assembly = self.document.addObject("MbDFEM::MbDAssembly", "Assembly")
        part = self.document.addObject("MbDFEM::MbDPart", "Part")
        assembly.addPart(part)
        assembly.times = [0.0, 0.25, 0.5, 0.75]
        part.xs = [0.0, 1.0, 2.0, 3.0]
        part.ys = [0.0, 0.0, 0.0, 0.0]
        part.zs = [0.0, 0.0, 0.0, 0.0]
        animation_parameters = assembly.ensureAnimationParameters()
        self.document.recompute()
        self.Gui.updateGui()

        panel = FreeCADMbDAnimationPanel.AnimationTaskPanel(animation_parameters)
        try:
            panel.update_rate_spin.lineEdit().setText("-72.5")
            panel.frame_spin.lineEdit().setText("2")
            panel.start_frame_spin.lineEdit().setText("2")
            panel.end_frame_spin.lineEdit().setText("3")
            panel.scale_spin.lineEdit().setText("4.000")
            panel.loop_check.setChecked(False)

            self.assertTrue(panel.accept())
            self.assertEqual(animation_parameters.updateRate, -72.5)
            self.assertEqual(animation_parameters.currentFrame, 2)
            self.assertEqual(animation_parameters.startFrame, 2)
            self.assertEqual(animation_parameters.endFrame, 3)
            self.assertEqual(animation_parameters.playbackSpeed, -18.125)
            self.assertEqual(animation_parameters.lengthScale, 4.0)
            self.assertEqual(panel.controller.length_scale, 4.0)
            self.assertFalse(animation_parameters.loop)
        finally:
            panel.reject()

        animation_parameters.currentFrame = 3
        panel = FreeCADMbDAnimationPanel.AnimationTaskPanel(animation_parameters)
        try:
            self.assertEqual(panel.frame_spin.value(), 3)
            self.assertEqual(panel.controller.current_frame, 3)
        finally:
            panel.reject()

    def test_animation_task_panel_input_time_and_state_indices(self):
        import FreeCADMbDAnimationPanel
        import FreeCADMbDFEMStateOverlay as Overlay

        assembly = self.document.addObject("MbDFEM::MbDAssembly", "Assembly")
        part = self.document.addObject("MbDFEM::MbDPart", "Part")
        assembly.addPart(part)
        assembly.times = [-sys.float_info.max, 0.0, 1.0]
        for name in ("xs", "ys", "zs"):
            setattr(part, name, [0.0] * 3)
        parameters = assembly.ensureAnimationParameters()
        panel = FreeCADMbDAnimationPanel.AnimationTaskPanel(parameters)
        try:
            self.assertEqual(panel.time_label.text(), "Input")
            self.assertEqual(panel.frame_count_label.text(), "/ 2")
            self.assertTrue(Overlay.state_text(assembly).startswith("State 0 / 2 "))
            panel.first_button.click()
            self.assertEqual(panel.time_label.text(), "0 / 1 s")
            panel.last_button.click()
            self.assertEqual(panel.time_label.text(), "1 / 1 s")
            self.assertTrue(Overlay.state_text(assembly).startswith("State 2 / 2 "))
            panel.input_button.click()
            self.assertEqual(panel.time_label.text(), "Input")
            self.assertEqual(assembly.times[0], -sys.float_info.max)
        finally:
            panel.reject()

    def test_animation_task_panel_play_toggle_and_frame_end_buttons(self):
        import FreeCADMbDAnimationPanel

        assembly = self.document.addObject("MbDFEM::MbDAssembly", "Assembly")
        part = self.document.addObject("MbDFEM::MbDPart", "Part")
        assembly.addPart(part)
        assembly.times = [0.0, 0.25, 0.5, 0.75]
        part.xs = [0.0, 1.0, 2.0, 3.0]
        part.ys = [0.0, 0.0, 0.0, 0.0]
        part.zs = [0.0, 0.0, 0.0, 0.0]
        animation_parameters = assembly.ensureAnimationParameters()
        animation_parameters.startFrame = 1
        animation_parameters.endFrame = 3
        self.document.recompute()
        self.Gui.updateGui()

        panel = FreeCADMbDAnimationPanel.AnimationTaskPanel(animation_parameters)
        try:
            self.assertEqual(panel.play_button.text(), "Play")
            self.assertTrue(panel.play_button.isCheckable())

            panel.play_button.click()
            self.assertTrue(panel.controller.is_playing)
            self.assertTrue(panel.play_button.isChecked())
            self.assertEqual(panel.play_button.text(), "Pause")

            panel.play_button.click()
            self.assertFalse(panel.controller.is_playing)
            self.assertFalse(panel.play_button.isChecked())
            self.assertEqual(panel.play_button.text(), "Play")

            panel.input_button.click()
            self.assertFalse(panel.controller.is_playing)
            self.assertEqual(panel.controller.current_frame, 0)
            self.assertEqual(animation_parameters.currentFrame, 0)

            panel.last_button.click()
            self.assertFalse(panel.controller.is_playing)
            self.assertEqual(panel.controller.current_frame, 3)
            self.assertEqual(animation_parameters.currentFrame, 3)

            panel.first_button.click()
            self.assertFalse(panel.controller.is_playing)
            self.assertEqual(panel.controller.current_frame, 1)
            self.assertEqual(animation_parameters.currentFrame, 1)
        finally:
            panel.reject()

    def test_simulation_parameters_open_task_panel_only_on_double_click(self):
        import FreeCADMbDSimulationPanel

        assembly = self.document.addObject("MbDFEM::MbDAssembly", "Assembly")
        simulation_parameters = assembly.ensureSimulationParameters()
        self.document.recompute()
        self.Gui.updateGui()

        self.assertEqual(
            simulation_parameters.ViewObject.TypeId,
            "MbDFEMGui::ViewProviderMbDSimulationParameters",
        )
        self.assertIs(
            FreeCADMbDSimulationPanel.owning_assembly(simulation_parameters),
            assembly,
        )

        self.Gui.Selection.addSelection(simulation_parameters)
        self.Gui.updateGui()
        self.assertIsNone(self.Gui.Control.activeDialog())

        self.assertTrue(simulation_parameters.ViewObject.doubleClicked())
        dialog = self.Gui.Control.activeDialog()
        try:
            self.assertIsInstance(dialog, FreeCADMbDSimulationPanel.SimulationTaskPanel)
            self.assertIs(dialog.parameters, simulation_parameters)
            self.assertIs(dialog.assembly, assembly)
        finally:
            if dialog is not None:
                self.Gui.Control.closeDialog()

    def test_mass_marker_double_click_opens_task_panel(self):
        import FreeCADMbDMassMarkerPanel

        part = self.document.addObject("MbDFEM::MbDPart", "Part")
        mass_marker = part.ensureMassMarker()
        self.document.recompute()
        self.Gui.updateGui()

        self.assertTrue(mass_marker.ViewObject.doubleClicked())
        dialog = self.Gui.Control.activeDialog()

        try:
            self.assertIsInstance(dialog, FreeCADMbDMassMarkerPanel.MassMarkerTaskPanel)
            self.assertIs(dialog.marker, mass_marker)
        finally:
            if dialog is not None:
                self.Gui.Control.closeDialog()

    def test_part_task_panel_edits_velocity_and_omega(self):
        import FreeCADMbDPartPanel

        part = self.document.addObject("MbDFEM::MbDPart", "Part")
        part.velocity = App.Vector(1, 2, 3)
        part.omega = App.Vector(4, 5, 6)
        self.document.recompute()
        self.Gui.updateGui()

        self.assertTrue(part.ViewObject.doubleClicked())
        dialog = self.Gui.Control.activeDialog()

        try:
            self.assertIsInstance(dialog, FreeCADMbDPartPanel.PartTaskPanel)
            self.assertIs(dialog.part, part)
            dialog.velocity_x.setText("10")
            dialog.velocity_y.setText("20")
            dialog.velocity_z.setText("30")
            dialog.omega_x.setText("40")
            dialog.omega_y.setText("50")
            dialog.omega_z.setText("60")

            self.assertTrue(dialog.accept())
            self.assertEqual(part.velocity, App.Vector(10, 20, 30))
            self.assertEqual(part.omega, App.Vector(40, 50, 60))
        finally:
            if self.Gui.Control.activeDialog() is not None:
                self.Gui.Control.closeDialog()


if __name__ == "__main__":
    sys.exit(unittest.main())
