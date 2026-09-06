# SPDX-License-Identifier: LGPL-2.1-or-later

import os
import math
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

import FreeCAD as App
import MbDFEM  # noqa: F401
import FreeCADMbDAnimation
import FreeCADMbDBackend
import FreeCADMbDExporter
import FreeCADMbDResults
import Part


class MbDFEMAssemblyTest(unittest.TestCase):
    class _MeshNode:
        def __init__(self, x, y, z):
            self.x = x
            self.y = y
            self.z = z

    @staticmethod
    def _load_embedded_module_for_app_test():
        import importlib.util
        import types

        module_names = (
            "femtaskpanels",
            "femtaskpanels.task_material_common",
            "femtaskpanels.task_result_mechanical",
            "femtaskpanels.task_solver_ccxtools",
        )
        original_modules = {name: sys.modules.get(name) for name in module_names}

        class _TaskPanel:
            pass

        femtaskpanels = types.ModuleType("femtaskpanels")
        task_material_common = types.ModuleType("task_material_common")
        task_result_mechanical = types.ModuleType("task_result_mechanical")
        task_solver_ccxtools = types.ModuleType("task_solver_ccxtools")
        task_material_common._TaskPanel = _TaskPanel
        task_result_mechanical._TaskPanel = _TaskPanel
        task_solver_ccxtools._TaskPanel = _TaskPanel
        femtaskpanels.task_material_common = task_material_common
        femtaskpanels.task_result_mechanical = task_result_mechanical
        femtaskpanels.task_solver_ccxtools = task_solver_ccxtools
        sys.modules["femtaskpanels"] = femtaskpanels
        sys.modules["femtaskpanels.task_material_common"] = task_material_common
        sys.modules["femtaskpanels.task_result_mechanical"] = task_result_mechanical
        sys.modules["femtaskpanels.task_solver_ccxtools"] = task_solver_ccxtools

        try:
            embedded_path = Path(__file__).with_name("FreeCADMbDFEMEmbedded.py")
            spec = importlib.util.spec_from_file_location("_MbDFEMEmbeddedAppTest", embedded_path)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            return module
        finally:
            for name, module in original_modules.items():
                if module is None:
                    sys.modules.pop(name, None)
                else:
                    sys.modules[name] = module

    @staticmethod
    def _assembly_folders(assembly):
        return {
            "Assemblies": assembly.getPropertyByName("_assembliesFolder"),
            "FixedParts": assembly.getPropertyByName("_fixedPartsFolder"),
            "Parts": assembly.getPropertyByName("_partsFolder"),
            "Joints": assembly.getPropertyByName("_jointsFolder"),
            "Motions": assembly.getPropertyByName("_motionsFolder"),
            "Actions": assembly.getPropertyByName("_actionsFolder"),
        }

    @staticmethod
    def _part_markers_folder(part):
        return part.getPropertyByName("_markersFolder")

    def test_tree_hierarchy(self):
        document = App.newDocument("MbDFEMTreeTest")

        try:
            assembly = document.addObject("MbDFEM::MbDAssembly", "MbDAssembly1")
            assembly_markers = [
                document.addObject("MbDFEM::MbDMarker", "MbDMarker1"),
                document.addObject("MbDFEM::MbDMarker", "MbDMarker2"),
            ]
            subassemblies = [
                document.addObject("MbDFEM::MbDAssembly", "MbDAssembly2"),
                document.addObject("MbDFEM::MbDAssembly", "MbDAssembly3"),
            ]
            parts = [
                document.addObject("MbDFEM::MbDPart", "MbDPart1"),
                document.addObject("MbDFEM::MbDPart", "MbDPart2"),
            ]
            joints = [
                document.addObject("MbDFEM::MbDJoint", "MbDJoint1"),
                document.addObject("MbDFEM::MbDJoint", "MbDJoint2"),
            ]
            motions = [
                document.addObject("MbDFEM::MbDMotion", "MbDMotion1"),
                document.addObject("MbDFEM::MbDMotion", "MbDMotion2"),
            ]
            actions = [
                document.addObject("MbDFEM::MbDAction", "MbDAction1"),
                document.addObject("MbDFEM::MbDAction", "MbDAction2"),
            ]
            part_markers = [
                [
                    document.addObject("MbDFEM::MbDMarker", "MbDMarker11"),
                    document.addObject("MbDFEM::MbDMarker", "MbDMarker12"),
                ],
                [
                    document.addObject("MbDFEM::MbDMarker", "MbDMarker21"),
                    document.addObject("MbDFEM::MbDMarker", "MbDMarker22"),
                ],
            ]

            for subassembly in subassemblies:
                assembly.addAssembly(subassembly)
            for part, markers in zip(parts, part_markers):
                assembly.addPart(part)
                for marker in markers:
                    part.addMarker(marker)
            for joint in joints:
                assembly.addJoint(joint)
            for motion in motions:
                assembly.addMotion(motion)
            for action in actions:
                assembly.addAction(action)
            joints[0].setMarkers(assembly_markers[0], part_markers[0][0])
            joints[1].setMarkerI(part_markers[0][1])
            joints[1].setMarkerJ(part_markers[1][0])
            motions[0].setMarkers(assembly_markers[0], part_markers[0][1])
            motions[1].setMarkers(assembly_markers[1], part_markers[1][1])
            actions[0].setMarkers(assembly_markers[0], part_markers[1][0])
            actions[1].setMarkers(assembly_markers[1], part_markers[1][1])

            self.assertEqual(assembly.assemblies, subassemblies)
            self.assertEqual(assembly.parts, parts)
            self.assertEqual(assembly.joints, joints)
            self.assertEqual(assembly.motions, motions)
            self.assertEqual(assembly.actions, actions)
            self.assertEqual(joints[0].markerI, assembly_markers[0])
            self.assertEqual(joints[0].markerJ, part_markers[0][0])
            self.assertEqual(joints[1].markerI, part_markers[0][1])
            self.assertEqual(joints[1].markerJ, part_markers[1][0])
            self.assertEqual(motions[0].markerI, assembly_markers[0])
            self.assertEqual(motions[0].markerJ, part_markers[0][1])
            self.assertEqual(actions[0].markerI, assembly_markers[0])
            self.assertEqual(actions[0].markerJ, part_markers[1][0])
            assembly_folders = self._assembly_folders(assembly)
            self.assertEqual(assembly_folders["Assemblies"].Group, subassemblies)
            self.assertEqual(assembly_folders["Parts"].Group, parts)
            self.assertEqual(assembly_folders["FixedParts"].Group, [])
            self.assertEqual(assembly_folders["Joints"].Group, joints)
            self.assertEqual(assembly_folders["Motions"].Group, motions)
            self.assertEqual(assembly_folders["Actions"].Group, actions)

            for part, markers in zip(parts, part_markers):
                self.assertEqual(part.markers, markers)
                self.assertEqual(self._part_markers_folder(part).Group, markers)
                self.assertEqual(part.Group, markers)
                for marker in markers:
                    self.assertEqual(marker.getParentGeoFeatureGroup(), part)
        finally:
            App.closeDocument(document.Name)

    def test_321_constraint_comments_include_node_coordinates(self):
        Embedded = self._load_embedded_module_for_app_test()

        nodes = {
            1: self._MeshNode(0, 0, -20),
            2: self._MeshNode(10, 0, -20),
            3: self._MeshNode(0, 1, -10),
            4: self._MeshNode(0, 4, -19.9),
        }
        fd, inp_file_name = tempfile.mkstemp(suffix=".inp")
        os.close(fd)

        try:
            Path(inp_file_name).write_text("*HEADING\n*STEP\n*END STEP\n", encoding="utf-8")

            constraint_nodes = Embedded._add_321_constraints_to_inp(inp_file_name, nodes)
            content = Path(inp_file_name).read_text(encoding="utf-8")

            self.assertEqual(
                [(label, node_id) for label, node_id, _ in constraint_nodes],
                [("nodeXYZ", 1), ("nodeYZ", 2), ("nodeZ", 4)],
            )
            self.assertIn("** nodeXYZ 1: x=0, y=0, z=-20\n", content)
            self.assertIn("** nodeYZ 2: x=10, y=0, z=-20\n", content)
            self.assertIn("** nodeZ 4: x=0, y=4, z=-19.9\n", content)
            self.assertIn("*BOUNDARY\n1,1,1,0\n1,2,2,0\n1,3,3,0\n", content)
        finally:
            os.remove(inp_file_name)

    def test_calculix_input_includes_mbd_assembly_gravity(self):
        Embedded = self._load_embedded_module_for_app_test()
        document = App.newDocument("MbDFEMCalculixGravityTest")
        fd, inp_file_name = tempfile.mkstemp(suffix=".inp")
        os.close(fd)

        try:
            assembly = document.addObject("MbDFEM::MbDAssembly", "Assembly")
            part = document.addObject("MbDFEM::MbDPart", "Part")
            fem_part = document.addObject("MbDFEM::FEMPart", "FEMPart")
            gravity = assembly.ensureGravity()
            gravity.gravity = App.Vector(0, -9.81, 0)
            assembly.addPart(part)
            fem_part.mbdItem = part
            Path(inp_file_name).write_text("*HEADING\n*STEP\n*END STEP\n", encoding="utf-8")

            self.assertEqual(
                Embedded._add_mbd_gravity_to_inp(inp_file_name, fem_part),
                App.Vector(0, -9.81, 0),
            )
            content = Path(inp_file_name).read_text(encoding="utf-8")

            self.assertIn("** MbDAssembly gravity\n", content)
            self.assertIn("*DLOAD\nEall,GRAV,9810,0,-1,0\n", content)
            self.assertLess(content.index("*DLOAD"), content.index("*END STEP"))

            Embedded._add_mbd_gravity_to_inp(inp_file_name, fem_part)
            self.assertEqual(
                Path(inp_file_name).read_text(encoding="utf-8").count("** MbDAssembly gravity\n"),
                1,
            )
        finally:
            os.remove(inp_file_name)
            App.closeDocument(document.Name)

    def test_calculix_input_transforms_mbd_assembly_gravity_to_mesh_coordinates(self):
        Embedded = self._load_embedded_module_for_app_test()
        document = App.newDocument("MbDFEMCalculixTransformedGravityTest")
        fd, inp_file_name = tempfile.mkstemp(suffix=".inp")
        os.close(fd)

        try:
            assembly = document.addObject("MbDFEM::MbDAssembly", "Assembly")
            part = document.addObject("MbDFEM::MbDPart", "Part")
            fem_part = document.addObject("MbDFEM::FEMPart", "FEMPart")
            gravity = assembly.ensureGravity()
            gravity.gravity = App.Vector(0, 0, -9.81)
            part.Placement = App.Placement(
                App.Vector(),
                App.Rotation(App.Vector(0, 1, 0), 90),
            )
            assembly.addPart(part)
            fem_part.mbdItem = part
            document.recompute()
            Path(inp_file_name).write_text("*HEADING\n*STEP\n*END STEP\n", encoding="utf-8")

            expected = part.getGlobalPlacement().Rotation.inverted().multVec(gravity.gravity)
            actual = Embedded._add_mbd_gravity_to_inp(inp_file_name, fem_part)
            content = Path(inp_file_name).read_text(encoding="utf-8")

            self.assertLess((actual - expected).Length, 1e-7)
            self.assertNotIn("*DLOAD\nEall,GRAV,9810,0,0,-1\n", content)
            self.assertIn(
                "Eall,GRAV,9810,{:.13G},{:.13G},{:.13G}\n".format(
                    expected.x / expected.Length,
                    expected.y / expected.Length,
                    expected.z / expected.Length,
                ),
                content,
            )
        finally:
            os.remove(inp_file_name)
            App.closeDocument(document.Name)

    def test_calculix_input_density_is_injected_for_mbd_grav_loads(self):
        import ObjectsFem

        Embedded = self._load_embedded_module_for_app_test()
        document = App.newDocument("MbDFEMCalculixDensityTest")
        fd, inp_file_name = tempfile.mkstemp(suffix=".inp")
        os.close(fd)

        try:
            assembly = document.addObject("MbDFEM::MbDAssembly", "Assembly")
            part = document.addObject("MbDFEM::MbDPart", "Part")
            fem_part = document.addObject("MbDFEM::FEMPart", "FEMPart")
            material = ObjectsFem.makeMaterialSolid(document, "FEMPart_Material")
            material.Material = {
                "Name": "StaleSteel",
                "YoungsModulus": "210000 MPa",
                "PoissonRatio": "0.3",
                "Density": "1 kg/m^3",
            }
            assembly.addPart(part)
            mass_marker = part.ensureMassMarker()
            mbd_material = mass_marker.material
            mbd_material.setPhysicalValue("Density", "7850 kg/m^3")
            mass_marker.material = mbd_material
            fem_part.mbdItem = part
            fem_part.addObject(material)
            Path(inp_file_name).write_text(
                "*MATERIAL, NAME=FEMPart_Material\n"
                "*ELASTIC\n"
                "210000,0.3\n"
                "*STEP\n"
                "*END STEP\n",
                encoding="utf-8",
            )

            self.assertTrue(Embedded._ensure_mbd_density_in_inp(inp_file_name, fem_part))
            content = Path(inp_file_name).read_text(encoding="utf-8")

            self.assertIn("*DENSITY\n7.85e-09\n", content)
            self.assertLess(content.index("*ELASTIC"), content.index("*DENSITY"))
            self.assertLess(content.index("*DENSITY"), content.index("*STEP"))

            self.assertFalse(Embedded._ensure_mbd_density_in_inp(inp_file_name, fem_part))
            self.assertEqual(
                Path(inp_file_name).read_text(encoding="utf-8").upper().count("*DENSITY"),
                1,
            )
        finally:
            os.remove(inp_file_name)
            App.closeDocument(document.Name)

    def test_calculix_input_ignores_stale_fem_part_material_without_mbd_marker(self):
        import ObjectsFem

        Embedded = self._load_embedded_module_for_app_test()
        document = App.newDocument("MbDFEMCalculixStaleDensityTest")
        fd, inp_file_name = tempfile.mkstemp(suffix=".inp")
        os.close(fd)

        try:
            fem_part = document.addObject("MbDFEM::FEMPart", "FEMPart")
            material = ObjectsFem.makeMaterialSolid(document, "FEMPart_Material")
            material.Material = {
                "Name": "StaleSteel",
                "YoungsModulus": "210000 MPa",
                "PoissonRatio": "0.3",
                "Density": "7850 kg/m^3",
            }
            fem_part.addObject(material)
            Path(inp_file_name).write_text(
                "*MATERIAL, NAME=FEMPart_Material\n"
                "*ELASTIC\n"
                "210000,0.3\n"
                "*STEP\n"
                "*END STEP\n",
                encoding="utf-8",
            )

            self.assertIsNone(Embedded._fem_part_material_object(fem_part, create=False))
            self.assertFalse(Embedded._ensure_mbd_density_in_inp(inp_file_name, fem_part))
            self.assertNotIn("*DENSITY", Path(inp_file_name).read_text(encoding="utf-8"))
        finally:
            os.remove(inp_file_name)
            App.closeDocument(document.Name)

    def test_calculix_input_density_falls_back_to_mbd_mass_marker(self):
        import ObjectsFem

        Embedded = self._load_embedded_module_for_app_test()
        document = App.newDocument("MbDFEMCalculixDensityFallbackTest")
        fd, inp_file_name = tempfile.mkstemp(suffix=".inp")
        os.close(fd)

        try:
            assembly = document.addObject("MbDFEM::MbDAssembly", "Assembly")
            part = document.addObject("MbDFEM::MbDPart", "Part")
            fem_part = document.addObject("MbDFEM::FEMPart", "FEMPart")
            material = ObjectsFem.makeMaterialSolid(document, "FEMPart_Material")
            material.Material = {
                "Name": "NoDensity",
                "YoungsModulus": "210000 MPa",
                "PoissonRatio": "0.3",
            }
            assembly.addPart(part)
            part.ensureMassMarker()
            fem_part.mbdItem = part
            fem_part.addObject(material)
            Path(inp_file_name).write_text(
                "*MATERIAL, NAME=FEMPart_Material\n"
                "*ELASTIC\n"
                "210000,0.3\n"
                "*STEP\n"
                "*END STEP\n",
                encoding="utf-8",
            )

            self.assertTrue(Embedded._ensure_mbd_density_in_inp(inp_file_name, fem_part))
            self.assertIn(
                "*DENSITY\n",
                Path(inp_file_name).read_text(encoding="utf-8"),
            )
        finally:
            os.remove(inp_file_name)
            App.closeDocument(document.Name)

    def test_calculix_input_skips_zero_or_missing_mbd_assembly_gravity(self):
        Embedded = self._load_embedded_module_for_app_test()
        document = App.newDocument("MbDFEMCalculixNoGravityTest")
        fd, inp_file_name = tempfile.mkstemp(suffix=".inp")
        os.close(fd)

        try:
            assembly = document.addObject("MbDFEM::MbDAssembly", "Assembly")
            part = document.addObject("MbDFEM::MbDPart", "Part")
            fem_part = document.addObject("MbDFEM::FEMPart", "FEMPart")
            gravity = assembly.ensureGravity()
            gravity.gravity = App.Vector(0, 0, 0)
            assembly.addPart(part)
            fem_part.mbdItem = part
            Path(inp_file_name).write_text("*HEADING\n*STEP\n*END STEP\n", encoding="utf-8")

            self.assertIsNone(Embedded._add_mbd_gravity_to_inp(inp_file_name, fem_part))
            self.assertNotIn(
                "** MbDAssembly gravity\n",
                Path(inp_file_name).read_text(encoding="utf-8"),
            )

            fem_part.mbdItem = None
            self.assertIsNone(Embedded._add_mbd_gravity_to_inp(inp_file_name, fem_part))
        finally:
            os.remove(inp_file_name)
            App.closeDocument(document.Name)

    def test_calculix_input_includes_mbd_part_dalembert_element_loads(self):
        import Fem

        Embedded = self._load_embedded_module_for_app_test()
        document = App.newDocument("MbDFEMCalculixDalembertTest")
        fd, inp_file_name = tempfile.mkstemp(suffix=".inp")
        os.close(fd)

        try:
            mesh = Fem.FemMesh()
            mesh.addNode(0, 1, 0, 1)
            mesh.addNode(0, -1, 0, 2)
            mesh.addNode(0, 0, 1, 3)
            mesh.addNode(4, 0, -1, 4)
            mesh.addVolume([1, 2, 3, 4], 42)

            mesh_object = document.addObject("Fem::FemMeshObject", "Mesh")
            mesh_object.FemMesh = mesh
            assembly = document.addObject("MbDFEM::MbDAssembly", "Assembly")
            part = document.addObject("MbDFEM::MbDPart", "Part")
            fem_part = document.addObject("MbDFEM::FEMPart", "FEMPart")
            assembly.addPart(part)
            fem_part.mbdItem = part
            fem_part.mesh = mesh_object
            part.alpha = App.Vector(0, 0, 2)
            Path(inp_file_name).write_text("*HEADING\n*STEP\n*END STEP\n", encoding="utf-8")

            loads = Embedded._add_mbd_dalembert_loads_to_inp(inp_file_name, fem_part)
            content = Path(inp_file_name).read_text(encoding="utf-8")

            self.assertEqual(len(loads), 1)
            self.assertEqual(loads[0][0], 42)
            self.assertAlmostEqual(loads[0][1], 0.002)
            self.assertLess(loads[0][2].distanceToPoint(App.Vector(0, -1, 0)), 1e-7)
            self.assertIn("** MbDPart D'Alembert element loads\n", content)
            self.assertIn("*DLOAD\n42,GRAV,2,0,-1", content)
            self.assertLess(content.index("*DLOAD"), content.index("*END STEP"))

            Embedded._add_mbd_dalembert_loads_to_inp(inp_file_name, fem_part)
            self.assertEqual(
                Path(inp_file_name)
                .read_text(encoding="utf-8")
                .count("** MbDPart D'Alembert element loads\n"),
                1,
            )
        finally:
            os.remove(inp_file_name)
            App.closeDocument(document.Name)

    def test_calculix_input_includes_zero_mbd_part_dalembert_element_loads(self):
        import Fem

        Embedded = self._load_embedded_module_for_app_test()
        document = App.newDocument("MbDFEMCalculixNoDalembertTest")
        fd, inp_file_name = tempfile.mkstemp(suffix=".inp")
        os.close(fd)

        try:
            mesh = Fem.FemMesh()
            mesh.addNode(0, 0, 0, 1)
            mesh.addNode(1, 0, 0, 2)
            mesh.addNode(0, 1, 0, 3)
            mesh.addNode(0, 0, 1, 4)
            mesh.addVolume([1, 2, 3, 4], 7)

            mesh_object = document.addObject("Fem::FemMeshObject", "Mesh")
            mesh_object.FemMesh = mesh
            assembly = document.addObject("MbDFEM::MbDAssembly", "Assembly")
            part = document.addObject("MbDFEM::MbDPart", "Part")
            fem_part = document.addObject("MbDFEM::FEMPart", "FEMPart")
            assembly.addPart(part)
            fem_part.mbdItem = part
            fem_part.mesh = mesh_object
            Path(inp_file_name).write_text("*HEADING\n*STEP\n*END STEP\n", encoding="utf-8")

            loads = Embedded._add_mbd_dalembert_loads_to_inp(inp_file_name, fem_part)
            content = Path(inp_file_name).read_text(encoding="utf-8")

            self.assertEqual(len(loads), 1)
            self.assertEqual(loads[0][0], 7)
            self.assertAlmostEqual(loads[0][1], 0.0)
            self.assertLess(loads[0][2].distanceToPoint(App.Vector(1, 0, 0)), 1e-7)
            self.assertIn("** MbDPart D'Alembert element loads\n", content)
            self.assertIn("*DLOAD\n7,GRAV,0,1,0,0\n", content)
        finally:
            os.remove(inp_file_name)
            App.closeDocument(document.Name)

    def test_calculix_input_transforms_mbd_part_dalembert_loads_to_mesh_coordinates(self):
        import Fem

        Embedded = self._load_embedded_module_for_app_test()
        document = App.newDocument("MbDFEMCalculixTransformedDalembertTest")
        fd, inp_file_name = tempfile.mkstemp(suffix=".inp")
        os.close(fd)

        try:
            mesh = Fem.FemMesh()
            mesh.addNode(0, 0, 0, 1)
            mesh.addNode(1, 0, 0, 2)
            mesh.addNode(0, 1, 0, 3)
            mesh.addNode(0, 0, 1, 4)
            mesh.addVolume([1, 2, 3, 4], 7)

            mesh_object = document.addObject("Fem::FemMeshObject", "Mesh")
            mesh_object.FemMesh = mesh
            assembly = document.addObject("MbDFEM::MbDAssembly", "Assembly")
            part = document.addObject("MbDFEM::MbDPart", "Part")
            fem_part = document.addObject("MbDFEM::FEMPart", "FEMPart")
            assembly.addPart(part)
            part.Placement = App.Placement(
                App.Vector(),
                App.Rotation(App.Vector(0, 1, 0), 90),
            )
            part.acceleration = App.Vector(0, 0, -9.81)
            fem_part.mbdItem = part
            fem_part.mesh = mesh_object
            document.recompute()
            Path(inp_file_name).write_text("*HEADING\n*STEP\n*END STEP\n", encoding="utf-8")

            inertial_acceleration = App.Vector(0, 0, 9.81)
            expected = part.getGlobalPlacement().Rotation.inverted().multVec(inertial_acceleration)
            loads = Embedded._add_mbd_dalembert_loads_to_inp(inp_file_name, fem_part)
            content = Path(inp_file_name).read_text(encoding="utf-8")

            self.assertEqual(len(loads), 1)
            self.assertLess(loads[0][2].distanceToPoint(expected / expected.Length), 1e-7)
            self.assertNotIn("*DLOAD\n7,GRAV,9810,0,0,1\n", content)
            self.assertIn(
                "7,GRAV,9810,{:.13G},{:.13G},{:.13G}\n".format(
                    expected.x / expected.Length,
                    expected.y / expected.Length,
                    expected.z / expected.Length,
                ),
                content,
            )
        finally:
            os.remove(inp_file_name)
            App.closeDocument(document.Name)

    def test_calculix_input_uses_applied_mbd_part_acceleration_state(self):
        import Fem
        import FreeCADMbDFEMResultsPanel

        Embedded = self._load_embedded_module_for_app_test()
        document = App.newDocument("MbDFEMCalculixDalembertStateTest")
        fd, inp_file_name = tempfile.mkstemp(suffix=".inp")
        os.close(fd)

        try:
            mesh = Fem.FemMesh()
            mesh.addNode(0, 0, 0, 1)
            mesh.addNode(1, 0, 0, 2)
            mesh.addNode(0, 1, 0, 3)
            mesh.addNode(0, 0, 1, 4)
            mesh.addVolume([1, 2, 3, 4], 7)

            mesh_object = document.addObject("Fem::FemMeshObject", "Mesh")
            mesh_object.FemMesh = mesh
            assembly = document.addObject("MbDFEM::MbDAssembly", "Assembly")
            part = document.addObject("MbDFEM::MbDPart", "Part")
            fem_part = document.addObject("MbDFEM::FEMPart", "FEMPart")
            assembly.addPart(part)
            assembly.times = [0.0, 1.0]
            part.xs = [0.0, 0.0]
            part.ys = [0.0, 0.0]
            part.zs = [0.0, 0.0]
            part.axs = [0.0, 0.0]
            part.ays = [0.0, 0.0]
            part.azs = [0.0, -9.81]
            fem_part.mbdItem = part
            fem_part.mesh = mesh_object

            FreeCADMbDFEMResultsPanel.apply_state(fem_part, 1)
            Path(inp_file_name).write_text("*HEADING\n*STEP\n*END STEP\n", encoding="utf-8")

            loads = Embedded._add_mbd_dalembert_loads_to_inp(inp_file_name, fem_part)
            content = Path(inp_file_name).read_text(encoding="utf-8")

            self.assertEqual(part.acceleration, App.Vector(0, 0, -9.81))
            self.assertEqual(len(loads), 1)
            self.assertAlmostEqual(loads[0][1], 9.81)
            self.assertLess(loads[0][2].distanceToPoint(App.Vector(0, 0, 1)), 1e-7)
            self.assertIn("*DLOAD\n7,GRAV,9810,0,0,1\n", content)
        finally:
            os.remove(inp_file_name)
            App.closeDocument(document.Name)

    def test_fem_part_analysis_adapter_links_results_and_groups_tree_children(self):
        Embedded = self._load_embedded_module_for_app_test()
        document = App.newDocument("MbDFEMResultMeshGroupingTest")

        try:
            fem_part = document.addObject("MbDFEM::FEMPart", "FEMPart")
            result_mesh = document.addObject("Fem::FemMeshObjectPython", "CCX_Results_Mesh")
            result = document.addObject("Fem::FemResultObjectPython", "CCX_Results")
            adapter = Embedded.FEMPartAnalysisAdapter(fem_part)

            adapter.addObject(result_mesh)
            adapter.addObject(result)

            self.assertIn(result_mesh, adapter.Group)
            self.assertIn(result, adapter.Group)
            self.assertNotIn(result_mesh, fem_part.Group)
            self.assertFalse(result_mesh.ViewObject.Visibility)
            self.assertFalse(result_mesh.ViewObject.ShowInTree)
            self.assertEqual(fem_part.results, [result])
            self.assertIn(fem_part.getResultsFolder(), fem_part.Group)
            self.assertIn(result, fem_part.getResultsFolder().Group)
        finally:
            App.closeDocument(document.Name)

    def test_fem_part_analysis_adapter_keeps_result_series_in_order(self):
        Embedded = self._load_embedded_module_for_app_test()
        document = App.newDocument("MbDFEMResultSeriesTest")

        try:
            fem_part = document.addObject("MbDFEM::FEMPart", "FEMPart")
            result_0 = document.addObject("Fem::FemResultObjectPython", "CCX_Results_0")
            result_1 = document.addObject("Fem::FemResultObjectPython", "CCX_Results_1")
            adapter = Embedded.FEMPartAnalysisAdapter(fem_part)

            adapter.addObject(result_0)
            adapter.addObject(result_1)
            adapter.addObject(result_0)

            self.assertEqual(fem_part.results, [result_0, result_1])
            self.assertIn(result_0, adapter.Group)
            self.assertIn(result_1, adapter.Group)
            self.assertEqual(fem_part.getResultsFolder().Group, [result_0, result_1])
        finally:
            App.closeDocument(document.Name)

    def test_fem_part_results_folder_synchronizes_results_series(self):
        document = App.newDocument("MbDFEMResultsFolderTest")

        try:
            fem_part = document.addObject("MbDFEM::FEMPart", "FEMPart")
            result_0 = document.addObject("Fem::FemResultObjectPython", "CCX_Results_0")
            result_1 = document.addObject("Fem::FemResultObjectPython", "CCX_Results_1")

            fem_part.results = [result_0, result_1]

            folder = fem_part.getResultsFolder()
            self.assertIsNotNone(folder)
            self.assertEqual(folder.Label, "Results")
            self.assertIn(folder, fem_part.Group)
            self.assertEqual(folder.Group, [result_0, result_1])
            self.assertIs(fem_part.getSubObject(f"{folder.Name}."), folder)
            self.assertIs(fem_part.getSubObject(f"{result_0.Name}."), result_0)

            folder.removeObject(result_0)

            self.assertEqual(fem_part.results, [result_1])
        finally:
            App.closeDocument(document.Name)

    def test_fem_part_result_series_corresponds_to_mbd_state_index(self):
        document = App.newDocument("MbDFEMResultStateIndexTest")

        try:
            assembly = document.addObject("MbDFEM::MbDAssembly", "Assembly")
            part = document.addObject("MbDFEM::MbDPart", "Part")
            fem_part = document.addObject("MbDFEM::FEMPart", "FEMPart")
            result_0 = document.addObject("Fem::FemResultObjectPython", "CCX_Results_0")
            result_1 = document.addObject("Fem::FemResultObjectPython", "CCX_Results_1")
            assembly.addPart(part)
            fem_part.mbdItem = part
            assembly.times = [0.0, 0.1]
            part.xs = [0.0, 1.0]
            part.ys = [0.0, 2.0]
            part.zs = [0.0, 3.0]
            fem_part.results = [result_0, result_1]

            self.assertIsNone(fem_part.validateResultSeries())
            self.assertIs(fem_part.resultForState(0), result_0)
            self.assertIs(fem_part.resultForState(1), result_1)
        finally:
            App.closeDocument(document.Name)

    def test_fem_part_result_series_rejects_mbd_state_count_mismatch(self):
        document = App.newDocument("MbDFEMResultStateMismatchTest")

        try:
            assembly = document.addObject("MbDFEM::MbDAssembly", "Assembly")
            part = document.addObject("MbDFEM::MbDPart", "Part")
            fem_part = document.addObject("MbDFEM::FEMPart", "FEMPart")
            result_0 = document.addObject("Fem::FemResultObjectPython", "CCX_Results_0")
            result_1 = document.addObject("Fem::FemResultObjectPython", "CCX_Results_1")
            assembly.addPart(part)
            fem_part.mbdItem = part
            assembly.times = [0.0, 0.1, 0.2]
            part.xs = [0.0, 1.0, 2.0]
            fem_part.results = [result_0, result_1]

            with self.assertRaisesRegex(ValueError, "MbDPart.xs has 3 values"):
                fem_part.validateResultSeries()
            with self.assertRaisesRegex(ValueError, "MbDAssembly.times has 3 values"):
                fem_part.resultForState(0)
        finally:
            App.closeDocument(document.Name)

    def test_fem_part_sparse_result_series_uses_state_index_metadata(self):
        document = App.newDocument("MbDFEMSparseResultStateIndexTest")

        try:
            assembly = document.addObject("MbDFEM::MbDAssembly", "Assembly")
            part = document.addObject("MbDFEM::MbDPart", "Part")
            fem_part = document.addObject("MbDFEM::FEMPart", "FEMPart")
            result_2 = document.addObject("Fem::FemResultObjectPython", "CCX_Results_2")
            assembly.addPart(part)
            fem_part.mbdItem = part
            assembly.times = [0.0, 0.1, 0.2]
            part.xs = [0.0, 1.0, 2.0]
            result_2.addProperty(
                "App::PropertyInteger",
                "MbDFEMStateIndex",
                "MbDFEM",
                "MbD time-state index solved by this result",
            )
            result_2.MbDFEMStateIndex = 2
            fem_part.results = [result_2]

            self.assertIsNone(fem_part.validateResultSeries())
            self.assertIs(fem_part.resultForState(2), result_2)
            with self.assertRaisesRegex(IndexError, "not in range"):
                fem_part.resultForState(3)
        finally:
            App.closeDocument(document.Name)

    def test_fem_part_results_skip_stock_overlay_label(self):
        Embedded = self._load_embedded_module_for_app_test()
        document = App.newDocument("MbDFEMResultLabelFallbackTest")

        try:
            import types

            calls = []

            def original_set_label(task_panel, result_name, mesh_data):
                calls.append((task_panel, result_name, mesh_data))

            class _TaskPanel:
                pass

            _TaskPanel.set_label = original_set_label
            femtaskpanels = types.ModuleType("femtaskpanels")
            task_result_mechanical = types.ModuleType("task_result_mechanical")
            task_result_mechanical._TaskPanel = _TaskPanel
            femtaskpanels.task_result_mechanical = task_result_mechanical
            original_modules = {
                name: sys.modules.get(name)
                for name in ("femtaskpanels", "femtaskpanels.task_result_mechanical")
            }
            sys.modules["femtaskpanels"] = femtaskpanels
            sys.modules["femtaskpanels.task_result_mechanical"] = task_result_mechanical
            try:
                Embedded._original_result_set_label = None
                Embedded.install_result_task_panel_label_fallback()
                Embedded.install_result_task_panel_label_fallback()
            finally:
                for name, module in original_modules.items():
                    if module is None:
                        sys.modules.pop(name, None)
                    else:
                        sys.modules[name] = module

            fem_part = document.addObject("MbDFEM::FEMPart", "FEMPart")
            fem_part_result = document.addObject("Fem::FemResultObjectPython", "CCX_Results")
            standalone_result = document.addObject(
                "Fem::FemResultObjectPython", "Standalone_CCX_Results"
            )
            fem_part.results = [fem_part_result]

            fem_part_panel = _TaskPanel()
            fem_part_panel.result_obj = fem_part_result
            standalone_panel = _TaskPanel()
            standalone_panel.result_obj = standalone_result

            task_result_mechanical._TaskPanel.set_label(
                fem_part_panel, "FEMPart result", "Displacement magnitude"
            )
            task_result_mechanical._TaskPanel.set_label(
                standalone_panel, "Standalone result", "Displacement magnitude"
            )

            self.assertEqual(calls, [(standalone_panel, "Standalone result", "Displacement magnitude")])
        finally:
            App.closeDocument(document.Name)

    def test_fem_part_refresh_hides_linked_result_mesh(self):
        Embedded = self._load_embedded_module_for_app_test()
        document = App.newDocument("MbDFEMResultMeshHideRefreshTest")

        try:
            fem_part = document.addObject("MbDFEM::FEMPart", "FEMPart")
            result = document.addObject("Fem::FemResultObjectPython", "CCX_Results")
            result_mesh = document.addObject("Fem::FemMeshObjectPython", "CCX_Results_Mesh")
            result.Mesh = result_mesh
            fem_part.results = [result]
            result_mesh.ViewObject.Visibility = True
            result_mesh.ViewObject.ShowInTree = True

            Embedded.refresh_view_providers(document)

            self.assertFalse(result_mesh.ViewObject.Visibility)
            self.assertFalse(result_mesh.ViewObject.ShowInTree)
        finally:
            App.closeDocument(document.Name)

    def test_create_relationships_save_and_reopen(self):
        with tempfile.TemporaryDirectory() as directory:
            filename = os.path.join(directory, "MbDFEMAssembly.FCStd")
            document = App.newDocument("MbDFEMTest")

            try:
                assembly = document.addObject("MbDFEM::MbDAssembly", "Assembly")
                subassembly = document.addObject("MbDFEM::MbDAssembly", "Subassembly")
                part = document.addObject("MbDFEM::MbDPart", "Part")
                assembly_marker = document.addObject("MbDFEM::MbDMarker", "AssemblyMarker")
                part_marker = document.addObject("MbDFEM::MbDMarker", "PartMarker")
                joint = document.addObject("MbDFEM::MbDJoint", "Joint")
                motion = document.addObject("MbDFEM::MbDMotion", "Motion")
                action = document.addObject("MbDFEM::MbDAction", "Action")

                self.assertEqual(assembly.TypeId, "MbDFEM::MbDAssembly")
                self.assertEqual(subassembly.TypeId, "MbDFEM::MbDAssembly")
                self.assertEqual(part.TypeId, "MbDFEM::MbDPart")
                self.assertEqual(assembly_marker.TypeId, "MbDFEM::MbDMarker")
                self.assertEqual(joint.TypeId, "MbDFEM::MbDJoint")
                self.assertEqual(motion.TypeId, "MbDFEM::MbDMotion")
                self.assertEqual(action.TypeId, "MbDFEM::MbDAction")

                assembly.Placement.Base = App.Vector(1, 2, 3)
                part.Placement.Base = App.Vector(4, 5, 6)
                assembly_marker.Placement.Base = App.Vector(7, 8, 9)
                joint.jointType = "Gear"
                joint.gearRatio = 2.5
                joint.pitchRadius = 12.0
                gravity = assembly.ensureGravity()
                simulation_parameters = assembly.ensureSimulationParameters()
                animation_parameters = assembly.ensureAnimationParameters()
                gravity.gravity = App.Vector(0, -9.81, 0)
                simulation_parameters.endTime = 2.5
                self.assertEqual(animation_parameters.startFrame, 1)
                self.assertEqual(simulation_parameters.maxStepSize, 1.0)
                self.assertEqual(simulation_parameters.minStepSize, 1.0e-09)
                simulation_parameters.maxStepSize = 0.002
                simulation_parameters.minStepSize = 1.0e-10
                simulation_parameters.significantDigits = 8
                simulation_parameters.maxIterations = 250
                simulation_parameters.outputInterval = 0.02
                animation_parameters.updateRate = 60
                animation_parameters.startFrame = 2
                animation_parameters.endFrame = 10
                animation_parameters.playbackSpeed = 0.5
                animation_parameters.loop = False
                animation_parameters.showTrails = True
                animation_parameters.trailLength = 120
                animation_parameters.interpolateFrames = False
                self.assertEqual(joint.jointType, "Gear")
                self.assertEqual(joint.gearRatio, 2.5)
                self.assertEqual(joint.pitchRadius, 12.0)
                self.assertEqual(joint.Label, "Gear MbDJoint")
                self.assertEqual(gravity.TypeId, "MbDFEM::MbDGravity")
                gravity_objects = [
                    obj for obj in document.Objects if obj.TypeId == "MbDFEM::MbDGravity"
                ]
                self.assertEqual(gravity_objects, [gravity])
                self.assertEqual(simulation_parameters.TypeId, "MbDFEM::MbDSimulationParameters")
                self.assertEqual(animation_parameters.TypeId, "MbDFEM::MbDAnimationParameters")
                self.assertIs(assembly.getGravity(), gravity)
                self.assertIs(assembly.getSimulationParameters(), simulation_parameters)
                self.assertIs(assembly.getAnimationParameters(), animation_parameters)
                self.assertIs(assembly.ensureGravity(), gravity)
                self.assertIs(assembly.ensureSimulationParameters(), simulation_parameters)
                self.assertIs(assembly.ensureAnimationParameters(), animation_parameters)

                assembly.addPart(part)
                assembly.addPart(part)
                assembly.addAssembly(subassembly)
                assembly.addAssembly(subassembly)
                assembly.addAssembly(assembly)
                assembly.addJoint(joint)
                assembly.addJoint(joint)
                assembly.addMotion(motion)
                assembly.addMotion(motion)
                assembly.addAction(action)
                assembly.addAction(action)
                joint.setMarkers(assembly_marker, part_marker)
                motion.setMarkerI(assembly_marker)
                motion.setMarkerJ(part_marker)
                action.setMarkers(assembly_marker, part_marker)
                part.addMarker(part_marker)

                self.assertEqual(assembly.parts, [part])
                self.assertEqual(assembly.assemblies, [subassembly])
                self.assertEqual(assembly.joints, [joint])
                self.assertEqual(assembly.motions, [motion])
                self.assertEqual(assembly.actions, [action])
                self.assertEqual(joint.markerI, assembly_marker)
                self.assertEqual(joint.markerJ, part_marker)
                self.assertEqual(motion.markerI, assembly_marker)
                self.assertEqual(motion.markerJ, part_marker)
                self.assertEqual(action.markerI, assembly_marker)
                self.assertEqual(action.markerJ, part_marker)
                self.assertEqual(part.markers, [part_marker])
                self.assertEqual(part.Group, [part_marker])
                self.assertEqual(part_marker.getParentGeoFeatureGroup(), part)
                assembly_folders = self._assembly_folders(assembly)
                self.assertEqual(assembly_folders["Assemblies"].Group, [subassembly])
                self.assertEqual(assembly_folders["Parts"].Group, [part])
                self.assertEqual(assembly_folders["FixedParts"].Group, [])
                self.assertEqual(assembly_folders["Joints"].Group, [joint])
                self.assertEqual(assembly_folders["Motions"].Group, [motion])
                self.assertEqual(assembly_folders["Actions"].Group, [action])
                self.assertEqual(self._part_markers_folder(part).Group, [part_marker])

                with self.assertRaises(TypeError):
                    assembly.addPart(assembly_marker)
                with self.assertRaises(TypeError):
                    assembly.addAssembly(part)
                with self.assertRaises(TypeError):
                    assembly.addJoint(part)
                with self.assertRaises(TypeError):
                    assembly.addMotion(part)
                with self.assertRaises(TypeError):
                    assembly.addAction(part)
                with self.assertRaises(TypeError):
                    joint.setMarkerI(part)
                with self.assertRaises(TypeError):
                    joint.setMarkerJ(part)
                with self.assertRaises(TypeError):
                    joint.setMarkers(part, part_marker)
                with self.assertRaises(TypeError):
                    part.addMarker(part)

                document.saveAs(filename)
                with zipfile.ZipFile(filename) as saved:
                    document_xml = saved.read("Document.xml").decode("utf-8")

                self.assertNotIn('name="_gravity"', document_xml)
                self.assertNotIn('name="_simulationParameters"', document_xml)
                self.assertNotIn('name="_animationParameters"', document_xml)
                self.assertIn('name="gravity" type="App::PropertyLink"', document_xml)
                self.assertIn(
                    'name="simulationParameters" type="App::PropertyLink"',
                    document_xml,
                )
                self.assertIn(
                    'name="animationParameters" type="App::PropertyLink"',
                    document_xml,
                )
            finally:
                App.closeDocument(document.Name)

            reopened = App.openDocument(filename)
            try:
                assembly = reopened.getObject("Assembly")
                subassembly = reopened.getObject("Subassembly")
                part = reopened.getObject("Part")
                assembly_marker = reopened.getObject("AssemblyMarker")
                part_marker = reopened.getObject("PartMarker")
                joint = reopened.getObject("Joint")
                motion = reopened.getObject("Motion")
                action = reopened.getObject("Action")
                gravity = reopened.getObject("Assembly_Gravity")
                simulation_parameters = reopened.getObject("Assembly_SimulationParameters")
                animation_parameters = reopened.getObject("Assembly_AnimationParameters")

                self.assertIsNotNone(assembly)
                self.assertEqual(assembly.TypeId, "MbDFEM::MbDAssembly")
                self.assertEqual(subassembly.TypeId, "MbDFEM::MbDAssembly")
                self.assertEqual(part.TypeId, "MbDFEM::MbDPart")
                self.assertEqual(assembly_marker.TypeId, "MbDFEM::MbDMarker")
                self.assertEqual(joint.TypeId, "MbDFEM::MbDJoint")
                self.assertEqual(joint.jointType, "Gear")
                self.assertEqual(joint.gearRatio, 2.5)
                self.assertEqual(joint.pitchRadius, 12.0)
                self.assertEqual(joint.Label, "Gear MbDJoint")
                self.assertEqual(gravity.TypeId, "MbDFEM::MbDGravity")
                self.assertEqual(simulation_parameters.TypeId, "MbDFEM::MbDSimulationParameters")
                self.assertEqual(animation_parameters.TypeId, "MbDFEM::MbDAnimationParameters")
                self.assertIs(assembly.getGravity(), gravity)
                self.assertIs(assembly.getSimulationParameters(), simulation_parameters)
                self.assertIs(assembly.getAnimationParameters(), animation_parameters)
                self.assertEqual(gravity.Label, "Gravity")
                self.assertEqual(simulation_parameters.Label, "SimulationParameters")
                self.assertEqual(animation_parameters.Label, "AnimationParameters")
                self.assertEqual(gravity.gravity, App.Vector(0, -9.81, 0))
                self.assertEqual(simulation_parameters.endTime, 2.5)
                self.assertEqual(simulation_parameters.maxStepSize, 0.002)
                self.assertEqual(simulation_parameters.minStepSize, 1.0e-10)
                self.assertEqual(simulation_parameters.significantDigits, 8)
                self.assertEqual(simulation_parameters.maxIterations, 250)
                self.assertEqual(simulation_parameters.outputInterval, 0.02)
                self.assertEqual(animation_parameters.updateRate, 60)
                self.assertEqual(animation_parameters.startFrame, 2)
                self.assertEqual(animation_parameters.endFrame, 10)
                self.assertEqual(animation_parameters.playbackSpeed, 0.5)
                self.assertFalse(animation_parameters.loop)
                self.assertTrue(animation_parameters.showTrails)
                self.assertEqual(animation_parameters.trailLength, 120)
                self.assertFalse(animation_parameters.interpolateFrames)
                self.assertEqual(motion.TypeId, "MbDFEM::MbDMotion")
                self.assertEqual(action.TypeId, "MbDFEM::MbDAction")
                self.assertEqual(assembly.Placement.Base, App.Vector(1, 2, 3))
                self.assertEqual(part.Placement.Base, App.Vector(4, 5, 6))
                self.assertEqual(assembly_marker.Placement.Base, App.Vector(7, 8, 9))
                self.assertEqual(assembly.parts, [part])
                self.assertEqual(assembly.assemblies, [subassembly])
                self.assertEqual(assembly.joints, [joint])
                self.assertEqual(assembly.motions, [motion])
                self.assertEqual(assembly.actions, [action])
                self.assertEqual(joint.markerI, assembly_marker)
                self.assertEqual(joint.markerJ, part_marker)
                self.assertEqual(motion.markerI, assembly_marker)
                self.assertEqual(motion.markerJ, part_marker)
                self.assertEqual(action.markerI, assembly_marker)
                self.assertEqual(action.markerJ, part_marker)
                self.assertEqual(part.markers, [part_marker])
                self.assertEqual(part.Group, [part_marker])
                self.assertEqual(part_marker.getParentGeoFeatureGroup(), part)
                assembly_folders = self._assembly_folders(assembly)
                self.assertEqual(assembly_folders["Assemblies"].Group, [subassembly])
                self.assertEqual(assembly_folders["Parts"].Group, [part])
                self.assertEqual(assembly_folders["FixedParts"].Group, [])
                self.assertEqual(assembly_folders["Joints"].Group, [joint])
                self.assertEqual(assembly_folders["Motions"].Group, [motion])
                self.assertEqual(assembly_folders["Actions"].Group, [action])
                self.assertEqual(self._part_markers_folder(part).Group, [part_marker])

            finally:
                App.closeDocument(reopened.Name)

    def test_removing_assembly_removes_owned_parameters(self):
        document = App.newDocument("MbDFEMAssemblyDeleteTest")

        try:
            assembly = document.addObject("MbDFEM::MbDAssembly", "Assembly")
            gravity = assembly.ensureGravity()
            simulation_parameters = assembly.ensureSimulationParameters()
            animation_parameters = assembly.ensureAnimationParameters()
            parameter_names = [
                gravity.Name,
                simulation_parameters.Name,
                animation_parameters.Name,
            ]

            document.removeObject(assembly.Name)

            self.assertIsNone(document.getObject("Assembly"))
            for name in parameter_names:
                self.assertIsNone(document.getObject(name))
        finally:
            App.closeDocument(document.Name)

    def test_part_owns_mass_marker(self):
        with tempfile.TemporaryDirectory() as directory:
            filename = os.path.join(directory, "MbDFEMMassMarker.FCStd")
            document = App.newDocument("MbDFEMMassMarkerTest")

            try:
                part = document.addObject("MbDFEM::MbDPart", "Part")
                mass_marker = part.ensureMassMarker()
                mass_marker.Placement = App.Placement(
                    App.Vector(10, 20, 30),
                    App.Rotation(App.Vector(0, 0, 1), 90),
                )

                self.assertEqual(mass_marker.TypeId, "MbDFEM::MbDMassMarker")
                self.assertTrue(mass_marker.isDerivedFrom("MbDFEM::MbDMarker"))
                self.assertIn("material", mass_marker.PropertiesList)
                self.assertEqual(mass_marker.material.UUID, "92589471-a6cb-4bbc-b748-d425a17dea7d")
                self.assertEqual(mass_marker.material.Name, "CalculiX-Steel")
                self.assertIs(part.getMassMarker(), mass_marker)
                self.assertIs(part.massMarker, mass_marker)
                self.assertEqual(part.markers, [])
                self.assertEqual(part.Group, [mass_marker])
                self.assertEqual(self._part_markers_folder(part).Group, [])
                self.assertEqual(mass_marker.getParentGeoFeatureGroup(), part)
                self.assertIs(part.ensureMassMarker(), mass_marker)

                document.saveAs(filename)
            finally:
                App.closeDocument(document.Name)

            reopened = App.openDocument(filename)
            try:
                part = reopened.getObject("Part")
                mass_marker = reopened.getObject("Part_MassMarker")

                self.assertEqual(mass_marker.TypeId, "MbDFEM::MbDMassMarker")
                self.assertIn("material", mass_marker.PropertiesList)
                self.assertIs(part.getMassMarker(), mass_marker)
                self.assertEqual(part.markers, [])
                self.assertEqual(part.Group, [mass_marker])
                self.assertEqual(self._part_markers_folder(part).Group, [])
                self.assertEqual(mass_marker.Placement.Base, App.Vector(10, 20, 30))
                self.assertTrue(
                    mass_marker.Placement.Rotation.isSame(
                        App.Rotation(App.Vector(0, 0, 1), 90),
                        1.0e-7,
                    )
                )
            finally:
                App.closeDocument(reopened.Name)

    def test_part_populates_mass_marker_from_shape(self):
        document = App.newDocument("MbDFEMMassMarkerShapeTest")

        try:
            part = document.addObject("MbDFEM::MbDPart", "Part")
            part.Shape = Part.makeBox(10, 20, 30)

            marker = part.populateMassMarkerFromShape()

            self.assertEqual(marker.TypeId, "MbDFEM::MbDMassMarker")
            self.assertIs(part.getMassMarker(), marker)
            self.assertTrue(marker.massMarkerFromShape)
            self.assertEqual(part.markers, [])
            self.assertEqual(part.Group, [marker])
            self.assertEqual(self._part_markers_folder(part).Group, [])
            self.assertEqual(marker.Placement.Base, App.Vector(5, 10, 15))
            self.assertAlmostEqual(marker.mass, 6.0e-6)
            self.assertAlmostEqual(marker.principalInertias.x, 2.5e-10)
            self.assertAlmostEqual(marker.principalInertias.y, 5.0e-10)
            self.assertAlmostEqual(marker.principalInertias.z, 6.5e-10)

            matrix = marker.Placement.Rotation.toMatrix()
            columns = [
                App.Vector(matrix.A11, matrix.A21, matrix.A31),
                App.Vector(matrix.A12, matrix.A22, matrix.A32),
                App.Vector(matrix.A13, matrix.A23, matrix.A33),
            ]
            self.assertEqual(
                columns,
                [App.Vector(0, 0, 1), App.Vector(0, 1, 0), App.Vector(-1, 0, 0)],
            )
            self.assertGreater(columns[0].cross(columns[1]).dot(columns[2]), 0.0)

            marker.mass = 42.0
            self.assertFalse(marker.massMarkerFromShape)

            part.populateMassMarkerFromShape()
            self.assertTrue(marker.massMarkerFromShape)
            marker.principalInertias = App.Vector(1, 2, 3)
            self.assertFalse(marker.massMarkerFromShape)

            part.populateMassMarkerFromShape()
            material = marker.material
            material.setPhysicalValue("Density", "2e-09 kg/mm^3")
            marker.material = material
            self.assertTrue(marker.massMarkerFromShape)
            self.assertAlmostEqual(marker.mass, 1.2e-5)
            self.assertAlmostEqual(marker.principalInertias.x, 5.0e-10)
            self.assertAlmostEqual(marker.principalInertias.y, 1.0e-9)
            self.assertAlmostEqual(marker.principalInertias.z, 1.3e-9)
        finally:
            App.closeDocument(document.Name)

    def test_part_auto_populates_mass_marker_when_shape_is_first_assigned(self):
        document = App.newDocument("MbDFEMMassMarkerAutoShapeTest")

        try:
            part = document.addObject("MbDFEM::MbDPart", "Part")
            self.assertIsNone(part.getMassMarker())

            part.Shape = Part.makeBox(10, 20, 30)

            marker = part.getMassMarker()
            self.assertIsNotNone(marker)
            self.assertEqual(marker.TypeId, "MbDFEM::MbDMassMarker")
            self.assertTrue(marker.massMarkerFromShape)
            self.assertEqual(marker.Placement.Base, App.Vector(5, 10, 15))
            self.assertAlmostEqual(marker.mass, 6.0e-6)
            self.assertAlmostEqual(marker.principalInertias.x, 2.5e-10)
            self.assertAlmostEqual(marker.principalInertias.y, 5.0e-10)
            self.assertAlmostEqual(marker.principalInertias.z, 6.5e-10)
            self.assertEqual(part.markers, [])
            self.assertEqual(part.Group, [marker])
        finally:
            App.closeDocument(document.Name)

    def test_transformed_part_auto_populates_mass_marker_in_local_coordinates(self):
        document = App.newDocument("MbDFEMMassMarkerTransformedPartTest")

        try:
            part = document.addObject("MbDFEM::MbDPart", "Part")
            part.Placement = App.Placement(
                App.Vector(10, 0, 0),
                App.Rotation(App.Vector(0, 1, 0), 40),
            )
            part.Shape = Part.makeBox(10, 20, 30)

            marker = part.getMassMarker()

            self.assertIsNotNone(marker)
            self.assertTrue(marker.massMarkerFromShape)
            self.assertLess((marker.Placement.Base - App.Vector(5, 10, 15)).Length, 1e-9)
            self.assertEqual(part.Placement.multVec(marker.Placement.Base),
                             part.Placement.multVec(App.Vector(5, 10, 15)))
        finally:
            App.closeDocument(document.Name)

    def test_restored_default_mass_marker_properties_repopulate_from_shape(self):
        with tempfile.TemporaryDirectory() as directory:
            filename = os.path.join(directory, "MbDFEMDefaultMassMarker.FCStd")
            document = App.newDocument("MbDFEMDefaultMassMarkerRestoreTest")

            try:
                part = document.addObject("MbDFEM::MbDPart", "Part")
                part.Shape = Part.makeBox(10, 20, 30)
                marker = part.getMassMarker()
                marker.mass = 1.0
                marker.principalInertias = App.Vector(1, 1, 1)
                self.assertFalse(marker.massMarkerFromShape)
                document.saveAs(filename)
            finally:
                App.closeDocument(document.Name)

            reopened = App.openDocument(filename)
            try:
                part = reopened.getObject("Part")
                marker = part.getMassMarker()

                self.assertTrue(marker.massMarkerFromShape)
                self.assertAlmostEqual(marker.mass, 6.0e-6)
                self.assertAlmostEqual(marker.principalInertias.x, 2.5e-10)
                self.assertAlmostEqual(marker.principalInertias.y, 5.0e-10)
                self.assertAlmostEqual(marker.principalInertias.z, 6.5e-10)
            finally:
                App.closeDocument(reopened.Name)

    def test_part_populates_mass_marker_in_part_coordinates(self):
        document = App.newDocument("MbDFEMMassMarkerLocalFrameTest")

        try:
            part = document.addObject("MbDFEM::MbDPart", "Part")
            shape = Part.makeBox(10, 20, 30)
            shape.Placement = App.Placement(
                App.Vector(100, 200, 300),
                App.Rotation(App.Vector(0, 0, 1), 90),
            )

            part.Shape = shape
            marker = part.getMassMarker()

            self.assertIsNotNone(marker)
            self.assertTrue(marker.massMarkerFromShape)
            self.assertTrue(
                part.Placement.isSame(
                    App.Placement(
                        App.Vector(100, 200, 300),
                        App.Rotation(App.Vector(0, 0, 1), 90),
                    ),
                    1.0e-7,
                )
            )
            self.assertEqual(marker.Placement.Base, App.Vector(5, 10, 15))
            self.assertEqual(part.Placement.multVec(marker.Placement.Base), shape.CenterOfMass)
        finally:
            App.closeDocument(document.Name)

    def test_restored_part_with_placed_shape_keeps_mass_marker_local(self):
        with tempfile.TemporaryDirectory() as directory:
            filename = os.path.join(directory, "MbDFEMPlacedShapeMassMarker.FCStd")
            document = App.newDocument("MbDFEMPlacedShapeMassMarkerTest")

            placement = App.Placement(
                App.Vector(100, 200, 300),
                App.Rotation(App.Vector(0, 0, 1), 90),
            )

            try:
                part = document.addObject("MbDFEM::MbDPart", "Part")
                part.Placement = placement
                shape = Part.makeBox(10, 20, 30)
                shape.Placement = placement
                part.Shape = shape

                marker = part.getMassMarker()
                self.assertIsNotNone(marker)
                self.assertTrue(marker.massMarkerFromShape)
                self.assertLess((marker.Placement.Base - App.Vector(5, 10, 15)).Length, 1e-9)

                document.saveAs(filename)
            finally:
                App.closeDocument(document.Name)

            reopened = App.openDocument(filename)
            try:
                part = reopened.getObject("Part")
                marker = part.getMassMarker()

                self.assertIsNotNone(marker)
                self.assertTrue(marker.massMarkerFromShape)
                self.assertTrue(part.Placement.isSame(placement, 1.0e-7))
                self.assertLess((marker.Placement.Base - App.Vector(5, 10, 15)).Length, 1e-9)
                self.assertLess(
                    (part.Placement.multVec(marker.Placement.Base)
                     - part.Shape.BoundBox.Center).Length,
                    1e-9,
                )
            finally:
                App.closeDocument(reopened.Name)

    def test_ground_part_moves_part_to_fixedparts(self):
        document = App.newDocument("MbDFEMGroundPartTest")

        try:
            assembly = document.addObject("MbDFEM::MbDAssembly", "Assembly")
            part = document.addObject("MbDFEM::MbDPart", "Part")

            assembly.addPart(part)
            self.assertEqual(assembly.parts, [part])
            self.assertEqual(assembly.fixedparts, [])
            self.assertEqual(assembly.getPartsFolder().Group, [part])
            self.assertIn(part, assembly.Group)
            self.assertEqual(part.getParentGeoFeatureGroup(), assembly)

            assembly.groundPart(part)
            self.assertEqual(assembly.parts, [])
            self.assertEqual(assembly.fixedparts, [part])
            self.assertEqual(assembly.getPartsFolder().Group, [])
            self.assertEqual(assembly.getFixedPartsFolder().Group, [part])
            self.assertIn(part, assembly.Group)
            self.assertEqual(part.getParentGeoFeatureGroup(), assembly)
            self.assertIs(document.getObject("Part"), part)
        finally:
            App.closeDocument(document.Name)

    def test_joint_type_updates_auto_label_but_preserves_custom_label(self):
        document = App.newDocument("MbDFEMJointLabelTest")

        try:
            joint = document.addObject("MbDFEM::MbDJoint", "Joint")
            joint.Label = "MbDJoint (A, B)"
            joint.jointType = "Revolute"
            self.assertEqual(joint.Label, "Revolute MbDJoint")

            joint.jointType = "RackPinion"
            self.assertEqual(joint.Label, "RackPinion MbDJoint")

            joint.Label = "Drive coupling"
            joint.jointType = "Gear"
            self.assertEqual(joint.Label, "Drive coupling")
        finally:
            App.closeDocument(document.Name)

    def test_tree_folder_subobject_paths_resolve_to_contained_objects(self):
        document = App.newDocument("MbDFEMFolderSubobjectPathTest")

        try:
            assembly = document.addObject("MbDFEM::MbDAssembly", "Assembly")
            part = document.addObject("MbDFEM::MbDPart", "Part")
            fixed_part = document.addObject("MbDFEM::MbDPart", "FixedPart")
            marker = document.addObject("MbDFEM::MbDMarker", "Marker")
            gravity = assembly.ensureGravity()
            simulation_parameters = assembly.ensureSimulationParameters()
            animation_parameters = assembly.ensureAnimationParameters()

            fixed_part.Shape = Part.makeBox(1, 1, 1)
            assembly.addPart(part)
            assembly.addFixedPart(fixed_part)
            part.addMarker(marker)

            part_path = f"{assembly.getPartsFolder().Name}.{part.Name}."
            fixed_part_path = f"{fixed_part.Name}."
            fixed_part_edge_path = f"{fixed_part.Name}.Edge1"
            fixed_part_face_path = f"{fixed_part.Name}.Face1"
            marker_path = f"{part.getMarkersFolder().Name}.{marker.Name}."
            gravity_path = f"{gravity.Name}."
            simulation_path = f"{simulation_parameters.Name}."
            animation_path = f"{animation_parameters.Name}."

            self.assertIs(assembly.getSubObject(part_path, retType=1), part)
            self.assertIs(assembly.getSubObject(fixed_part_path, retType=1), fixed_part)
            self.assertIs(assembly.getSubObject(fixed_part_edge_path, retType=1), fixed_part)
            self.assertIsNotNone(assembly.getSubObject(fixed_part_edge_path))
            self.assertIs(assembly.getSubObject(fixed_part_face_path, retType=1), fixed_part)
            self.assertIsNotNone(assembly.getSubObject(fixed_part_face_path))
            self.assertIs(part.getSubObject(marker_path, retType=1), marker)
            self.assertIs(assembly.getSubObject(gravity_path, retType=1), gravity)
            self.assertIs(assembly.getSubObject(simulation_path, retType=1), simulation_parameters)
            self.assertIs(assembly.getSubObject(animation_path, retType=1), animation_parameters)
        finally:
            App.closeDocument(document.Name)

    def test_fem_tree_folder_subobject_paths_resolve_to_contained_objects(self):
        document = App.newDocument("MbDFEMFEMFolderSubobjectPathTest")

        try:
            assembly = document.addObject("MbDFEM::FEMAssembly", "FEMAssembly")
            part = document.addObject("MbDFEM::FEMPart", "FEMPart")
            joint = document.addObject("MbDFEM::FEMJoint", "FEMJoint")
            motion = document.addObject("MbDFEM::FEMJoint", "FEMMotion")
            action = document.addObject("MbDFEM::FEMAction", "FEMAction")

            assembly.ensureCategoryFolders()
            assembly.getPartsFolder().addObject(part)
            assembly.getJointsFolder().addObject(joint)
            assembly.getMotionsFolder().addObject(motion)
            assembly.getActionsFolder().addObject(action)

            part_path = f"{assembly.getPartsFolder().Name}.{part.Name}."
            joint_path = f"{assembly.getJointsFolder().Name}.{joint.Name}."
            motion_path = f"{assembly.getMotionsFolder().Name}.{motion.Name}."
            action_path = f"{assembly.getActionsFolder().Name}.{action.Name}."

            self.assertIs(assembly.getSubObject(part_path, retType=1), part)
            self.assertIs(assembly.getSubObject(f"{part.Name}.", retType=1), part)
            self.assertIs(assembly.getSubObject(joint_path, retType=1), joint)
            self.assertIs(assembly.getSubObject(f"{joint.Name}.", retType=1), joint)
            self.assertIs(assembly.getSubObject(motion_path, retType=1), motion)
            self.assertIs(assembly.getSubObject(f"{motion.Name}.", retType=1), motion)
            self.assertIs(assembly.getSubObject(action_path, retType=1), action)
            self.assertIs(assembly.getSubObject(f"{action.Name}.", retType=1), action)
        finally:
            App.closeDocument(document.Name)

    def test_child_element_visibility_maps_to_contained_objects(self):
        document = App.newDocument("MbDFEMElementVisibilityTest")

        try:
            assembly = document.addObject("MbDFEM::MbDAssembly", "Assembly")
            part = document.addObject("MbDFEM::MbDPart", "Pin_MbDPart")
            marker = document.addObject("MbDFEM::MbDMarker", "Marker")
            part.Label = "Pin001"
            marker.Label = "Marker001"

            assembly.addPart(part)
            part.addMarker(marker)

            self.assertEqual(assembly.isElementVisible("Pin_MbDPart"), 1)
            self.assertEqual(assembly.isElementVisible("Pin001"), -1)
            self.assertEqual(part.isElementVisible("Marker"), 1)
            self.assertEqual(part.isElementVisible("Marker001"), -1)

            self.assertEqual(assembly.setElementVisible("Pin_MbDPart", False), 0)
            self.assertFalse(part.Visibility)
            self.assertEqual(assembly.isElementVisible("Pin_MbDPart"), 0)
            self.assertEqual(assembly.setElementVisible("Pin001", True), -1)
            self.assertFalse(part.Visibility)
            self.assertEqual(assembly.setElementVisible("Pin_MbDPart", True), 1)
            self.assertTrue(part.Visibility)

            self.assertEqual(part.setElementVisible("Marker", False), 0)
            self.assertFalse(marker.Visibility)
            self.assertEqual(part.isElementVisible("Marker001"), -1)
            self.assertEqual(part.setElementVisible("Marker001", True), -1)
            self.assertFalse(marker.Visibility)
            self.assertEqual(part.setElementVisible("Marker", True), 1)
            self.assertTrue(marker.Visibility)
        finally:
            App.closeDocument(document.Name)

    def test_duplicate_labels_do_not_affect_internal_name_resolution(self):
        document = App.newDocument("MbDFEMDuplicateLabelTest")

        try:
            assembly = document.addObject("MbDFEM::MbDAssembly", "Assembly")
            first_part = document.addObject("MbDFEM::MbDPart", "FirstPart")
            second_part = document.addObject("MbDFEM::MbDPart", "SecondPart")
            first_marker = document.addObject("MbDFEM::MbDMarker", "FirstMarker")
            second_marker = document.addObject("MbDFEM::MbDMarker", "SecondMarker")

            first_part.Label = "Pin"
            second_part.Label = "Pin"
            first_marker.Label = "JointMarker"
            second_marker.Label = "JointMarker"

            assembly.addPart(first_part)
            assembly.addPart(second_part)
            first_part.addMarker(first_marker)
            second_part.addMarker(second_marker)

            self.assertEqual(assembly.setElementVisible("FirstPart", False), 0)
            self.assertFalse(first_part.Visibility)
            self.assertTrue(second_part.Visibility)
            self.assertEqual(assembly.setElementVisible("Pin", True), -1)
            self.assertFalse(first_part.Visibility)
            self.assertTrue(second_part.Visibility)

            self.assertEqual(second_part.setElementVisible("SecondMarker", False), 0)
            self.assertTrue(first_marker.Visibility)
            self.assertFalse(second_marker.Visibility)
            self.assertEqual(second_part.setElementVisible("JointMarker", True), -1)
            self.assertTrue(first_marker.Visibility)
            self.assertFalse(second_marker.Visibility)
        finally:
            App.closeDocument(document.Name)

    def test_assembly_placement_defines_parts_local_coordinate_system(self):
        document = App.newDocument("MbDFEMAssemblyPlacementTest")

        try:
            assembly = document.addObject("MbDFEM::MbDAssembly", "Assembly")
            part = document.addObject("MbDFEM::MbDPart", "Part")
            fixed_part = document.addObject("MbDFEM::MbDPart", "FixedPart")

            part.Placement.Base = App.Vector(1, 0, 0)
            fixed_part.Placement.Base = App.Vector(0, 2, 0)
            assembly.addPart(part)
            assembly.addFixedPart(fixed_part)
            self.assertIn(part, assembly.Group)
            self.assertIn(fixed_part, assembly.Group)
            self.assertEqual(part.getParentGeoFeatureGroup(), assembly)
            self.assertEqual(fixed_part.getParentGeoFeatureGroup(), assembly)

            assembly.Placement.Base = App.Vector(10, 0, 0)
            self.assertEqual(part.Placement.Base, App.Vector(1, 0, 0))
            self.assertEqual(fixed_part.Placement.Base, App.Vector(0, 2, 0))
            self.assertEqual(assembly.getPlacementOf("Part.", part).Base, App.Vector(11, 0, 0))
            self.assertEqual(
                assembly.getPlacementOf("FixedPart.", fixed_part).Base,
                App.Vector(10, 2, 0),
            )

            assembly.Placement = App.Placement(
                App.Vector(0, 0, 0),
                App.Rotation(App.Vector(0, 0, 1), 90),
            )
            self.assertEqual(part.Placement.Base, App.Vector(1, 0, 0))
            self.assertEqual(fixed_part.Placement.Base, App.Vector(0, 2, 0))
            self.assertLess(
                assembly.getPlacementOf("Part.", part).Base.distanceToPoint(App.Vector(0, 1, 0)),
                1e-7,
            )
            self.assertLess(
                assembly.getPlacementOf("FixedPart.", fixed_part).Base.distanceToPoint(
                    App.Vector(-2, 0, 0)
                ),
                1e-7,
            )
        finally:
            App.closeDocument(document.Name)

    def test_part_placement_defines_marker_local_coordinate_system(self):
        document = App.newDocument("MbDFEMPartPlacementTest")

        try:
            part = document.addObject("MbDFEM::MbDPart", "Part")
            marker = document.addObject("MbDFEM::MbDMarker", "Marker")

            marker.Placement.Base = App.Vector(1, 0, 0)
            part.addMarker(marker)

            self.assertEqual(part.markers, [marker])
            self.assertEqual(part.getMarkersFolder().Group, [marker])
            self.assertEqual(part.Group, [marker])
            self.assertEqual(marker.getParentGeoFeatureGroup(), part)

            part.Placement.Base = App.Vector(10, 0, 0)
            self.assertEqual(marker.Placement.Base, App.Vector(1, 0, 0))
            self.assertEqual(part.getPlacementOf("Marker.", marker).Base, App.Vector(11, 0, 0))

            part.Placement = App.Placement(
                App.Vector(0, 0, 0),
                App.Rotation(App.Vector(0, 0, 1), 90),
            )
            self.assertEqual(marker.Placement.Base, App.Vector(1, 0, 0))
            self.assertLess(
                part.getPlacementOf("Marker.", marker).Base.distanceToPoint(App.Vector(0, 1, 0)),
                1e-7,
            )
        finally:
            App.closeDocument(document.Name)

    def test_part_global_position_of_local_point(self):
        document = App.newDocument("MbDFEMPartGlobalPositionTest")

        try:
            assembly = document.addObject("MbDFEM::MbDAssembly", "Assembly")
            part = document.addObject("MbDFEM::MbDPart", "Part")
            assembly.addPart(part)

            assembly.Placement = App.Placement(
                App.Vector(10, 20, 30),
                App.Rotation(App.Vector(0, 0, 1), 90),
            )
            part.Placement = App.Placement(
                App.Vector(1, 2, 3),
                App.Rotation(App.Vector(0, 1, 0), 180),
            )

            point = App.Vector(4, 5, 6)
            expected = part.getGlobalPlacement().multVec(point)
            actual = part.globalPositionOf(point)

            self.assertLess(actual.distanceToPoint(expected), 1e-7)
        finally:
            App.closeDocument(document.Name)

    def test_part_global_velocity_of_local_point(self):
        document = App.newDocument("MbDFEMPartGlobalVelocityTest")

        try:
            assembly = document.addObject("MbDFEM::MbDAssembly", "Assembly")
            part = document.addObject("MbDFEM::MbDPart", "Part")
            assembly.addPart(part)

            assembly.Placement = App.Placement(
                App.Vector(10, 20, 30),
                App.Rotation(App.Vector(0, 0, 1), 90),
            )
            part.Placement = App.Placement(
                App.Vector(1, 2, 3),
                App.Rotation(App.Vector(0, 1, 0), 180),
            )
            part.velocity = App.Vector(1, 2, 3)
            part.omega = App.Vector(0, 0, 2)

            point = App.Vector(4, 5, 6)
            radius = part.getGlobalPlacement().Rotation.multVec(point)
            expected = part.velocity + part.omega.cross(radius)
            actual = part.globalVelocityOf(point)

            self.assertLess(actual.distanceToPoint(expected), 1e-7)
        finally:
            App.closeDocument(document.Name)

    def test_part_global_acceleration_of_local_point(self):
        document = App.newDocument("MbDFEMPartGlobalAccelerationTest")

        try:
            assembly = document.addObject("MbDFEM::MbDAssembly", "Assembly")
            part = document.addObject("MbDFEM::MbDPart", "Part")
            assembly.addPart(part)

            assembly.Placement = App.Placement(
                App.Vector(10, 20, 30),
                App.Rotation(App.Vector(0, 0, 1), 90),
            )
            part.Placement = App.Placement(
                App.Vector(1, 2, 3),
                App.Rotation(App.Vector(0, 1, 0), 180),
            )
            part.acceleration = App.Vector(1, 2, 3)
            part.alpha = App.Vector(0, 0, 4)
            part.omega = App.Vector(0, 0, 2)

            point = App.Vector(4, 5, 6)
            radius = part.getGlobalPlacement().Rotation.multVec(point)
            expected = (
                part.acceleration
                + part.alpha.cross(radius)
                + part.omega.cross(part.omega.cross(radius))
            )
            actual = part.globalAccelerationOf(point)

            self.assertLess(actual.distanceToPoint(expected), 1e-7)
        finally:
            App.closeDocument(document.Name)

    def test_fem_part_element_centroid_uses_linked_mesh_and_mbd_part_transform(self):
        import Fem

        document = App.newDocument("MbDFEMElementCentroidTest")

        try:
            mesh = Fem.FemMesh()
            mesh.addNode(0, 0, 0, 1)
            mesh.addNode(4, 0, 0, 2)
            mesh.addNode(0, 8, 0, 3)
            mesh.addNode(0, 0, 12, 4)
            element_id = 42
            mesh.addVolume([1, 2, 3, 4], element_id)

            mesh_object = document.addObject("Fem::FemMeshObject", "Mesh")
            mesh_object.FemMesh = mesh
            part = document.addObject("MbDFEM::MbDPart", "Part")
            fem_part = document.addObject("MbDFEM::FEMPart", "FEMPart")
            fem_part.mesh = mesh_object
            fem_part.mbdItem = part
            part.Placement = App.Placement(
                App.Vector(10, 20, 30),
                App.Rotation(App.Vector(0, 0, 1), 90),
            )

            expected_local = App.Vector(1, 2, 3)
            actual_local = fem_part.elementCentroidLocal(element_id)
            actual_global = fem_part.elementCentroidGlobal(element_id)

            self.assertLess(actual_local.distanceToPoint(expected_local), 1e-7)
            self.assertLess(
                actual_global.distanceToPoint(part.globalPositionOf(expected_local)),
                1e-7,
            )
        finally:
            App.closeDocument(document.Name)

    def test_part_placement_does_not_transform_shape_coordinates(self):
        document = App.newDocument("MbDFEMPartShapePlacementTest")

        try:
            part = document.addObject("MbDFEM::MbDPart", "Part")
            part.Shape = Part.makeCylinder(8, 20)
            document.recompute()

            part.Placement = App.Placement(
                App.Vector(10, 0, 0),
                App.Rotation(App.Vector(0, 1, 0), 40),
            )
            document.recompute()

            self.assertLess(part.Shape.Placement.Base.Length, 1e-9)
            self.assertLess(abs(part.Shape.Placement.Rotation.Angle), 1e-9)
        finally:
            App.closeDocument(document.Name)

    def test_reparent_part_between_assemblies_removes_old_semantic_links(self):
        document = App.newDocument("MbDFEMPartReparentTest")

        try:
            first_assembly = document.addObject("MbDFEM::MbDAssembly", "FirstAssembly")
            second_assembly = document.addObject("MbDFEM::MbDAssembly", "SecondAssembly")
            part = document.addObject("MbDFEM::MbDPart", "Part")

            first_assembly.addPart(part)
            self.assertEqual(first_assembly.parts, [part])
            self.assertEqual(first_assembly.getPartsFolder().Group, [part])
            self.assertIn(part, first_assembly.Group)
            self.assertEqual(part.getParentGeoFeatureGroup(), first_assembly)

            second_assembly.addPart(part)

            self.assertEqual(first_assembly.parts, [])
            self.assertEqual(first_assembly.getPartsFolder().Group, [])
            self.assertNotIn(part, first_assembly.Group)
            self.assertEqual(second_assembly.parts, [part])
            self.assertEqual(second_assembly.getPartsFolder().Group, [part])
            self.assertIn(part, second_assembly.Group)
            self.assertEqual(part.getParentGeoFeatureGroup(), second_assembly)
        finally:
            App.closeDocument(document.Name)

    def test_reparent_marker_removes_old_part_semantic_links(self):
        document = App.newDocument("MbDFEMMarkerReparentTest")

        try:
            first_part = document.addObject("MbDFEM::MbDPart", "FirstPart")
            second_part = document.addObject("MbDFEM::MbDPart", "SecondPart")
            marker = document.addObject("MbDFEM::MbDMarker", "Marker")

            first_part.addMarker(marker)
            second_part.addMarker(marker)

            self.assertEqual(first_part.markers, [])
            self.assertEqual(first_part.getMarkersFolder().Group, [])
            self.assertNotIn(marker, first_part.Group)
            self.assertEqual(second_part.markers, [marker])
            self.assertEqual(second_part.getMarkersFolder().Group, [marker])
            self.assertEqual(marker.getParentGeoFeatureGroup(), second_part)
        finally:
            App.closeDocument(document.Name)

    def test_deleting_part_deletes_owned_markers(self):
        document = App.newDocument("MbDFEMDeletePartTest")

        try:
            assembly = document.addObject("MbDFEM::MbDAssembly", "Assembly")
            part = document.addObject("MbDFEM::MbDPart", "Part")
            marker = document.addObject("MbDFEM::MbDMarker", "Marker")

            assembly.addPart(part)
            part.addMarker(marker)
            marker_folder_name = part.getMarkersFolder().Name

            document.removeObject(part.Name)

            self.assertIsNone(document.getObject("Part"))
            self.assertIsNone(document.getObject("Marker"))
            self.assertIsNone(document.getObject(marker_folder_name))
            self.assertEqual(assembly.parts, [])
            self.assertEqual(assembly.getPartsFolder().Group, [])
            self.assertEqual(assembly.Group, [])
        finally:
            App.closeDocument(document.Name)

    def test_remove_marker_detaches_without_deleting_marker(self):
        document = App.newDocument("MbDFEMRemoveMarkerTest")

        try:
            part = document.addObject("MbDFEM::MbDPart", "Part")
            marker = document.addObject("MbDFEM::MbDMarker", "Marker")

            part.addMarker(marker)
            self.assertEqual(part.markers, [marker])
            self.assertEqual(part.getMarkersFolder().Group, [marker])
            self.assertIn(marker, part.Group)

            part.removeMarker(marker)

            self.assertIs(document.getObject("Marker"), marker)
            self.assertEqual(part.markers, [])
            self.assertEqual(part.getMarkersFolder().Group, [])
            self.assertNotIn(marker, part.Group)
            self.assertIsNone(marker.getParentGeoFeatureGroup())
        finally:
            App.closeDocument(document.Name)

    def test_freecadmbd_exporter_writes_assembly_model(self):
        with tempfile.TemporaryDirectory() as directory:
            document = App.newDocument("MbDFEMExportTest")

            try:
                assembly = document.addObject("MbDFEM::MbDAssembly", "Assembly")
                part = document.addObject("MbDFEM::MbDPart", "Part")
                fixed_part = document.addObject("MbDFEM::MbDPart", "FixedPart")
                marker_i = document.addObject("MbDFEM::MbDMarker", "MarkerI")
                marker_j = document.addObject("MbDFEM::MbDMarker", "MarkerJ")
                joint = document.addObject("MbDFEM::MbDJoint", "Joint")

                part.Placement.Base = App.Vector(1, 2, 3)
                part.velocity = App.Vector(16, 17, 18)
                part.omega = App.Vector(1.5, 2.5, 3.5)
                fixed_part.Placement.Base = App.Vector(4, 5, 6)
                marker_i.Placement = App.Placement(
                    App.Vector(7, 8, 9),
                    App.Rotation(App.Vector(0, 0, 1), 90),
                )
                mass_marker = part.ensureMassMarker()
                mass_marker.Placement = App.Placement(
                    App.Vector(13, 14, 15),
                    App.Rotation(App.Vector(0, 0, 1), 180),
                )
                mass_marker.mass = 2.5
                mass_marker.principalInertias = App.Vector(0.1, 0.2, 0.3)
                marker_j.Placement.Base = App.Vector(10, 11, 12)

                assembly.addPart(part)
                assembly.addFixedPart(fixed_part)
                part.addMarker(marker_i)
                fixed_part.addMarker(marker_j)
                joint.setMarkers(marker_i, marker_j)
                joint.jointType = "Revolute"
                assembly.addJoint(joint)
                assembly.ensureGravity()
                assembly.ensureSimulationParameters()
                animation_parameters = assembly.ensureAnimationParameters()
                animation_parameters.startFrame = 2
                animation_parameters.endFrame = 4

                filename = os.path.join(directory, "assembly.asmt")
                FreeCADMbDExporter.export_assembly(assembly, filename)
                with open(filename, encoding="utf-8") as file:
                    exported = file.read()

                self.assertIn("FreeCADMbD\nAssembly\n", exported)
                self.assertIn(
                    "\tNotes\n\t\t(Text string: '' runs: (Core.RunArray new))\n",
                    exported,
                )
                self.assertIn("\t\tPart\n\t\t\tName\n\t\t\t\tPart\n", exported)
                self.assertNotIn("\t\tPart\n\t\t\tName\n\t\t\t\tFixedPart\n", exported)
                self.assertIn("\t\t\t\t0.001\t0.002\t0.003\t\n", exported)
                self.assertIn("\t\t\t0.004\t0.005\t0.006\t\n", exported)
                self.assertIn("\t\t\t\t\t0.01\t0.011\t0.012\t\n", exported)
                stripped_lines = [line.strip() for line in exported.splitlines()]

                def find_sequence(sequence, start=0):
                    for index in range(start, len(stripped_lines) - len(sequence) + 1):
                        if stripped_lines[index : index + len(sequence)] == sequence:
                            return index
                    self.fail(f"Could not find ASMT sequence: {sequence!r}")

                part_index = find_sequence(["Part", "Name", "Part"])
                part_position_index = stripped_lines.index("Position3D", part_index)
                part_velocity_index = stripped_lines.index("Velocity3D", part_position_index)
                part_omega_index = stripped_lines.index("Omega3D", part_velocity_index)
                self.assertEqual(stripped_lines[part_velocity_index + 1], "0.016\t0.017\t0.018")
                self.assertEqual(stripped_lines[part_omega_index + 1], "1.5\t2.5\t3.5")

                refpoints_index = stripped_lines.index("RefPoints", part_index)
                refpoint_index = stripped_lines.index("RefPoint", refpoints_index)
                refpoint_position_index = stripped_lines.index("Position3D", refpoint_index)
                self.assertEqual(stripped_lines[refpoint_position_index + 1], "0\t0\t0")
                refpoint_rotation_index = stripped_lines.index(
                    "RotationMatrix",
                    refpoint_position_index,
                )
                self.assertEqual(
                    stripped_lines[refpoint_rotation_index + 1 : refpoint_rotation_index + 4],
                    ["1\t0\t0", "0\t1\t0", "0\t0\t1"],
                )

                mass_marker_index = stripped_lines.index("PrincipalMassMarker", part_index)
                mass_marker_position_index = stripped_lines.index("Position3D", mass_marker_index)
                self.assertEqual(
                    stripped_lines[mass_marker_position_index + 1],
                    "0.013\t0.014\t0.015",
                )
                mass_marker_rotation_index = stripped_lines.index(
                    "RotationMatrix",
                    mass_marker_position_index,
                )
                self.assertEqual(
                    stripped_lines[
                        mass_marker_rotation_index + 1 : mass_marker_rotation_index + 4
                    ],
                    ["-1\t0\t0", "0\t-1\t0", "0\t0\t1"],
                )
                self.assertEqual(stripped_lines[mass_marker_rotation_index + 5], "2.5")
                self.assertEqual(stripped_lines[mass_marker_rotation_index + 7], "0.1\t0.2\t0.3")
                self.assertEqual(stripped_lines[mass_marker_rotation_index + 9], "1")

                marker_index = find_sequence(["Name", "MarkerI"], refpoint_index)
                marker_position_index = stripped_lines.index("Position3D", marker_index)
                self.assertEqual(
                    stripped_lines[marker_position_index + 1],
                    "0.007\t0.008\t0.009",
                )
                marker_rotation_index = stripped_lines.index("RotationMatrix", marker_position_index)
                self.assertEqual(
                    stripped_lines[marker_rotation_index + 1 : marker_rotation_index + 4],
                    ["0\t-1\t0", "1\t0\t0", "0\t0\t1"],
                )
                self.assertLess(
                    exported.index("\t\t\tFeatureOrder\n"),
                    exported.index("\t\t\tPrincipalMassMarker\n"),
                )
                self.assertLess(
                    exported.index("\t\t\tPrincipalMassMarker\n"),
                    exported.index("\t\t\tRefPoints\n"),
                )
                self.assertIn("\t\t\tRevoluteJoint\n", exported)
                self.assertIn("/Assembly/Part/MarkerI", exported)
                self.assertIn("/Assembly/Ground_FixedPart_MarkerJ", exported)
                self.assertNotIn("/Assembly/FixedPart/MarkerJ", exported)
                self.assertIn("\tConstantGravity\n\t\t0\t0\t-9.81", exported)
                self.assertIn("\t\tistart\n\t\t\t3\n", exported)
                self.assertIn("\t\tiend\n\t\t\t5\n", exported)
            finally:
                App.closeDocument(document.Name)

    def test_freecadmbd_exporter_writes_coordinates_relative_to_assembly(self):
        with tempfile.TemporaryDirectory() as directory:
            document = App.newDocument("MbDFEMExportAssemblyFrameTest")

            try:
                assembly = document.addObject("MbDFEM::MbDAssembly", "Assembly")
                part = document.addObject("MbDFEM::MbDPart", "Part")
                marker = document.addObject("MbDFEM::MbDMarker", "Marker")

                assembly.Placement = App.Placement(
                    App.Vector(100, 200, 300),
                    App.Rotation(App.Vector(0, 0, 1), 90),
                )
                part.Placement = App.Placement(
                    App.Vector(1, 2, 3),
                    App.Rotation(App.Vector(0, 0, 1), 90),
                )
                marker.Placement = App.Placement(
                    App.Vector(7, 8, 9),
                    App.Rotation(App.Vector(0, 0, 1), 180),
                )

                assembly.addPart(part)
                part.addMarker(marker)

                filename = os.path.join(directory, "assembly.asmt")
                FreeCADMbDExporter.export_assembly(assembly, filename)
                with open(filename, encoding="utf-8") as file:
                    exported = file.read()

                stripped_lines = [line.strip() for line in exported.splitlines()]

                def find_sequence(sequence, start=0):
                    for index in range(start, len(stripped_lines) - len(sequence) + 1):
                        if stripped_lines[index : index + len(sequence)] == sequence:
                            return index
                    self.fail(f"Could not find ASMT sequence: {sequence!r}")

                assembly_position_index = stripped_lines.index("Position3D")
                self.assertEqual(stripped_lines[assembly_position_index + 1], "0\t0\t0")
                assembly_rotation_index = stripped_lines.index("RotationMatrix")
                self.assertEqual(
                    stripped_lines[assembly_rotation_index + 1 : assembly_rotation_index + 4],
                    ["1\t0\t0", "0\t1\t0", "0\t0\t1"],
                )

                part_index = find_sequence(["Part", "Name", "Part"])
                part_position_index = stripped_lines.index("Position3D", part_index)
                self.assertEqual(stripped_lines[part_position_index + 1], "0.001\t0.002\t0.003")
                part_rotation_index = stripped_lines.index("RotationMatrix", part_position_index)
                self.assertEqual(
                    stripped_lines[part_rotation_index + 1 : part_rotation_index + 4],
                    ["0\t-1\t0", "1\t0\t0", "0\t0\t1"],
                )

                marker_index = find_sequence(["Name", "Marker"], part_index)
                marker_position_index = stripped_lines.index("Position3D", marker_index)
                self.assertEqual(stripped_lines[marker_position_index + 1], "0.007\t0.008\t0.009")
                marker_rotation_index = stripped_lines.index("RotationMatrix", marker_position_index)
                self.assertEqual(
                    stripped_lines[marker_rotation_index + 1 : marker_rotation_index + 4],
                    ["0\t-1\t0", "1\t0\t0", "0\t0\t1"],
                )
            finally:
                App.closeDocument(document.Name)

    def test_freecadmbd_exporter_absorbs_folder_fixed_parts(self):
        with tempfile.TemporaryDirectory() as directory:
            document = App.newDocument("MbDFEMExportFixedFolderTest")

            try:
                assembly = document.addObject("MbDFEM::MbDAssembly", "Assembly")
                stale_part = document.addObject("MbDFEM::MbDPart", "StalePart")
                moving_part = document.addObject("MbDFEM::MbDPart", "MovingPart")
                marker = document.addObject("MbDFEM::MbDMarker", "Marker")

                stale_part.Placement.Base = App.Vector(4, 5, 6)
                marker.Placement.Base = App.Vector(10, 11, 12)
                stale_part.addMarker(marker)
                assembly.addPart(stale_part)
                assembly.addPart(moving_part)
                assembly.getPartsFolder().removeObject(stale_part)
                assembly.getFixedPartsFolder().addObject(stale_part)

                self.assertEqual(assembly.parts, [moving_part])
                self.assertEqual(assembly.fixedparts, [stale_part])
                self.assertEqual(assembly.getPartsFolder().Group, [moving_part])
                self.assertEqual(assembly.getFixedPartsFolder().Group, [stale_part])

                filename = os.path.join(directory, "assembly.asmt")
                FreeCADMbDExporter.export_assembly(assembly, filename)
                with open(filename, encoding="utf-8") as file:
                    exported = file.read()

                self.assertNotIn("\t\tPart\n\t\t\tName\n\t\t\t\tStalePart\n", exported)
                self.assertIn("\t\tPart\n\t\t\tName\n\t\t\t\tMovingPart\n", exported)
                self.assertIn("\t\t\t0.004\t0.005\t0.006\t\n", exported)
                self.assertIn("\t\t\t\t\t0.01\t0.011\t0.012\t\n", exported)
                self.assertIn("Ground_StalePart_Marker", exported)
            finally:
                App.closeDocument(document.Name)

    def test_freecadmbd_default_asmt_path_uses_document_name(self):
        with tempfile.TemporaryDirectory() as directory:
            filename = os.path.join(directory, "RealisticPendulumMbDFEM.FCStd")
            document = App.newDocument("MbDFEMExportPathTest")

            try:
                assembly = document.addObject("MbDFEM::MbDAssembly", "MbDAssembly")
                document.saveAs(filename)
                self.assertEqual(
                    FreeCADMbDBackend.default_asmt_path(assembly),
                    Path(directory)
                    / "RealisticPendulumMbDFEM"
                    / "MbDFEM"
                    / "Case001"
                    / "MbDAssembly.asmt",
                )
            finally:
                App.closeDocument(document.Name)

    def test_freecadmbd_default_calculix_path_uses_part_and_frame(self):
        with tempfile.TemporaryDirectory() as directory:
            filename = os.path.join(directory, "RealisticPendulumMbDFEM.FCStd")
            document = App.newDocument("MbDFEMCalculixPathTest")

            try:
                mbd_part = document.addObject("MbDFEM::MbDPart", "MbDPart001")
                fem_part = document.addObject("MbDFEM::FEMPart", "FEMPart001")
                fem_part.mbdItem = mbd_part
                document.saveAs(filename)

                working_dir = FreeCADMbDBackend.default_calculix_working_dir(fem_part, 12)

                self.assertEqual(
                    working_dir,
                    Path(directory)
                    / "RealisticPendulumMbDFEM"
                    / "MbDFEM"
                    / "Case001"
                    / "MbDPart001"
                    / "Frame000012",
                )
                self.assertTrue(working_dir.is_dir())
            finally:
                App.closeDocument(document.Name)

    def test_freecadmbd_warns_when_asmt_is_not_newer_than_document(self):
        with tempfile.TemporaryDirectory() as directory:
            fcstd_path = Path(directory) / "MyAssembly.FCStd"
            asmt_path = Path(directory) / "MyAssembly" / "MbDFEM" / "Case001" / "MbDAssembly.asmt"
            asmt_path.parent.mkdir(parents=True)
            fcstd_path.write_text("document", encoding="utf-8")
            asmt_path.write_text("asmt", encoding="utf-8")

            class Document:
                FileName = str(fcstd_path)

            os.utime(fcstd_path, (200.0, 200.0))
            os.utime(asmt_path, (100.0, 100.0))

            warning = FreeCADMbDBackend.asmt_freshness_warning(Document, asmt_path)
            self.assertIn("ASMT file is not newer than the FCStd file", warning)

            os.utime(asmt_path, (300.0, 300.0))
            self.assertEqual(
                FreeCADMbDBackend.asmt_freshness_warning(Document, asmt_path),
                "",
            )

    def test_freecadmbd_warns_when_fem_files_are_not_newer_than_asmt(self):
        with tempfile.TemporaryDirectory() as directory:
            filename = os.path.join(directory, "MyAssembly.FCStd")
            document = App.newDocument("MbDFEMFemFreshnessPathTest")

            try:
                mbd_part = document.addObject("MbDFEM::MbDPart", "MbDPart001")
                fem_part = document.addObject("MbDFEM::FEMPart", "FEMPart001")
                fem_part.mbdItem = mbd_part
                document.saveAs(filename)

                asmt_path = FreeCADMbDBackend.default_asmt_path(fem_part)
                working_dir = FreeCADMbDBackend.default_calculix_working_dir(fem_part, 1)
                dat_path = working_dir / "calculix.dat"
                asmt_path.write_text("asmt", encoding="utf-8")
                dat_path.write_text("dat", encoding="utf-8")

                os.utime(asmt_path, (200.0, 200.0))
                os.utime(dat_path, (100.0, 100.0))

                warning = FreeCADMbDBackend.fem_files_freshness_warning(fem_part, 1)
                self.assertIn("FEM files for this state are older than the ASMT file", warning)
                self.assertIn(str(dat_path), warning)

                os.utime(dat_path, (300.0, 300.0))
                self.assertEqual(
                    FreeCADMbDBackend.fem_files_freshness_warning(fem_part, 1),
                    "",
                )
            finally:
                App.closeDocument(document.Name)

    def test_freecadmbd_result_import_fills_solved_asmt_series(self):
        with tempfile.TemporaryDirectory() as directory:
            document = App.newDocument("MbDFEMSolvedSeriesImportTest")

            try:
                assembly = document.addObject("MbDFEM::MbDAssembly", "Assembly")
                part = document.addObject("MbDFEM::MbDPart", "Part")
                joint = document.addObject("MbDFEM::MbDJoint", "Joint")
                assembly.addPart(part)
                assembly.addJoint(joint)

                result_file = os.path.join(directory, "assembly.solved.asmt")
                with open(result_file, "w", encoding="utf-8") as file:
                    file.write(
                        "\n".join(
                            [
                                "FreeCADMbD",
                                "TimeSeries",
                                "Time\tInput\t0\t0.1\t0.2",
                                "AssemblySeries\t/Assembly",
                                "X\t0\t1\t2\t3",
                                "Y\t0\t4\t5\t6",
                                "AlphaZ\t0\t7\t8\t9",
                                "PartSeries\t/Assembly/Part",
                                "X\t0\t10\t11\t12",
                                "Z\t0\t13\t14\t15",
                                "OmegaY\t0\t16\t17\t18",
                                "RevoluteJointSeries\t/Assembly/Joint",
                                "FXonI\t0\t20\t21\t22",
                                "FYonI\t0\t23\t24\t25",
                                "FZonI\t0\t26\t27\t28",
                                "TXonI\t0\t29\t30\t31",
                                "TYonI\t0\t32\t33\t34",
                                "TZonI\t0\t35\t36\t37",
                                "",
                            ]
                        )
                    )

                imported = FreeCADMbDResults.import_results(assembly, result_file)

                self.assertEqual(imported, [assembly, part, joint])
                self.assertEqual(assembly.times, [-sys.float_info.max, 0.0, 0.1, 0.2])
                self.assertEqual(assembly.xs, [0.0, 1.0, 2.0, 3.0])
                self.assertEqual(assembly.ys, [0.0, 4.0, 5.0, 6.0])
                self.assertEqual(assembly.alpzs, [0.0, 7.0, 8.0, 9.0])
                self.assertEqual(part.xs, [0.0, 10.0, 11.0, 12.0])
                self.assertEqual(part.zs, [0.0, 13.0, 14.0, 15.0])
                self.assertEqual(part.omeys, [0.0, 16.0, 17.0, 18.0])
                self.assertEqual(joint.fxs, [0.0, 20.0, 21.0, 22.0])
                self.assertEqual(joint.fys, [0.0, 23.0, 24.0, 25.0])
                self.assertEqual(joint.fzs, [0.0, 26.0, 27.0, 28.0])
                self.assertEqual(joint.txs, [0.0, 29.0, 30.0, 31.0])
                self.assertEqual(joint.tys, [0.0, 32.0, 33.0, 34.0])
                self.assertEqual(joint.tzs, [0.0, 35.0, 36.0, 37.0])
            finally:
                App.closeDocument(document.Name)

    def test_freecadmbd_animation_controller_scrubs_part_results(self):
        document = App.newDocument("MbDFEMAnimationScrubTest")

        try:
            assembly = document.addObject("MbDFEM::MbDAssembly", "Assembly")
            part = document.addObject("MbDFEM::MbDPart", "Part")
            assembly.addPart(part)
            assembly.times = [0.0, 0.5, 1.0]
            part.xs = [0.0, 0.5, 1.0]
            part.ys = [1.0, 1.5, 2.0]
            part.zs = [2.0, 2.5, 3.0]
            part.vxs = [4.0, 4.5, 5.0]
            part.vys = [5.0, 5.5, 6.0]
            part.vzs = [6.0, 6.5, 7.0]
            part.omexs = [7.0, 7.5, 8.0]
            part.omeys = [8.0, 8.5, 9.0]
            part.omezs = [9.0, 9.5, 10.0]
            part.axs = [10.0, 10.5, 11.0]
            part.ays = [11.0, 11.5, 12.0]
            part.azs = [12.0, 12.5, 13.0]
            part.alpxs = [13.0, 13.5, 14.0]
            part.alpys = [14.0, 14.5, 15.0]
            part.alpzs = [15.0, 15.5, 16.0]

            controller = FreeCADMbDAnimation.AnimationController(assembly)

            self.assertEqual(controller.times, [0.0, 0.5, 1.0])
            self.assertEqual(controller.frame_count, 3)

            controller.setTime(0.25)

            self.assertAlmostEqual(part.Placement.Base.x, 250.0)
            self.assertAlmostEqual(part.Placement.Base.y, 1250.0)
            self.assertAlmostEqual(part.Placement.Base.z, 2250.0)
            self.assertEqual(part.velocity, App.Vector(4250.0, 5250.0, 6250.0))
            self.assertEqual(part.omega, App.Vector(7.25, 8.25, 9.25))
            self.assertEqual(part.acceleration, App.Vector(10.25, 11.25, 12.25))
            self.assertEqual(part.alpha, App.Vector(13.25, 14.25, 15.25))
            self.assertEqual(controller.current_frame, 0)

            controller.stepForward()

            self.assertEqual(controller.current_frame, 1)
            self.assertAlmostEqual(controller.current_time, 0.5)
            self.assertAlmostEqual(part.Placement.Base.x, 500.0)
        finally:
            App.closeDocument(document.Name)

    def test_freecadmbd_animation_controller_uses_frame_range(self):
        document = App.newDocument("MbDFEMAnimationRangeTest")

        try:
            assembly = document.addObject("MbDFEM::MbDAssembly", "Assembly")
            part = document.addObject("MbDFEM::MbDPart", "Part")
            assembly.addPart(part)
            parameters = assembly.ensureAnimationParameters()
            parameters.startFrame = 1
            parameters.endFrame = 2
            assembly.times = [0.0, 0.5, 1.0, 1.5]
            part.xs = [0.0, 1.0, 2.0, 3.0]
            part.ys = [0.0, 0.0, 0.0, 0.0]
            part.zs = [0.0, 0.0, 0.0, 0.0]

            controller = FreeCADMbDAnimation.AnimationController(assembly)

            self.assertEqual(controller.source_frame_count, 4)
            self.assertEqual(controller.frame_count, 2)
            self.assertEqual(controller.start_frame, 1)
            self.assertEqual(controller.end_frame, 2)
            self.assertEqual(controller.times, [0.5, 1.0])
            self.assertEqual(controller.result_times, [0.0, 0.5, 1.0, 1.5])

            controller.setFrame(0)
            self.assertEqual(controller.current_frame, 0)
            self.assertAlmostEqual(part.Placement.Base.x, 0.0)

            controller.setFrame(3)
            self.assertEqual(controller.current_frame, 3)
            self.assertAlmostEqual(part.Placement.Base.x, 3000.0)
        finally:
            App.closeDocument(document.Name)

    def test_freecadmbd_animation_controller_slerps_rotations(self):
        document = App.newDocument("MbDFEMAnimationRotationTest")

        try:
            assembly = document.addObject("MbDFEM::MbDAssembly", "Assembly")
            part = document.addObject("MbDFEM::MbDPart", "Part")
            assembly.addPart(part)
            assembly.times = [0.0, 1.0]
            part.xs = [0.0, 0.0]
            part.ys = [0.0, 0.0]
            part.zs = [0.0, 0.0]
            part.bryxs = [0.0, 0.0]
            part.bryys = [0.0, 0.0]
            part.bryzs = [math.radians(350), math.radians(10)]

            controller = FreeCADMbDAnimation.AnimationController(assembly)
            controller.setTime(0.5)

            expected = App.Rotation(App.Vector(0, 0, 1), 0)
            long_way = App.Rotation(App.Vector(0, 0, 1), 180)
            self.assertTrue(part.Placement.Rotation.isSame(expected, 1.0e-7))
            self.assertFalse(part.Placement.Rotation.isSame(long_way, 1.0e-7))
        finally:
            App.closeDocument(document.Name)

    def test_freecadmbd_animation_controller_uses_animation_parameters_for_tick(self):
        document = App.newDocument("MbDFEMAnimationTickTest")

        try:
            assembly = document.addObject("MbDFEM::MbDAssembly", "Assembly")
            part = document.addObject("MbDFEM::MbDPart", "Part")
            assembly.addPart(part)
            parameters = assembly.ensureAnimationParameters()
            parameters.updateRate = 10
            parameters.startFrame = 0
            parameters.playbackSpeed = 2.0
            parameters.loop = True
            assembly.times = [0.0, 1.0]
            part.xs = [0.0, 1.0]
            part.ys = [0.0, 0.0]
            part.zs = [0.0, 0.0]

            controller = FreeCADMbDAnimation.AnimationController(assembly)

            self.assertEqual(controller.update_rate, 10.0)
            self.assertEqual(controller.playback_speed, 2.0)
            controller.tick(0.25)
            self.assertAlmostEqual(controller.current_time, 0.5)
            self.assertAlmostEqual(part.Placement.Base.x, 500.0)

            controller.tick(0.5)

            self.assertAlmostEqual(controller.current_time, 0.5)
            self.assertAlmostEqual(part.Placement.Base.x, 500.0)
        finally:
            App.closeDocument(document.Name)

    def test_freecadmbd_result_import_rejects_mismatched_series_lengths(self):
        with tempfile.TemporaryDirectory() as directory:
            document = App.newDocument("MbDFEMSeriesLengthTest")

            try:
                assembly = document.addObject("MbDFEM::MbDAssembly", "Assembly")

                result_file = os.path.join(directory, "assembly.solved.asmt")
                with open(result_file, "w", encoding="utf-8") as file:
                    file.write(
                        "\n".join(
                            [
                                "FreeCADMbD",
                                "TimeSeries",
                                "Time\tInput\t0\t0.1",
                                "AssemblySeries\t/Assembly",
                                "X\t1\t2",
                                "",
                            ]
                        )
                    )

                with self.assertRaisesRegex(ValueError, "Assembly.xs has 2 values; expected 3"):
                    FreeCADMbDResults.import_results(assembly, result_file)
            finally:
                App.closeDocument(document.Name)

    def test_freecadmbd_backend_requires_configured_executable(self):
        document = App.newDocument("MbDFEMBackendConfigTest")
        old_env = os.environ.pop("FREECADMBD_EXE", None)
        preferences = App.ParamGet(FreeCADMbDBackend.PREF_GROUP)
        old_preference = preferences.GetString(FreeCADMbDBackend.EXE_PREF, "")

        try:
            preferences.SetString(FreeCADMbDBackend.EXE_PREF, "")
            assembly = document.addObject("MbDFEM::MbDAssembly", "Assembly")

            with self.assertRaisesRegex(RuntimeError, "executable is not configured"):
                FreeCADMbDBackend.FreeCADMbDProcessBackend().solve(assembly)
        finally:
            preferences.SetString(FreeCADMbDBackend.EXE_PREF, old_preference)
            if old_env is not None:
                os.environ["FREECADMBD_EXE"] = old_env
            App.closeDocument(document.Name)
