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
import FreeCADMbDFEMCLOADs
import FreeCADMbDFEMDLOADs
import FreeCADMbDFEMResultsPanel
import FreeCADMbDFreeBodyDiagram
import FreeCADMbDResults
import Part


class _FakeViewport:
    def getPointOnViewport(self, point):
        return (point.x, point.y)


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
            self.assertIn("*NSET,NSET=MbDFEM321Constraints\n1,2,4\n", content)
            self.assertIn("*BOUNDARY\n1,1,1,0\n1,2,2,0\n1,3,3,0\n", content)
            self.assertIn("*NODE PRINT,NSET=MbDFEM321Constraints\nRF\n", content)
            self.assertLess(content.index("*NSET"), content.index("*STEP"))
            self.assertLess(content.index("*NODE PRINT"), content.index("*END STEP"))
        finally:
            os.remove(inp_file_name)

    def test_321_constraint_reaction_forces_are_read_from_dat(self):
        Embedded = self._load_embedded_module_for_app_test()

        constraint_nodes = (
            ("nodeXYZ", 1, self._MeshNode(0, 0, 0)),
            ("nodeYZ", 2, self._MeshNode(1, 0, 0)),
            ("nodeZ", 4, self._MeshNode(0, 1, 0)),
        )
        fd, dat_file_name = tempfile.mkstemp(suffix=".dat")
        os.close(fd)

        try:
            Path(dat_file_name).write_text(
                "\n"
                " forces (fx,fy,fz) for set MBDFEM321CONSTRAINTS and time  0.1000000E+01\n"
                "\n"
                "      1  1.000000D+00 -2.000000D+00  3.000000D+00\n"
                "      2  4.000000D+00  0.000000D+00 -5.000000D+00\n"
                "      4  0.000000D+00  6.000000D+00  0.000000D+00\n"
                "\n",
                encoding="utf-8",
            )

            reactions = Embedded._read_321_constraint_reaction_forces(
                dat_file_name,
                constraint_nodes,
            )
            self.assertEqual(reactions[1], (1.0, -2.0, 3.0))
            self.assertEqual(reactions[2], (4.0, 0.0, -5.0))
            self.assertEqual(reactions[4], (0.0, 6.0, 0.0))

            lines = Embedded._format_321_constraint_force_feedback(
                dat_file_name,
                constraint_nodes,
            )
            self.assertEqual(
                lines,
                [
                    "totalRF: Fx=5, Fy=4, Fz=-2, |F|=6.7082039325",
                    "totalRM: Mx=0, My=5, Mz=0, |M|=5",
                ],
            )
        finally:
            os.remove(dat_file_name)

    def test_joint_force_uses_fem_part_rotation_at_requested_state(self):
        Embedded = self._load_embedded_module_for_app_test()

        class MbDPart:
            Placement = App.Placement()
            bryxs = [0.0, 0.0, 0.0]
            bryys = [0.0, 0.0, math.pi / 2.0]
            bryzs = [0.0, 0.0, 0.0]

            def getGlobalPlacement(self):
                return self.Placement

        class FEMPart:
            mbdItem = MbDPart()
            Document = None

        force = App.Vector(1.0, 0.0, 0.0)
        transformed = Embedded._vector_in_fem_part_coordinates(
            FEMPart(),
            force,
            state_index=2,
        )
        state_rotation = App.Rotation(App.Vector(0, 1, 0), 90.0)
        expected = state_rotation.inverted().multVec(force)

        self.assertLess(transformed.distanceToPoint(expected), 1e-12)
        self.assertGreater(transformed.distanceToPoint(force), 1.0)

    def test_joint_loads_do_not_fall_back_to_marker_when_face_pairs_are_unavailable(self):
        Embedded = self._load_embedded_module_for_app_test()
        original_face_pairs = Embedded._joint_face_pairs
        try:
            Embedded._joint_face_pairs = lambda _joint: []

            loads = Embedded._joint_loads_for_fem_part(
                object(),
                object(),
                {},
                App.Vector(1, 2, 3),
            )
        finally:
            Embedded._joint_face_pairs = original_face_pairs

        self.assertEqual(loads, [])

    def test_joint_face_pairs_share_force_and_torque_equally(self):
        Embedded = self._load_embedded_module_for_app_test()
        part_i, part_j = object(), object()
        force, torque = App.Vector(12, -6, 3), App.Vector(-9, 15, 6)
        original_pairs = Embedded._joint_face_pairs
        original_cloads = Embedded._face_pair_cloads_for_fem_part
        try:
            for count in (1, 2, 3):
                pairs = [
                    {"type": "CylCyl", "partI": part_i, "partJ": part_j}
                    for _ in range(count)
                ]
                # Unsupported faces and faces on unrelated parts cannot carry a share.
                pairs += [
                    {"type": "RectRect", "partI": part_i, "partJ": part_j},
                    {"type": "CylCyl", "partI": object(), "partJ": object()},
                ]
                Embedded._joint_face_pairs = lambda _joint: pairs
                Embedded._face_pair_cloads_for_fem_part = (
                    lambda joint, pair, part, nodes, force, torque: (force, torque)
                )
                for part, sign in ((part_i, 1.0), (part_j, -1.0)):
                    for input_torque in (torque * sign, None):
                        with self.subTest(count=count, sign=sign, torque=input_torque):
                            loads = Embedded._joint_loads_for_fem_part(
                                object(), part, {}, force * sign, input_torque
                            )
                            self.assertEqual(len(loads), count)
                            total_force, total_torque = App.Vector(), App.Vector()
                            for pair_force, pair_torque in loads:
                                self.assertLess(
                                    pair_force.distanceToPoint(force * (sign / count)), 1e-12
                                )
                                total_force += pair_force
                                if input_torque is None:
                                    self.assertIsNone(pair_torque)
                                else:
                                    self.assertLess(
                                        pair_torque.distanceToPoint(input_torque * (1.0 / count)),
                                        1e-12,
                                    )
                                    total_torque += pair_torque
                            self.assertLess(total_force.distanceToPoint(force * sign), 1e-12)
                            if input_torque is not None:
                                self.assertLess(total_torque.distanceToPoint(input_torque), 1e-12)
            self.assertEqual((force.x, force.y, force.z), (12, -6, 3))
            self.assertEqual((torque.x, torque.y, torque.z), (-9, 15, 6))
        finally:
            Embedded._joint_face_pairs = original_pairs
            Embedded._face_pair_cloads_for_fem_part = original_cloads

    def test_joint_face_pair_torque_shift_preserves_moment_at_marker_i(self):
        Embedded = self._load_embedded_module_for_app_test()
        part = object()
        origin = App.Vector(2, -3, 5)
        centers = [App.Vector(1, 4, -2), App.Vector(-3, 2, 8)]
        force, torque = App.Vector(12, -6, 3), App.Vector(-9, 15, 6)
        original_pairs = Embedded._joint_face_pairs
        original_reference = Embedded._cylindrical_face_reference
        original_cloads = Embedded._face_pair_cloads_for_fem_part
        try:
            Embedded._cylindrical_face_reference = lambda face: {"origin": face}
            Embedded._face_pair_cloads_for_fem_part = (
                lambda joint, pair, part, nodes, force, torque: (force, torque)
            )
            for side, sign in (("I", 1.0), ("J", -1.0)):
                for face_centers in (centers, [origin]):
                    Embedded._joint_face_pairs = lambda _joint: [
                        {"type": "CylCyl", "part" + side: part, "face" + side: center}
                        for center in face_centers
                    ]
                    for input_torque in (torque * sign, None):
                        with self.subTest(side=side, centers=face_centers, torque=input_torque):
                            loads = Embedded._joint_loads_for_fem_part(
                                object(), part, {}, force * sign, input_torque,
                                force_origin=origin,
                            )
                            total_force, total_moment = App.Vector(), App.Vector()
                            for center, (pair_force, pair_torque) in zip(face_centers, loads):
                                total_force += pair_force
                                total_moment += pair_torque + (center - origin).cross(pair_force)
                            self.assertEqual(len(loads), len(face_centers))
                            self.assertLess(total_force.distanceToPoint(force * sign), 1e-12)
                            expected = App.Vector() if input_torque is None else input_torque
                            self.assertLess(total_moment.distanceToPoint(expected), 1e-12)
        finally:
            Embedded._joint_face_pairs = original_pairs
            Embedded._cylindrical_face_reference = original_reference
            Embedded._face_pair_cloads_for_fem_part = original_cloads

    def test_joint_force_origin_uses_marker_i_and_sampled_part_placements(self):
        from types import SimpleNamespace

        Embedded = self._load_embedded_module_for_app_test()
        assembly_placement = App.Placement(App.Vector(100, 200, -30), App.Rotation(20, 30, 40))
        assembly = SimpleNamespace(Placement=assembly_placement)
        source = SimpleNamespace(
            Placement=App.Placement(App.Vector(90, 80, 70), App.Rotation()),
            xs=[1, 10], ys=[2, 20], zs=[3, 30],
            bryxs=[0, 0], bryys=[0, 0], bryzs=[0, math.pi / 2],
        )
        target = SimpleNamespace(
            Placement=App.Placement(App.Vector(-90, -80, -70), App.Rotation()),
            xs=[4, -10], ys=[5, 5], zs=[6, 7],
            bryxs=[0, math.pi / 2], bryys=[0, 0], bryzs=[0, 0],
        )
        source.getGlobalPlacement = lambda: assembly_placement.multiply(source.Placement)
        target.getGlobalPlacement = lambda: assembly_placement.multiply(target.Placement)
        source.isDerivedFrom = lambda _type: True
        marker = SimpleNamespace(
            Placement=App.Placement(App.Vector(2, 3, 4), App.Rotation()),
            getParentGeoFeatureGroup=lambda: source,
        )
        joint = SimpleNamespace(markerI=marker)
        original_assembly = Embedded._owning_mbd_assembly
        try:
            Embedded._owning_mbd_assembly = lambda _part: assembly
            for state in (None, 1):
                if state is None:
                    source_global = source.getGlobalPlacement()
                    target_global = target.getGlobalPlacement()
                else:
                    source_global = assembly_placement.multiply(App.Placement(
                        App.Vector(10, 20, 30), App.Rotation(App.Vector(0, 0, 1), 90)
                    ))
                    target_global = assembly_placement.multiply(App.Placement(
                        App.Vector(-10, 5, 7), App.Rotation(App.Vector(1, 0, 0), 90)
                    ))
                expected = target_global.inverse().multVec(
                    source_global.multVec(marker.Placement.Base)
                )
                actual = Embedded._joint_force_origin_in_fem_part(
                    joint, SimpleNamespace(mbdItem=target), state
                )
                self.assertLess(actual.distanceToPoint(expected), 1e-10)
                same_part = Embedded._joint_force_origin_in_fem_part(
                    joint, SimpleNamespace(mbdItem=source), state
                )
                self.assertLess(same_part.distanceToPoint(marker.Placement.Base), 1e-12)
        finally:
            Embedded._owning_mbd_assembly = original_assembly

    def test_321_constraint_nodes_are_cached_and_frame_metadata_preserves_result_nodes(self):
        Embedded = self._load_embedded_module_for_app_test()

        class Mesh:
            Name = "Mesh"

        class FEMPart:
            mesh = Mesh()

            def addProperty(self, _property_type, name, _group, _doc):
                setattr(self, name, None)

        fem_part = FEMPart()
        first_nodes = {
            1: self._MeshNode(0, 0, -20),
            2: self._MeshNode(10, 0, -20),
            3: self._MeshNode(0, 4, -19.9),
            4: self._MeshNode(0, 4, -20),
        }
        second_nodes = {
            11: self._MeshNode(0, 0, -20),
            12: self._MeshNode(10, 0, -20),
            13: self._MeshNode(0, 4, -20),
        }
        original_nodes = Embedded._fem_mesh_nodes
        try:
            Embedded._fem_mesh_nodes = lambda mesh: first_nodes
            first = Embedded._321_constraint_nodes_for_fem_part(fem_part)

            self.assertEqual([(label, node_id) for label, node_id, _ in first], [
                ("nodeXYZ", 1),
                ("nodeYZ", 2),
                ("nodeZ", 4),
            ])
            self.assertEqual(fem_part.Auto321NodeXYZ, 1)
            self.assertEqual(fem_part.Auto321NodeYZ, 2)
            self.assertEqual(fem_part.Auto321NodeZ, 4)

            fd, inp_file_name = tempfile.mkstemp(suffix=".inp")
            os.close(fd)
            try:
                Embedded._write_321_constraint_frame_metadata(inp_file_name, fem_part, first)
                sidecar = Embedded._read_321_constraint_frame_metadata(
                    Embedded._frame_metadata_sidecar_file_name_for_inp(inp_file_name)
                )
                metadata = Embedded._read_frame_metadata_sidecar(
                    Embedded._frame_metadata_sidecar_file_name_for_inp(inp_file_name)
                )
            finally:
                os.remove(inp_file_name)
                sidecar_name = Embedded._frame_metadata_sidecar_file_name_for_inp(inp_file_name)
                if os.path.exists(sidecar_name):
                    os.remove(sidecar_name)

            self.assertIn("constraints_321", metadata["artifacts"])
            self.assertEqual([(label, node_id) for label, node_id, _ in sidecar], [
                ("nodeXYZ", 1),
                ("nodeYZ", 2),
                ("nodeZ", 4),
            ])

            Embedded._fem_mesh_nodes = lambda mesh: second_nodes
            second = Embedded._321_constraint_nodes_for_fem_part(fem_part)

            self.assertEqual([(label, node_id) for label, node_id, _ in second], [
                ("nodeXYZ", 11),
                ("nodeYZ", 12),
                ("nodeZ", 13),
            ])
            self.assertEqual(fem_part.Auto321NodeXYZ, 11)
            self.assertEqual(fem_part.Auto321NodeYZ, 12)
            self.assertEqual(fem_part.Auto321NodeZ, 13)
        finally:
            Embedded._fem_mesh_nodes = original_nodes

    def test_321_mesh_cache_uses_global_link_scope(self):
        Embedded = self._load_embedded_module_for_app_test()
        document = App.newDocument("MbDFEM321CacheScopeTest")
        try:
            fem_part = document.addObject("MbDFEM::FEMPart", "FEMPart")
            mesh = document.addObject("App::FeaturePython", "Mesh")

            Embedded._set_fem_part_321_cache(fem_part, mesh, "signature", (1, 2, 3))

            self.assertEqual(
                fem_part.getTypeIdOfProperty("Auto321Mesh"),
                "App::PropertyLinkGlobal",
            )
            self.assertIs(fem_part.Auto321Mesh, mesh)
            document.recompute()
        finally:
            App.closeDocument(document.Name)

    def test_321_constraint_writer_adds_force_output_to_existing_constraint_block(self):
        Embedded = self._load_embedded_module_for_app_test()

        nodes = {
            1: self._MeshNode(0, 0, 0),
            2: self._MeshNode(1, 0, 0),
            3: self._MeshNode(0, 1, 0),
        }
        fd, inp_file_name = tempfile.mkstemp(suffix=".inp")
        os.close(fd)

        try:
            Path(inp_file_name).write_text(
                "*HEADING\n"
                "*STEP\n"
                "** Automatic 3-2-1 constraints\n"
                "*BOUNDARY\n"
                "1,1,1,0\n"
                "1,2,2,0\n"
                "1,3,3,0\n"
                "2,2,2,0\n"
                "2,3,3,0\n"
                "3,3,3,0\n"
                "*END STEP\n",
                encoding="utf-8",
            )

            Embedded._add_321_constraints_to_inp(inp_file_name, nodes)
            content = Path(inp_file_name).read_text(encoding="utf-8")

            self.assertEqual(content.count("** Automatic 3-2-1 constraints"), 1)
            self.assertEqual(content.count("*BOUNDARY"), 1)
            self.assertIn("*NSET,NSET=MbDFEM321Constraints\n1,2,3\n", content)
            self.assertIn("*NODE PRINT,NSET=MbDFEM321Constraints\nRF\n", content)
            self.assertLess(content.index("*NSET"), content.index("*STEP"))
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
            gravity.gravity = App.Vector(0, -9810.0, 0)
            assembly.addPart(part)
            fem_part.mbdItem = part
            Path(inp_file_name).write_text("*HEADING\n*STEP\n*END STEP\n", encoding="utf-8")

            self.assertEqual(
                Embedded._add_mbd_gravity_to_inp(inp_file_name, fem_part),
                App.Vector(0, -9810.0, 0),
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
            gravity.gravity = App.Vector(0, 0, -9810.0)
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

    def test_calculix_input_mbd_density_uses_fem_tonne_per_mm3_units(self):
        import ObjectsFem

        Embedded = self._load_embedded_module_for_app_test()
        document = App.newDocument("MbDFEMCalculixDensityUnitsTest")
        fd, inp_file_name = tempfile.mkstemp(suffix=".inp")
        os.close(fd)

        try:
            assembly = document.addObject("MbDFEM::MbDAssembly", "Assembly")
            part = document.addObject("MbDFEM::MbDPart", "Part")
            fem_part = document.addObject("MbDFEM::FEMPart", "FEMPart")
            material = ObjectsFem.makeMaterialSolid(document, "FEMPart_Material")
            material.Material = {
                "Name": "Steel",
                "YoungsModulus": "210000 MPa",
                "PoissonRatio": "0.3",
                "Density": "7850 kg/m^3",
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

            density = Embedded._mbd_density_in_tonne_per_mm3(fem_part)

            self.assertAlmostEqual(density, 7.85e-9)
            self.assertEqual(
                density,
                App.Units.Quantity("7850 kg/m^3").getValueAs("t/mm^3").Value,
            )
            self.assertTrue(Embedded._ensure_mbd_density_in_inp(inp_file_name, fem_part))
            self.assertIn("*DENSITY\n7.85e-09\n", Path(inp_file_name).read_text(encoding="utf-8"))
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
            self.assertAlmostEqual(loads[0][1], 2.0)
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

    def test_calculix_input_mbd_acceleration_loads_use_mm_per_second_squared(self):
        import Fem

        Embedded = self._load_embedded_module_for_app_test()
        document = App.newDocument("MbDFEMCalculixAccelerationUnitsTest")
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
            gravity = assembly.ensureGravity()
            gravity.gravity = App.Vector(0, -9810.0, 0)
            assembly.addPart(part)
            fem_part.mbdItem = part
            fem_part.mesh = mesh_object
            part.acceleration = App.Vector(0, -9810.0, 0)
            Path(inp_file_name).write_text("*HEADING\n*STEP\n*END STEP\n", encoding="utf-8")

            Embedded._add_mbd_gravity_to_inp(inp_file_name, fem_part)
            loads = Embedded._add_mbd_dalembert_loads_to_inp(inp_file_name, fem_part)
            content = Path(inp_file_name).read_text(encoding="utf-8")

            self.assertEqual(len(loads), 1)
            self.assertAlmostEqual(loads[0][1], 9810.0)
            self.assertIn("Eall,GRAV,9810,0,-1,0\n", content)
            self.assertIn("7,GRAV,9810,0,1,0\n", content)
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

    def test_calculix_input_dalembert_loads_use_volume_elements_only(self):
        import Fem

        Embedded = self._load_embedded_module_for_app_test()
        document = App.newDocument("MbDFEMCalculixDalembertVolumeOnlyTest")
        fd, inp_file_name = tempfile.mkstemp(suffix=".inp")
        os.close(fd)

        try:
            mesh = Fem.FemMesh()
            mesh.addNode(0, 1, 0, 1)
            mesh.addNode(0, -1, 0, 2)
            mesh.addNode(0, 0, 1, 3)
            mesh.addNode(4, 0, -1, 4)
            mesh.addNode(100, 0, 0, 5)
            mesh.addNode(100, 1, 0, 6)
            mesh.addNode(100, 0, 1, 7)
            mesh.addVolume([1, 2, 3, 4], 42)
            mesh.addFace([5, 6, 7], 84)
            mesh.addEdge([5, 6], 126)

            mesh_object = document.addObject("Fem::FemMeshObject", "Mesh")
            mesh_object.FemMesh = mesh
            assembly = document.addObject("MbDFEM::MbDAssembly", "Assembly")
            part = document.addObject("MbDFEM::MbDPart", "Part")
            fem_part = document.addObject("MbDFEM::FEMPart", "FEMPart")
            assembly.addPart(part)
            fem_part.mbdItem = part
            fem_part.mesh = mesh_object
            part.acceleration = App.Vector(0, 2, 0)
            Path(inp_file_name).write_text("*HEADING\n*STEP\n*END STEP\n", encoding="utf-8")

            loads = Embedded._add_mbd_dalembert_loads_to_inp(inp_file_name, fem_part)
            content = Path(inp_file_name).read_text(encoding="utf-8")

            self.assertEqual([load[0] for load in loads], [42])
            self.assertIn("*DLOAD\n42,GRAV,2,0,-1", content)
            self.assertNotIn("\n84,GRAV", content)
            self.assertNotIn("\n126,GRAV", content)
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
            part.acceleration = App.Vector(0, 0, -9810)
            fem_part.mbdItem = part
            fem_part.mesh = mesh_object
            document.recompute()
            Path(inp_file_name).write_text("*HEADING\n*STEP\n*END STEP\n", encoding="utf-8")

            inertial_acceleration = App.Vector(0, 0, 9810)
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
            part.azs = [0.0, -9810.0]
            fem_part.mbdItem = part
            fem_part.mesh = mesh_object

            FreeCADMbDFEMResultsPanel.apply_state(fem_part, 1)
            Path(inp_file_name).write_text("*HEADING\n*STEP\n*END STEP\n", encoding="utf-8")

            loads = Embedded._add_mbd_dalembert_loads_to_inp(inp_file_name, fem_part)
            content = Path(inp_file_name).read_text(encoding="utf-8")

            self.assertEqual(part.acceleration, App.Vector(0, 0, -9810.0))
            self.assertEqual(len(loads), 1)
            self.assertAlmostEqual(loads[0][1], 9810.0)
            self.assertLess(loads[0][2].distanceToPoint(App.Vector(0, 0, 1)), 1e-7)
            self.assertIn("*DLOAD\n7,GRAV,9810,0,0,1\n", content)
        finally:
            os.remove(inp_file_name)
            App.closeDocument(document.Name)

    def test_calculix_input_distributes_joint_side_force_on_cylindrical_hole_octants(self):
        import Fem

        Embedded = self._load_embedded_module_for_app_test()
        document = App.newDocument("MbDFEMJointCylinderLoadTest")
        fd, inp_file_name = tempfile.mkstemp(suffix=".inp")
        os.close(fd)

        try:
            mesh = Fem.FemMesh()
            node_data = {
                1: (1, 1, 1),
                2: (1, -1, 1),
                3: (1, 1, -3),
                4: (math.sqrt(1.75), -0.5, 2),
                9: (1, -1, -2),
                5: (-1, 1, 1),
                6: (-1, -1, 1),
                7: (-1, 1, -1),
                8: (-1, -1, -1),
            }
            for node_id, coordinates in node_data.items():
                mesh.addNode(*coordinates, node_id)

            mesh_object = document.addObject("Fem::FemMeshObject", "Mesh")
            mesh_object.FemMesh = mesh
            assembly = document.addObject("MbDFEM::MbDAssembly", "Assembly")
            pin_shape = Part.makeCylinder(
                math.sqrt(2.0),
                5.0,
                App.Vector(0, 0, -3),
                App.Vector(0, 0, 1),
            )
            block = Part.makeBox(6.0, 6.0, 5.0, App.Vector(-3.0, -3.0, -3.0))
            part = document.addObject("MbDFEM::MbDPart", "Part")
            part.Shape = block.cut(pin_shape)
            pin_part = document.addObject("MbDFEM::MbDPart", "PinPart")
            pin_part.Shape = pin_shape
            fem_part = document.addObject("MbDFEM::FEMPart", "FEMPart")
            marker = document.addObject("MbDFEM::MbDMarker", "Marker")
            marker_j = document.addObject("MbDFEM::MbDMarker", "MarkerJ")
            joint = document.addObject("MbDFEM::MbDJoint", "Joint")
            assembly.times = [0.0, 1.0]
            assembly.addPart(part)
            assembly.addPart(pin_part)
            assembly.addJoint(joint)
            part.addMarker(marker)
            pin_part.addMarker(marker_j)
            fem_part.mbdItem = part
            fem_part.mesh = mesh_object
            marker.Placement = App.Placement()
            marker_j.Placement = App.Placement()
            joint.markerI = marker
            joint.markerJ = marker_j
            joint.fxs = [0.0, 80.0]
            joint.fys = [0.0, 0.0]
            joint.fzs = [0.0, 40.0]
            Path(inp_file_name).write_text("*HEADING\n*STEP\n*END STEP\n", encoding="utf-8")

            loads = Embedded._add_mbd_joint_cylindrical_hole_loads_to_inp(
                inp_file_name,
                fem_part,
                state_index=1,
            )
            content = Path(inp_file_name).read_text(encoding="utf-8")
            frame_metadata = Embedded._read_frame_metadata_sidecar(
                Embedded._frame_metadata_sidecar_file_name_for_inp(inp_file_name)
            )

            self.assertEqual(len(loads), 1)
            cload_metadata = frame_metadata["artifacts"][Embedded._MBD_CLOAD_ARTIFACT]
            self.assertEqual(cload_metadata["algorithm"], Embedded._MBD_CLOAD_ALGORITHM)
            self.assertEqual(cload_metadata["source"], os.path.basename(inp_file_name))
            values = loads[0]["nodal_values"]
            node_values = {
                node_id: Embedded._joint_side_force_node_value(loads[0], name, node_id)
                for name in ("U1", "U4", "L1", "L4")
                for node_id in loads[0]["octants"][name]
            }
            self.assertNotAlmostEqual(node_values[2], node_values[4])
            self.assertAlmostEqual(
                node_values[2],
                values["U4"] * loads[0]["node_cosines"][2],
            )
            self.assertAlmostEqual(
                node_values[4],
                values["U4"] * loads[0]["node_cosines"][4],
            )
            total_force = (
                node_values[1]
                + node_values[2]
                + node_values[4]
                + node_values[3]
                + node_values[9]
            )
            moment_y = (
                node_values[1] * 1
                + node_values[2] * 1
                + node_values[4] * 2
                + node_values[3] * -3
                + node_values[9] * -2
            )
            moment_z = (
                node_values[1] * 1
                + node_values[2] * -1
                + node_values[4] * -0.5
                + node_values[3] * 1
                + node_values[9] * -1
            )
            self.assertAlmostEqual(total_force, 80.0)
            self.assertAlmostEqual(moment_y, 0.0)
            self.assertAlmostEqual(moment_z, 0.0)
            self.assertIn("*NSET,NSET=NSU1\n1\n", content)
            self.assertIn("*NSET,NSET=NSU4\n2,4\n", content)
            self.assertIn("*NSET,NSET=NSL1\n3\n", content)
            self.assertIn("*NSET,NSET=NSL4\n9\n", content)
            self.assertIn("*NSET,NSET=NS1\n1,3\n", content)
            self.assertIn("*NSET,NSET=NS2\n5,7\n", content)
            self.assertIn("*NSET,NSET=NS3\n6,8\n", content)
            self.assertIn("*NSET,NSET=NS4\n2,4,9\n", content)
            self.assertIn("*CLOAD\n", content)
            cload_values = {}
            axis_cload_values = {}
            for line in content.splitlines():
                fields = line.split(",")
                if len(fields) == 3 and fields[1] == "1":
                    cload_values[int(fields[0])] = float(fields[2])
                if len(fields) == 3 and fields[0].startswith("NS") and fields[1] == "3":
                    axis_cload_values[fields[0][2:]] = float(fields[2])
            for node_id, value in node_values.items():
                self.assertAlmostEqual(cload_values[node_id], value)
            self.assertEqual(set(axis_cload_values), {"1", "2", "3", "4"})
            for name, value in loads[0]["axis_nodal_values"].items():
                self.assertAlmostEqual(axis_cload_values[name], value)
            total_axis_force = sum(
                loads[0]["axis_nodal_values"][name] * len(loads[0]["axis_sets"][name])
                for name in ("1", "2", "3", "4")
            )
            moment_x = sum(
                (node_data[node_id][1]) * loads[0]["axis_nodal_values"][name]
                for name in ("1", "2", "3", "4")
                for node_id in loads[0]["axis_sets"][name]
            )
            moment_y = sum(
                (node_data[node_id][0]) * loads[0]["axis_nodal_values"][name]
                for name in ("1", "2", "3", "4")
                for node_id in loads[0]["axis_sets"][name]
            )
            self.assertAlmostEqual(total_axis_force, 40.0)
            self.assertAlmostEqual(moment_x, 0.0)
            self.assertAlmostEqual(moment_y, 0.0)
        finally:
            sidecar_name = Embedded._frame_metadata_sidecar_file_name_for_inp(inp_file_name)
            if os.path.exists(sidecar_name):
                os.remove(sidecar_name)
            os.remove(inp_file_name)
            App.closeDocument(document.Name)

    def test_calculix_input_joint_cylindrical_cloads_use_newtons(self):
        Embedded = self._load_embedded_module_for_app_test()
        load = {
            "x_axis": App.Vector(0.6, 0.8, 0),
            "z_axis": App.Vector(0, 0, 1),
            "octants": {"U1": [10], "U4": [], "L1": [], "L4": []},
            "nodal_values": {"U1": 100.0, "U4": 0.0, "L1": 0.0, "L4": 0.0},
            "node_cosines": {10: 1.0},
        }

        content = Embedded._format_joint_cylindrical_hole_cloads(load)

        self.assertEqual(content, "*CLOAD\n10,1,60\n10,2,80\n")

    def test_calculix_input_keeps_joint_force_and_torque_cloads_separate(self):
        Embedded = self._load_embedded_module_for_app_test()
        load = {
            "x_axis": App.Vector(1, 0, 0),
            "z_axis": App.Vector(0, 0, 1),
            "octants": {"U1": [10], "U4": [], "L1": [], "L4": []},
            "nodal_values": {"U1": 5.0, "U4": 0.0, "L1": 0.0, "L4": 0.0},
            "node_cosines": {10: 1.0},
            "torque_side_load": {
                "x_axis": App.Vector(1, 0, 0),
                "octants": {"U1": [10], "U4": [], "L2": [], "L3": []},
                "nodal_values": {"U1": 3.0, "U4": 0.0, "L2": 0.0, "L3": 0.0},
                "node_cosines": {10: 1.0},
                "node_z_values": {10: 2.0},
            },
        }

        content = Embedded._format_joint_cylindrical_hole_cloads(load)

        self.assertEqual(content, "*CLOAD\n10,1,5\n10,1,6\n")


    def test_calculix_input_distributes_joint_side_torque_on_cylindrical_face_octants(self):
        Embedded = self._load_embedded_module_for_app_test()
        origin = App.Vector(0, 0, 0)
        x_axis = App.Vector(1, 0, 0)
        y_axis = App.Vector(0, 1, 0)
        z_axis = App.Vector(0, 0, 1)
        nodes = {
            1: App.Vector(1, 1, 2),
            2: App.Vector(1, -1, 2),
            3: App.Vector(-1, 1, -1),
            4: App.Vector(-1, -1, -1),
            5: App.Vector(-1, 1, 2),
            6: App.Vector(-1, -1, 2),
            7: App.Vector(1, 1, -1),
            8: App.Vector(1, -1, -1),
        }
        torque_system = (
            origin,
            x_axis,
            y_axis,
            z_axis,
            80.0,
            0.0,
            {"radius": math.sqrt(2.0), "axial_limits": (-1.0, 2.0)},
        )

        torque_load = Embedded._prototype_pin_bending_load(
            torque_system,
            nodes,
        )

        self.assertIsNotNone(torque_load)
        self.assertEqual(torque_load["octants"]["U1"], [1])
        self.assertEqual(torque_load["octants"]["U4"], [2])
        self.assertEqual(torque_load["octants"]["L2"], [3])
        self.assertEqual(torque_load["octants"]["L3"], [4])
        self.assertEqual(torque_load["node_z_values"], {1: 2.0, 2: 2.0, 3: -1.0, 4: -1.0})
        node_values = {
            node_id: Embedded._joint_torque_y_node_value(torque_load, name, node_id)
            for name in ("U1", "U4", "L2", "L3")
            for node_id in torque_load["octants"][name]
        }
        for name in ("U1", "U4", "L2", "L3"):
            for node_id in torque_load["octants"][name]:
                self.assertAlmostEqual(
                    node_values[node_id],
                    torque_load["nodal_values"][name]
                    * torque_load["node_z_values"][node_id]
                    * torque_load["node_cosines"][node_id],
                )
        total_force = sum(node_values.values())
        moment_y = sum(nodes[node_id].z * value for node_id, value in node_values.items())
        moment_z = -sum(nodes[node_id].y * value for node_id, value in node_values.items())
        self.assertAlmostEqual(total_force, 0.0)
        self.assertAlmostEqual(moment_y, 80.0)
        self.assertAlmostEqual(moment_z, 0.0)

    def test_axial_torque_cloads_preserve_wrench_and_minimize_region_forces(self):
        import numpy as np

        Embedded = self._load_embedded_module_for_app_test()
        origin = App.Vector(7, -3, 11)
        rotation = App.Rotation(23, 41, 17)
        x_axis, y_axis, z_axis = [
            rotation.multVec(axis)
            for axis in (App.Vector(1, 0, 0), App.Vector(0, 1, 0), App.Vector(0, 0, 1))
        ]
        names = ("U1", "U2", "U3", "U4", "L1", "L2", "L3", "L4")
        for symmetric in (True, False):
            nodes, octants = {}, {name: [] for name in names}
            for region, name in enumerate(names):
                for offset in range(2 if symmetric else 1 + region % 3):
                    angle = math.radians(90 * (region % 4) + 20 + offset * 19)
                    z = (2 if region < 4 else -2) if symmetric else (
                        (1 if region < 4 else -1) * (1 + region * 0.2 + offset * 0.3)
                    )
                    node_id = len(nodes) + 1
                    nodes[node_id] = origin + rotation.multVec(
                        App.Vector(3 * math.cos(angle), 3 * math.sin(angle), z)
                    )
                    octants[name].append(node_id)
            for requested in (80.0, -80.0):
                with self.subTest(symmetric=symmetric, torque=requested):
                    axis_load = Embedded._prototype_pin_axial_torque_load(
                        nodes, octants, origin, x_axis, y_axis, z_axis, requested
                    )
                    self.assertIsNotNone(axis_load)
                    load = {"x_axis": x_axis, "z_axis": z_axis, "octants": octants,
                            "torque_axis_load": axis_load}
                    content = Embedded._format_joint_face_pair_cloads(load)
                    vectors = {}
                    for line in content.splitlines()[1:]:
                        node, dof, value = line.split(",")
                        vector = vectors.setdefault(int(node), App.Vector())
                        vector[int(dof) - 1] += float(value)
                    total_force, total_moment = App.Vector(), App.Vector()
                    for node_id, vector in vectors.items():
                        relative = nodes[node_id] - origin
                        self.assertAlmostEqual(vector.dot(z_axis), 0.0, places=10)
                        self.assertAlmostEqual(vector.dot(relative), 0.0, places=10)
                        total_force += vector
                        total_moment += relative.cross(vector)
                    self.assertLess(total_force.Length, 1e-9)
                    self.assertLess(total_moment.distanceToPoint(z_axis * requested), 1e-9)
                    matrix = np.zeros((6, 8))
                    for column, name in enumerate(names):
                        for node_id in octants[name]:
                            relative = nodes[node_id] - origin
                            tangent = z_axis.cross(relative)
                            tangent.normalize()
                            moment = relative.cross(tangent)
                            matrix[:, column] += tuple(tangent) + tuple(moment)
                            self.assertAlmostEqual(
                                vectors[node_id].dot(tangent), axis_load["nodal_values"][name],
                                places=10,
                            )
                    # The minimum-cost solution is orthogonal to every feasible
                    # perturbation in the equilibrium matrix's null space.
                    _, singular, vh = np.linalg.svd(matrix, full_matrices=True)
                    rank = sum(singular > 1e-10)
                    coefficients = np.array([axis_load["nodal_values"][name] for name in names])
                    self.assertLess(np.linalg.norm(vh[rank:] @ coefficients), 1e-9)
                    if symmetric:
                        for value in coefficients:
                            self.assertAlmostEqual(value, requested / (len(nodes) * 3))
                    nsets = Embedded._format_joint_face_pair_nsets(load)
                    for name in names:
                        self.assertIn("*NSET,NSET=NS" + name + "\n", nsets)

    def test_axial_torque_handles_redundant_and_infeasible_constraints(self):
        Embedded = self._load_embedded_module_for_app_test()
        names = ("U1", "U2", "U3", "U4", "L1", "L2", "L3", "L4")
        nodes = {i + 1: App.Vector(math.cos(i * math.pi / 2 + 0.3),
                                   math.sin(i * math.pi / 2 + 0.3), 0) for i in range(4)}
        octants = {name: [i + 1] if i < 4 else [] for i, name in enumerate(names)}
        args = (App.Vector(), App.Vector(1, 0, 0), App.Vector(0, 1, 0), App.Vector(0, 0, 1), 40)
        result = Embedded._prototype_pin_axial_torque_load(nodes, octants, *args)
        self.assertIsNotNone(result)
        for name in names[:4]:
            self.assertAlmostEqual(result["nodal_values"][name], 10)
        sparse = {name: [1] if name == "U1" else [] for name in names}
        self.assertIsNone(Embedded._prototype_pin_axial_torque_load(nodes, sparse, *args))

    def test_cylindrical_face_load_exports_pure_axial_torque(self):
        Embedded = self._load_embedded_module_for_app_test()
        cylinder = Part.makeCylinder(3, 4, App.Vector(0, 0, -2))
        face = next(f for f in cylinder.Faces if f.Surface.TypeId == "Part::GeomCylinder")
        nodes = {}
        for z in (-1, 1):
            for angle in (0.3, 1.9, 3.4, 5.1):
                nodes[len(nodes) + 1] = App.Vector(3 * math.cos(angle), 3 * math.sin(angle), z)
        load = Embedded._prototype_pin_face_load(
            None, face, None, nodes, App.Vector(), App.Vector(0, 0, 80)
        )
        self.assertIsNotNone(load)
        resultant, moment = App.Vector(), App.Vector()
        for line in Embedded._format_joint_face_pair_cloads(load).splitlines()[1:]:
            node, dof, value = line.split(",")
            vector = App.Vector()
            vector[int(dof) - 1] = float(value)
            resultant += vector
            moment += (nodes[int(node)] - load["origin"]).cross(vector)
        self.assertLess(resultant.Length, 1e-9)
        self.assertLess(moment.distanceToPoint(App.Vector(0, 0, 80)), 1e-9)

    def test_cyl_cyl_hole_cloads_are_computed_by_cpp_face_pair(self):
        import MbDFEM

        document = App.newDocument("MbDFEMCppCylCylCLOADTest")
        try:
            face_pair = document.addObject("MbDFEM::CylCylFacePair", "FacePair")
            nodes = []
            node_id = 1
            for z_value in (-1.0, 1.0):
                for angle in (-75.0, -45.0, -15.0, 15.0, 45.0, 75.0):
                    radians = math.radians(angle)
                    nodes.append(
                        (node_id, App.Vector(math.cos(radians), math.sin(radians), z_value))
                    )
                    node_id += 1

            cloads = MbDFEM.cylCylHoleCLOADs(
                face_pair,
                nodes,
                App.Vector(0, 0, 0),
                App.Vector(0, 0, 1),
                1.0,
                -1.0,
                1.0,
                App.Vector(80, 0, 0),
            )

            forces = {}
            for result_node_id, dof, value in cloads:
                vector = forces.setdefault(result_node_id, App.Vector())
                if dof == 1:
                    vector.x += value
                elif dof == 2:
                    vector.y += value
                else:
                    vector.z += value
            total_force = App.Vector()
            total_moment = App.Vector()
            node_positions = dict(nodes)
            for result_node_id, vector in forces.items():
                total_force += vector
                total_moment += node_positions[result_node_id].cross(vector)

            self.assertGreater(len(cloads), 0)
            self.assertLess(total_force.distanceToPoint(App.Vector(80, 0, 0)), 1e-9)
            self.assertLess(total_moment.Length, 1e-9)
        finally:
            App.closeDocument(document.Name)

    def test_cyl_cyl_hole_cloads_are_symmetric_on_symmetric_mesh(self):
        import MbDFEM

        document = App.newDocument("MbDFEMCppCylCylSymmetryTest")
        try:
            face_pair = document.addObject("MbDFEM::CylCylFacePair", "FacePair")
            nodes = []
            mirrored_ids = []
            node_id = 1
            for z_value in (-1.0, 1.0):
                for angle in (15.0, 45.0, 75.0):
                    radians = math.radians(angle)
                    positive_id = node_id
                    nodes.append((positive_id, App.Vector(math.cos(radians), math.sin(radians), z_value)))
                    node_id += 1
                    negative_id = node_id
                    nodes.append((negative_id, App.Vector(math.cos(radians), -math.sin(radians), z_value)))
                    node_id += 1
                    mirrored_ids.append((positive_id, negative_id))

            cloads = MbDFEM.cylCylHoleCLOADs(
                face_pair,
                nodes,
                App.Vector(),
                App.Vector(0, 0, 1),
                1.0,
                -1.0,
                1.0,
                App.Vector(80, 0, 0),
            )
            x_forces = {node: value for node, dof, value in cloads if dof == 1}

            for positive_id, negative_id in mirrored_ids:
                self.assertAlmostEqual(x_forces[positive_id], x_forces[negative_id])
        finally:
            App.closeDocument(document.Name)

    def test_cyl_cyl_hole_cloads_preserve_dense_mesh_resultant(self):
        import MbDFEM

        document = App.newDocument("MbDFEMCppCylCylDenseMeshTest")
        try:
            face_pair = document.addObject("MbDFEM::CylCylFacePair", "FacePair")
            nodes = []
            node_id = 1
            for z_value in (-5.0, 5.0):
                for angle_index in range(-900, 901):
                    radians = math.radians(angle_index * 0.1)
                    nodes.append(
                        (
                            node_id,
                            App.Vector(28.0 * math.cos(radians), 28.0 * math.sin(radians), z_value),
                        )
                    )
                    node_id += 1

            requested_force = App.Vector(100.0, 0.0, 0.0)
            cloads = MbDFEM.cylCylHoleCLOADs(
                face_pair,
                nodes,
                App.Vector(),
                App.Vector(0, 0, 1),
                28.0,
                -5.0,
                5.0,
                requested_force,
            )
            resultant = App.Vector()
            for _node_id, dof, value in cloads:
                resultant[dof - 1] += value

            self.assertGreater(len(cloads), 0)
            self.assertLess(resultant.distanceToPoint(requested_force), 1e-9)
        finally:
            App.closeDocument(document.Name)

    def test_cyl_cyl_hole_cloads_omit_unsupported_sparse_distribution(self):
        import MbDFEM

        document = App.newDocument("MbDFEMCppCylCylSparseTest")
        try:
            face_pair = document.addObject("MbDFEM::CylCylFacePair", "FacePair")
            nodes = [
                (1, App.Vector(1, 0, -1)),
                (2, App.Vector(0, 1, -1)),
                (3, App.Vector(1, 0, 1)),
                (4, App.Vector(0, 1, 1)),
            ]

            cloads = MbDFEM.cylCylHoleCLOADs(
                face_pair,
                nodes,
                App.Vector(),
                App.Vector(0, 0, 1),
                1.0,
                -1.0,
                1.0,
                App.Vector(80, 0, 0),
            )

            self.assertEqual(cloads, [])
        finally:
            App.closeDocument(document.Name)

    def test_cylindrical_face_reference_is_centered_over_bounded_face(self):
        Embedded = self._load_embedded_module_for_app_test()
        cylinder = Part.makeCylinder(5.0, 14.0, App.Vector(0, -7, 192), App.Vector(0, 1, 0))
        face = next(
            candidate
            for candidate in cylinder.Faces
            if candidate.Surface.TypeId == "Part::GeomCylinder"
        )

        reference = Embedded._cylindrical_face_reference(face)

        self.assertIsNotNone(reference)
        self.assertLess(reference["origin"].distanceToPoint(App.Vector(0, 0, 192)), 1e-12)
        self.assertAlmostEqual(reference["axial_limits"][0], -7.0)
        self.assertAlmostEqual(reference["axial_limits"][1], 7.0)


    def test_hole_cpp_rejects_incomplete_bending_load(self):
        document = App.newDocument("HoleIncompleteBending")
        try:
            pair = document.addObject("MbDFEM::CylCylFacePair", "Pair")
            # An equatorial ring supports axial torque but cannot create bending
            # with the prescribed transverse force couples.
            nodes = [(i + 1, App.Vector(math.cos(a), math.sin(a), 0))
                     for i, a in enumerate((0.3, 1.9, 3.4, 5.1))]
            with self.assertRaisesRegex(RuntimeError, "bending torque"):
                MbDFEM.cylCylHoleLoadComponents(
                    pair, nodes, App.Vector(), App.Vector(0, 0, 1), 1, -1, 1,
                    App.Vector(), App.Vector(0, 10, 20),
                )
        finally:
            App.closeDocument(document.Name)

    def test_hole_cpp_domain_entry_samples_shares_and_transfers_marker_i_reaction(self):
        Embedded = self._load_embedded_module_for_app_test()
        document = App.newDocument("FinalHoleDomain")
        try:
            assembly = document.addObject("MbDFEM::MbDAssembly", "Assembly")
            assembly.Placement = App.Placement(App.Vector(20, -10, 5), App.Rotation(12, 23, 34))
            hole = document.addObject("MbDFEM::MbDPart", "Hole")
            pin = document.addObject("MbDFEM::MbDPart", "Pin")
            cylinder = Part.makeCylinder(3, 6, App.Vector(0, 0, -3))
            hole.Shape = Part.makeBox(10, 10, 6, App.Vector(-5, -5, -3)).cut(cylinder)
            pin.Shape = cylinder
            assembly.addPart(hole)
            assembly.addPart(pin)
            marker_hole = document.addObject("MbDFEM::MbDMarker", "HoleMarker")
            marker_pin = document.addObject("MbDFEM::MbDMarker", "PinMarker")
            hole.addMarker(marker_hole)
            pin.addMarker(marker_pin)
            marker_hole.Placement.Base = App.Vector(1, 2, 1)
            marker_pin.Placement.Base = App.Vector(-1, 1, 2)
            joint = document.addObject("MbDFEM::MbDJoint", "Joint")
            assembly.addJoint(joint)
            hole_face = next(i for i, f in enumerate(hole.Shape.Faces, 1)
                             if f.Surface.TypeId == "Part::GeomCylinder")
            pin_face = next(i for i, f in enumerate(pin.Shape.Faces, 1)
                            if f.Surface.TypeId == "Part::GeomCylinder")
            pairs = []
            for reverse in (False, True):
                pair = document.addObject("MbDFEM::CylCylFacePair", "Pair")
                pair.faceI = ((pin, [f"Face{pin_face}"]) if reverse else (hole, [f"Face{hole_face}"]))
                pair.faceJ = ((hole, [f"Face{hole_face}"]) if reverse else (pin, [f"Face{pin_face}"]))
                pairs.append(pair)
            nodes = {}
            for z in (-2, 2):
                for i in range(24):
                    angle = (i + 0.3) * math.pi / 12
                    nodes[len(nodes) + 1] = App.Vector(3 * math.cos(angle), 3 * math.sin(angle), z)
            hole.xs, hole.ys, hole.zs = [0, 4], [1, 3], [2, -1]
            pin.xs, pin.ys, pin.zs = [1, -2], [0, 2], [1, 4]
            hole.bryxs, hole.bryys, hole.bryzs = [0, 0.3], [0, 0.2], [0, -0.4]
            pin.bryxs, pin.bryys, pin.bryzs = [0, -0.1], [0, 0.4], [0, 0.2]
            joint.fxs, joint.fys, joint.fzs = [12, 16], [4, -2], [7, 3]
            joint.txs, joint.tys, joint.tzs = [9, -2], [-6, 8], [13, 10]
            for on_i in (True, False):
                joint.markerI = marker_hole if on_i else marker_pin
                joint.markerJ = marker_pin if on_i else marker_hole
                for sample in ((-1, -1, 0.0), (1, 1, 0.0), (0, 1, 0.35)):
                    with self.subTest(on_i=on_i, sample=sample):
                        lower, upper, ratio = sample
                        if lower < 0:
                            target = hole.getGlobalPlacement()
                            source = (hole if on_i else pin).getGlobalPlacement()
                            force, torque = App.Vector(12, 4, 7), App.Vector(9, -6, 13)
                        else:
                            target = assembly.getGlobalPlacement().multiply(
                                FreeCADMbDFreeBodyDiagram._placement_at_sample(hole, sample)
                            )
                            source = assembly.getGlobalPlacement().multiply(
                                FreeCADMbDFreeBodyDiagram._placement_at_sample(hole if on_i else pin, sample)
                            )
                            force = FreeCADMbDFreeBodyDiagram._sample_vector(joint, ("fxs", "fys", "fzs"), sample)
                            torque = FreeCADMbDFreeBodyDiagram._sample_vector(joint, ("txs", "tys", "tzs"), sample)
                        origin = target.inverse().multVec(source.multVec(joint.markerI.Placement.Base))
                        sign = 1 if on_i else -1
                        force = target.Rotation.inverted().multVec(force * sign)
                        torque = target.Rotation.inverted().multVec(torque * sign)
                        resultant, moment = App.Vector(), App.Vector()
                        for pair in pairs:
                            load = MbDFEM.cylCylJointHoleLoad(pair, joint, hole, list(nodes.items()), pairs, *sample)
                            self.assertLess(load["force"].distanceToPoint(force * 0.5), 1e-9)
                            self.assertLess(load["torque"].distanceToPoint(
                                torque * 0.5 + (origin - load["origin"]).cross(force * 0.5)), 1e-9)
                            for line in Embedded._format_joint_face_pair_cloads(load).splitlines():
                                if line.startswith("*"):
                                    continue
                                node, dof, value = line.split(",")
                                vector = App.Vector()
                                vector[int(dof) - 1] = float(value)
                                resultant += vector
                                moment += (nodes[int(node)] - origin).cross(vector)
                        self.assertLess(resultant.distanceToPoint(force), 1e-8)
                        self.assertLess(moment.distanceToPoint(torque), 1e-8)
                        original_pairs = Embedded._joint_face_pairs
                        try:
                            side = "I" if on_i else "J"
                            Embedded._joint_face_pairs = lambda _joint: [
                                {"type": "CylCyl", "part" + side: hole,
                                 "face" + side: hole.Shape.Faces[hole_face - 1],
                                 "role" + side: "hole", "object": pair}
                                for pair in pairs
                            ]
                            # Python's pin-prototype inputs must have no influence
                            # on the authoritative hole-domain entry point.
                            bridged = Embedded._joint_loads_for_fem_part(
                                joint, hole, nodes, App.Vector(999, 999, 999),
                                App.Vector(999, 999, 999), force_origin=App.Vector(999, 999, 999),
                                sample=sample,
                            )
                            self.assertEqual(len(bridged), 2)
                            for load in bridged:
                                self.assertLess(load["force"].distanceToPoint(force * 0.5), 1e-9)
                        finally:
                            Embedded._joint_face_pairs = original_pairs
            with self.assertRaisesRegex(RuntimeError, "not a cylindrical hole"):
                MbDFEM.cylCylJointHoleLoad(pairs[0], joint, pin, list(nodes.items()), pairs)
        finally:
            App.closeDocument(document.Name)

    def test_hole_debug_display_keeps_contributions_at_same_node_separate(self):
        from types import SimpleNamespace

        module = FreeCADMbDFEMCLOADs
        load = {"nodes": {1: App.Vector()}, "cload_components": {
            "transverse_force": [(1, 1, 5.0)],
            "bending_torque": [(1, 1, -2.0)],
        }}
        mesh = SimpleNamespace(getGlobalPlacement=lambda: App.Placement())
        part = SimpleNamespace(mesh=mesh)
        original_loads = module._mbd_joint_cylindrical_hole_loads
        original_inp = module._diagram_vectors_from_matching_inp
        try:
            module._mbd_joint_cylindrical_hole_loads = lambda *args: [load]
            module._diagram_vectors_from_matching_inp = lambda *args: None
            vectors = module._diagram_vectors(part, object())
            self.assertEqual(len(vectors), 2)
            self.assertEqual([vector.value.x for vector in vectors], [5.0, -2.0])
            content = module.FreeCADMbDFEMEmbedded._MBD_JOINT_CLOAD_MARKER + (
                "*CLOAD\n** MbDFEM transverse_force\n1,1,5\n"
                "** MbDFEM bending_torque\n1,1,-2\n"
            )
            parsed = module._cload_vectors_from_inp_content(content, separate=True)
            self.assertEqual([vector.x for vector in parsed.values()], [5.0, -2.0])
        finally:
            module._mbd_joint_cylindrical_hole_loads = original_loads
            module._diagram_vectors_from_matching_inp = original_inp

    def test_hole_cpp_export_preserves_separate_shifted_face_pair_wrenches(self):
        Embedded = self._load_embedded_module_for_app_test()
        document = App.newDocument("HoleCombinedWrench")
        original_pairs = Embedded._joint_face_pairs
        try:
            part = document.addObject("MbDFEM::MbDPart", "Part")
            rotation = App.Rotation(23, 41, 17)
            z_axis = rotation.multVec(App.Vector(0, 0, 1))
            force = rotation.multVec(App.Vector(12, 4, 7))
            torque = rotation.multVec(App.Vector(9, -6, 13))
            marker_origin = App.Vector(-2, 4, 1)
            pairs, nodes = [], {}
            for center in (App.Vector(10, 0, 0), App.Vector(-10, 0, 0)):
                cylinder = Part.makeCylinder(3, 6, center - z_axis * 3, z_axis)
                face = next(f for f in cylinder.Faces if f.Surface.TypeId == "Part::GeomCylinder")
                pair = document.addObject("MbDFEM::CylCylFacePair", "Pair")
                pairs.append({"type": "CylCyl", "partI": part, "faceI": face,
                              "roleI": "hole", "object": pair})
                for level in (-1, 1):
                    for i in range(24):
                        angle = i * math.pi / 12 + 0.13
                        # Unequal axial positions exercise the moment constraints.
                        local = App.Vector(3 * math.cos(angle), 3 * math.sin(angle),
                                           level * (1.2 + 0.03 * i))
                        nodes[len(nodes) + 1] = center + rotation.multVec(local)
            loads = []
            for pair in pairs:
                reference = Embedded._cylindrical_face_reference(pair["faceI"])
                center = reference["origin"]
                components = MbDFEM.cylCylHoleLoadComponents(
                    pair["object"], list(nodes.items()), center, z_axis, 3, -3, 3,
                    force * 0.5, torque * 0.5 + (marker_origin - center).cross(force * 0.5),
                )
                loads.append({"origin": center, "x_axis": rotation.multVec(App.Vector(1, 0, 0)),
                              "z_axis": z_axis, "cload_components": components})
            self.assertEqual(len(loads), 2)
            resultant, moment = App.Vector(), App.Vector()
            for load in loads:
                components = load["cload_components"]
                self.assertEqual(set(components), {
                    "transverse_force", "axial_force", "bending_torque", "axial_torque"
                })
                self.assertTrue(all(components.values()))
                records = [record for values in components.values() for record in values]
                self.assertGreater(len(records), len({(n, d) for n, d, _ in records}))
                content = Embedded._format_joint_face_pair_cloads(load)
                for line in content.splitlines():
                    if line.startswith("*"):
                        continue
                    node, dof, value = line.split(",")
                    vector = App.Vector()
                    vector[int(dof) - 1] = float(value)
                    resultant += vector
                    moment += (nodes[int(node)] - marker_origin).cross(vector)
                parsed = FreeCADMbDFEMCLOADs._cload_vectors_from_inp_content(
                    Embedded._MBD_JOINT_CLOAD_MARKER + content, separate=True
                )
                self.assertEqual(len({key[0] for key in parsed}), 4)
            self.assertLess(resultant.distanceToPoint(force), 1e-8)
            self.assertLess(moment.distanceToPoint(torque), 1e-8)
        finally:
            Embedded._joint_face_pairs = original_pairs
            App.closeDocument(document.Name)

    def test_hole_separate_cloads_calculix_reaction_equilibrium(self):
        import shutil
        import subprocess

        solver = os.environ.get("CCX") or shutil.which("ccx")
        if not solver:
            self.skipTest("Set CCX to run the hole CLOAD CalculiX integration test")
        Embedded = self._load_embedded_module_for_app_test()
        document = App.newDocument("HoleCalculixEquilibrium")
        try:
            pair = document.addObject("MbDFEM::CylCylFacePair", "Pair")
            nodes, fixed, hole_nodes = {}, [], []
            sectors = 16
            for level, z in enumerate((-2.0, 2.0)):
                for ring, radius in enumerate((3.0, 5.0)):
                    for i in range(sectors):
                        angle = (i + 0.25) * 2 * math.pi / sectors
                        node_id = 1 + level * 2 * sectors + ring * sectors + i
                        nodes[node_id] = App.Vector(radius * math.cos(angle), radius * math.sin(angle), z)
                        (hole_nodes if ring == 0 else fixed).append(node_id)
            force, torque = App.Vector(12, 4, 7), App.Vector(9, -6, 13)
            components = MbDFEM.cylCylHoleLoadComponents(
                pair, list(nodes.items()), App.Vector(), App.Vector(0, 0, 1), 3, -2, 2,
                force, torque,
            )
            # Keep roundoff-sized contributions separate. Overlong scientific
            # notation used to make CalculiX 2.18 reject the entire input deck.
            components["bending_torque"].extend([
                (hole_nodes[0], 1, -5.1662497447053908e-18),
                (hole_nodes[0], 1, 5.1662497447053908e-18),
            ])
            load = {"x_axis": App.Vector(1, 0, 0), "z_axis": App.Vector(0, 0, 1),
                    "cload_components": components}
            lines = ["*NODE\n"]
            lines += [f"{n},{p.x:.17g},{p.y:.17g},{p.z:.17g}\n" for n, p in nodes.items()]
            lines.append("*ELEMENT,TYPE=C3D8,ELSET=SOLID\n")
            for i in range(sectors):
                j = (i + 1) % sectors
                lower = [1 + i, 1 + sectors + i, 1 + sectors + j, 1 + j]
                element = lower + [n + 2 * sectors for n in lower]
                lines.append(f"{i + 1}," + ",".join(map(str, element)) + "\n")
            lines += ["*NSET,NSET=FIXED\n", ",".join(map(str, fixed[:16])) + "\n",
                      ",".join(map(str, fixed[16:])) + "\n",
                      "*MATERIAL,NAME=STEEL\n*ELASTIC\n210000,0.3\n",
                      "*SOLID SECTION,ELSET=SOLID,MATERIAL=STEEL\n",
                      "*BOUNDARY\nFIXED,1,3\n*STEP\n*STATIC\n",
                      Embedded._format_joint_face_pair_cloads(load),
                      "*NODE PRINT,NSET=FIXED\nRF\n*END STEP\n"]
            with tempfile.TemporaryDirectory(prefix="mbdfem-hole-") as directory:
                Path(directory, "hole.inp").write_text("".join(lines))
                run = subprocess.run([solver, "-i", "hole"], cwd=directory,
                                     capture_output=True, text=True, timeout=60)
                self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
                result = Path(directory, "hole.dat").read_text()
            reactions = {}
            for line in result.splitlines():
                fields = line.split()
                if len(fields) == 4 and fields[0].isdigit():
                    reactions[int(fields[0])] = App.Vector(*map(float, fields[1:]))
            self.assertEqual(set(reactions), set(fixed), result)
            resultant, moment = App.Vector(), App.Vector()
            for node, reaction in reactions.items():
                resultant += reaction
                moment += nodes[node].cross(reaction)
            self.assertLess((resultant + force).Length, 1e-4)
            self.assertLess((moment + torque).Length, 1e-4)
        finally:
            App.closeDocument(document.Name)

    def test_hole_cload_numeric_fields_fit_calculix_reader(self):
        Embedded = self._load_embedded_module_for_app_test()
        values = [-5.1662497447053908e-18, -1.4204904906045063e-49,
                  -1.234567890123456e-308, -1.234567890123456e308,
                  -0.020664998978821566, 12.345678901234567]
        load = {"x_axis": App.Vector(1, 0, 0), "z_axis": App.Vector(0, 0, 1),
                "cload_components": {"transverse_force": [(8, 1, value) for value in values]}}
        content = Embedded._format_joint_face_pair_cloads(load)
        records = [line.split(",") for line in content.splitlines() if not line.startswith("*")]
        self.assertEqual(len(records), len(values))
        for record, expected in zip(records, values):
            self.assertLessEqual(len(record[2]), 20)
            self.assertNotEqual(float(record[2]), 0.0)
            self.assertLess(abs(float(record[2]) / expected - 1.0), 1e-12)

    def test_joint_touching_face_pairs_returns_faces_from_marker_parts(self):
        Embedded = self._load_embedded_module_for_app_test()
        document = App.newDocument("MbDFEMJointTouchingFacePairsTest")

        try:
            part_i = document.addObject("MbDFEM::MbDPart", "PartI")
            part_j = document.addObject("MbDFEM::MbDPart", "PartJ")
            part_i.Shape = Part.makeBox(1, 1, 1)
            part_j.Shape = Part.makeBox(1, 1, 1)
            part_j.Placement = App.Placement(App.Vector(1, 0, 0), App.Rotation())

            marker_i = document.addObject("MbDFEM::MbDMarker", "MarkerI")
            marker_j = document.addObject("MbDFEM::MbDMarker", "MarkerJ")
            part_i.addMarker(marker_i)
            part_j.addMarker(marker_j)

            joint = document.addObject("MbDFEM::MbDJoint", "Joint")
            joint.markerI = marker_i
            joint.markerJ = marker_j
            fem_joint = document.addObject("MbDFEM::FEMJoint", "FEMJoint")
            fem_joint.mbdItem = joint
            document.recompute()

            pairs = Embedded._joint_touching_face_pairs(joint)

            self.assertFalse(hasattr(joint, "facePairs"))
            self.assertTrue(hasattr(fem_joint, "facePairs"))
            self.assertEqual(len(pairs), 1)
            face_i, face_j = pairs[0]
            self.assertLess(face_i.CenterOfMass.distanceToPoint(App.Vector(1, 0.5, 0.5)), 1e-7)
            self.assertLess(face_j.CenterOfMass.distanceToPoint(App.Vector(0, 0.5, 0.5)), 1e-7)
            self.assertEqual(len(fem_joint.facePairs), 1)
            face_pair = fem_joint.facePairs[0]
            self.assertTrue(face_pair.isDerivedFrom("MbDFEM::FacePair"))
            self.assertEqual(face_pair.faceI, (part_i, ("Face6",)))
            self.assertEqual(face_pair.faceJ, (part_j, ("Face5",)))
        finally:
            App.closeDocument(document.Name)

    def test_face_pair_type_uses_anul_anul_when_either_face_is_annular(self):
        Embedded = self._load_embedded_module_for_app_test()

        self.assertEqual(Embedded._face_pair_type("Anul", "Anul"), "AnulAnul")
        self.assertEqual(Embedded._face_pair_type("Anul", "Rect"), "AnulAnul")
        self.assertEqual(Embedded._face_pair_type("Rect", "Anul"), "AnulAnul")
        self.assertEqual(Embedded._face_pair_type("Anul", None), "AnulAnul")
        self.assertEqual(Embedded._face_pair_type(None, "Anul"), "AnulAnul")

    def test_joint_face_pairs_use_stored_fem_joint_references_before_geometry_search(self):
        Embedded = self._load_embedded_module_for_app_test()
        document = App.newDocument("MbDFEMStoredJointFacePairsTest")

        try:
            pin = document.addObject("MbDFEM::MbDPart", "Pin")
            pin.Shape = Part.makeCylinder(1.0, 2.0)
            block = document.addObject("MbDFEM::MbDPart", "Block")
            block.Shape = Part.makeBox(4.0, 4.0, 2.0, App.Vector(-2.0, -2.0, 0.0)).cut(
                Part.makeCylinder(1.0, 2.0)
            )
            pin_face_index = next(
                index
                for index, face in enumerate(pin.Shape.Faces, start=1)
                if getattr(face.Surface, "TypeId", None) == "Part::GeomCylinder"
            )
            hole_face_index = next(
                index
                for index, face in enumerate(block.Shape.Faces, start=1)
                if getattr(face.Surface, "TypeId", None) == "Part::GeomCylinder"
            )

            marker_i = document.addObject("MbDFEM::MbDMarker", "MarkerI")
            marker_j = document.addObject("MbDFEM::MbDMarker", "MarkerJ")
            pin.addMarker(marker_i)
            block.addMarker(marker_j)
            joint = document.addObject("MbDFEM::MbDJoint", "Joint")
            joint.markerI = marker_i
            joint.markerJ = marker_j
            fem_joint = document.addObject("MbDFEM::FEMJoint", "FEMJoint")
            fem_joint.mbdItem = joint
            face_pair = document.addObject("MbDFEM::CylCylFacePair", "CylCylFacePair")
            face_pair.faceI = (pin, ["Face{}".format(pin_face_index)])
            face_pair.faceJ = (block, ["Face{}".format(hole_face_index)])
            fem_joint.facePairs = [face_pair]

            # A placement-based touching-face search cannot find this pair.
            pin.Placement.Base = App.Vector(100, 0, 0)
            document.recompute()

            pairs = Embedded._joint_face_pairs(joint)

            self.assertEqual(len(pairs), 1)
            self.assertEqual(pairs[0]["type"], "CylCyl")
            self.assertEqual(pairs[0]["subNameI"], "Face{}".format(pin_face_index))
            self.assertEqual(pairs[0]["subNameJ"], "Face{}".format(hole_face_index))
        finally:
            App.closeDocument(document.Name)

    def test_joint_face_pair_is_anchored_to_marker_faces(self):
        Embedded = self._load_embedded_module_for_app_test()
        document = App.newDocument("MbDFEMMarkerAnchoredFacePairTest")

        try:
            pin = document.addObject("MbDFEM::MbDPart", "Pin")
            pin.Shape = Part.makeCylinder(1.0, 2.0)
            block = document.addObject("MbDFEM::MbDPart", "Block")
            block.Shape = Part.makeBox(4.0, 4.0, 2.0, App.Vector(-2.0, -2.0, 0.0)).cut(
                Part.makeCylinder(1.0, 2.0)
            )
            pin_face_index = next(
                index
                for index, face in enumerate(pin.Shape.Faces, start=1)
                if getattr(face.Surface, "TypeId", None) == "Part::GeomCylinder"
            )
            hole_face_index = next(
                index
                for index, face in enumerate(block.Shape.Faces, start=1)
                if getattr(face.Surface, "TypeId", None) == "Part::GeomCylinder"
            )
            pin_plane_index = next(
                index
                for index, face in enumerate(pin.Shape.Faces, start=1)
                if getattr(face.Surface, "TypeId", None) == "Part::GeomPlane"
            )
            block_plane_index = next(
                index
                for index, face in enumerate(block.Shape.Faces, start=1)
                if getattr(face.Surface, "TypeId", None) == "Part::GeomPlane"
            )

            marker_i = document.addObject("MbDFEM::MbDMarker", "MarkerI")
            marker_j = document.addObject("MbDFEM::MbDMarker", "MarkerJ")
            pin.addMarker(marker_i)
            block.addMarker(marker_j)
            marker_i.Geometry = (pin, ["Face{}".format(pin_face_index)])
            marker_j.Geometry = (block, ["Face{}".format(hole_face_index)])
            joint = document.addObject("MbDFEM::MbDJoint", "Joint")
            joint.markerI = marker_i
            joint.markerJ = marker_j
            fem_joint = document.addObject("MbDFEM::FEMJoint", "FEMJoint")
            fem_joint.mbdItem = joint
            # A stale stored pair that does not contain the marker faces must
            # not be reused.
            stale_pair = document.addObject("MbDFEM::RectRectFacePair", "StaleFacePair")
            stale_pair.faceI = (pin, ["Face{}".format(pin_plane_index)])
            stale_pair.faceJ = (block, ["Face{}".format(block_plane_index)])
            fem_joint.facePairs = [stale_pair]
            document.recompute()

            pairs = Embedded._joint_face_pairs(joint)

            self.assertEqual(len(pairs), 1)
            self.assertEqual(pairs[0]["type"], "CylCyl")
            self.assertEqual(pairs[0]["subNameI"], "Face{}".format(pin_face_index))
            self.assertEqual(pairs[0]["subNameJ"], "Face{}".format(hole_face_index))
            self.assertEqual(len(fem_joint.facePairs), 1)
            face_pair = fem_joint.facePairs[0]
            self.assertEqual(face_pair.TypeId, "MbDFEM::CylCylFacePair")
            self.assertEqual(face_pair.faceI, (pin, ("Face{}".format(pin_face_index),)))
            self.assertEqual(face_pair.faceJ, (block, ("Face{}".format(hole_face_index),)))
        finally:
            App.closeDocument(document.Name)

    def test_face_pair_document_objects_save_and_reopen(self):
        document = App.newDocument("MbDFEMFacePairPersistenceTest")
        fd, file_name = tempfile.mkstemp(suffix=".FCStd")
        os.close(fd)

        try:
            part_i = document.addObject("MbDFEM::MbDPart", "PartI")
            part_j = document.addObject("MbDFEM::MbDPart", "PartJ")
            part_i.Shape = Part.makeCylinder(1.0, 2.0)
            part_j.Shape = Part.makeCylinder(1.0, 2.0)
            face_pair = document.addObject("MbDFEM::CylCylFacePair", "FacePair")
            face_pair.faceI = (part_i, ["Face1"])
            face_pair.faceJ = (part_j, ["Face1"])
            fem_joint = document.addObject("MbDFEM::FEMJoint", "FEMJoint")
            fem_joint.facePairs = [face_pair]
            document.recompute()
            document.saveAs(file_name)
            App.closeDocument(document.Name)

            reopened = App.openDocument(file_name)
            reopened_pair = reopened.getObject("FacePair")
            reopened_joint = reopened.getObject("FEMJoint")

            self.assertEqual(reopened_pair.TypeId, "MbDFEM::CylCylFacePair")
            self.assertTrue(reopened_pair.isDerivedFrom("MbDFEM::FacePair"))
            self.assertEqual(reopened_pair.faceI[1], ("Face1",))
            self.assertEqual(reopened_pair.faceJ[1], ("Face1",))
            self.assertEqual(reopened_joint.facePairs, [reopened_pair])
        finally:
            if App.ActiveDocument is not None and App.ActiveDocument.Name == document.Name:
                App.closeDocument(document.Name)
            if os.path.exists(file_name):
                os.remove(file_name)

    def test_cyl_cyl_face_pair_roles_identify_hole_and_pin(self):
        Embedded = self._load_embedded_module_for_app_test()

        pin = Part.makeCylinder(1.0, 2.0)
        block = Part.makeBox(4.0, 4.0, 2.0, App.Vector(-2.0, -2.0, 0.0))
        hole = block.cut(pin)
        pin_face = next(
            face for face in pin.Faces if getattr(face.Surface, "TypeId", None) == "Part::GeomCylinder"
        )
        hole_face = next(
            face for face in hole.Faces if getattr(face.Surface, "TypeId", None) == "Part::GeomCylinder"
        )

        self.assertEqual(Embedded._cylindrical_face_role(pin_face), "pin")
        self.assertEqual(Embedded._cylindrical_face_role(hole_face), "hole")
        roles = Embedded._cyl_cyl_face_pair_roles(pin_face, hole_face)
        self.assertIs(roles["hole"], hole_face)
        self.assertIs(roles["pin"], pin_face)
        self.assertEqual(roles["holeSide"], "J")
        self.assertEqual(roles["pinSide"], "I")


    def test_joint_side_load_minimum_norm_solver_skips_singular_constraints(self):
        Embedded = self._load_embedded_module_for_app_test()

        self.assertIsNone(
            Embedded._solve_minimum_norm_constraints(
                [
                    [1.0, 1.0, 1.0, 1.0],
                    [2.0, 2.0, 2.0, 2.0],
                    [0.0, 0.0, 0.0, 0.0],
                ],
                [80.0, 0.0, 0.0],
            )
        )

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

    def test_results_panel_uses_global_scalar_range_for_result_series(self):
        document = App.newDocument("MbDFEMGlobalResultRangeTest")

        try:
            fem_part = document.addObject("MbDFEM::FEMPart", "FEMPart")
            result_0 = document.addObject("Fem::FemResultObjectPython", "CCX_Results_0")
            result_1 = document.addObject("Fem::FemResultObjectPython", "CCX_Results_1")
            result_0.vonMises = [2.0, 4.0, 8.0]
            result_1.vonMises = [1.0, 10.0, 6.0]
            fem_part.results = [result_0, result_1]

            self.assertEqual(
                FreeCADMbDFEMResultsPanel._global_pipeline_scalar_range(
                    fem_part,
                    "von Mises Stress",
                ),
                (1.0e6, 10.0e6),
            )
        finally:
            App.closeDocument(document.Name)

    def test_results_panel_display_field_labels_include_post_pipeline_units(self):
        self.assertEqual(
            FreeCADMbDFEMResultsPanel._pipeline_field_display_label("von Mises Stress"),
            "von Mises Stress [Pa]",
        )
        self.assertEqual(
            FreeCADMbDFEMResultsPanel._pipeline_field_display_label("Stress xx component"),
            "Stress xx component [Pa]",
        )
        self.assertEqual(
            FreeCADMbDFEMResultsPanel._pipeline_field_display_label("Displacement Magnitude"),
            "Displacement Magnitude [m]",
        )
        self.assertEqual(
            FreeCADMbDFEMResultsPanel._pipeline_field_display_label("Temperature"),
            "Temperature",
        )

    def test_results_panel_displays_asmt_input_state_time_as_input(self):
        class Assembly:
            times = [-sys.float_info.max, 0.0, 0.1]

        class FEMPart:
            pass

        fem_part = FEMPart()
        original_owning_assembly = FreeCADMbDFEMResultsPanel.owning_mbd_assembly

        try:
            FreeCADMbDFEMResultsPanel.owning_mbd_assembly = lambda obj: Assembly()

            self.assertEqual(FreeCADMbDFEMResultsPanel._state_time(fem_part, 0), -sys.float_info.max)
            self.assertEqual(FreeCADMbDFEMResultsPanel._state_time_text(fem_part, 0), "Input")
            self.assertEqual(FreeCADMbDFEMResultsPanel._state_label_time_text(fem_part, 0), "Input")
            self.assertEqual(FreeCADMbDFEMResultsPanel._state_time_text(fem_part, 1), "0 s")
            self.assertEqual(FreeCADMbDFEMResultsPanel._state_label_time_text(fem_part, 2), "0.1s")
            self.assertEqual(FreeCADMbDFEMEmbedded._solver_state_time_text(fem_part, 0), "Input")
        finally:
            FreeCADMbDFEMResultsPanel.owning_mbd_assembly = original_owning_assembly

    def test_results_panel_field_combo_refreshes_legend_for_selected_raw_field(self):
        class FakeEnumProperty:
            def __init__(self, names, value):
                self.names = list(names)
                self.value = value

            def getEnumVector(self):
                return self.names

            def getValueAsString(self):
                return self.value

            def setValue(self, value):
                if isinstance(value, int):
                    self.value = self.names[value]
                    return
                if value not in self.names:
                    raise ValueError(value)
                self.value = value

        class FakeViewObject:
            def __init__(self):
                self.Field = FakeEnumProperty(
                    ["None", "Displacement Magnitude", "von Mises Stress"],
                    "von Mises Stress",
                )
                self.Component = FakeEnumProperty(["Not a vector"], "Not a vector")

            def updateMaterial(self):
                pass

            def updateColorBars(self):
                pass

        class FakePipeline:
            def __init__(self):
                self.ViewObject = FakeViewObject()

        class FakeCombo:
            def __init__(self):
                self._items = ["None", "Displacement Magnitude", "von Mises Stress"]
                self._data = {}
                self._current_index = 1

            def objectName(self):
                return "Field"

            def count(self):
                return len(self._items)

            def itemText(self, index):
                return self._items[index]

            def setItemText(self, index, text):
                self._items[index] = text

            def itemData(self, index, role):
                return self._data.get((index, role))

            def setItemData(self, index, value, role):
                self._data[(index, role)] = value

            def currentIndex(self):
                return self._current_index

            def currentText(self):
                return self._items[self._current_index]

        class FakeFemPart:
            pass

        class FakeLabel:
            def __init__(self):
                self.text = ""

            def setText(self, text):
                self.text = text

        panel = FreeCADMbDFEMResultsPanel.FEMResultsTaskPanel.__new__(
            FreeCADMbDFEMResultsPanel.FEMResultsTaskPanel
        )
        pipeline = FakePipeline()
        fem_part = FakeFemPart()
        fem_part.visual = pipeline
        panel.fem_part = fem_part
        panel._playback_color_range = (1.0, 2.0)
        panel._playback_color_field = "von Mises Stress"
        panel.field_label = FakeLabel()
        combo = FakeCombo()
        refreshed_fields = []
        scheduled_fields = []

        original_refresh = FreeCADMbDFEMResultsPanel._refresh_pipeline_fixed_color_range
        original_schedule = FreeCADMbDFEMResultsPanel._schedule_pipeline_fixed_color_range_refresh
        original_global_range = FreeCADMbDFEMResultsPanel._global_pipeline_scalar_range

        try:
            FreeCADMbDFEMResultsPanel._decorate_pipeline_field_combo(combo)

            def refresh(fem_part_arg, pipeline_arg, value_range=None):
                refreshed_fields.append(
                    (
                        FreeCADMbDFEMResultsPanel._pipeline_field_name(pipeline_arg),
                        value_range,
                    )
                )

            def schedule(fem_part_arg, pipeline_arg, value_range=None):
                scheduled_fields.append(
                    (
                        FreeCADMbDFEMResultsPanel._pipeline_field_name(pipeline_arg),
                        value_range,
                    )
                )

            FreeCADMbDFEMResultsPanel._refresh_pipeline_fixed_color_range = refresh
            FreeCADMbDFEMResultsPanel._schedule_pipeline_fixed_color_range_refresh = schedule
            FreeCADMbDFEMResultsPanel._global_pipeline_scalar_range = (
                lambda fem_part_arg, field: (0.1, 0.2)
                if field == "Displacement Magnitude"
                else (100.0, 200.0)
            )

            panel._set_pipeline_from_task_panel(combo)

            self.assertEqual(
                FreeCADMbDFEMResultsPanel._pipeline_field_name(pipeline),
                "Displacement Magnitude",
            )
            self.assertEqual(refreshed_fields, [("Displacement Magnitude", (0.1, 0.2))])
            self.assertEqual(scheduled_fields, [("Displacement Magnitude", (0.1, 0.2))])
            self.assertIsNone(panel._playback_color_range)
            self.assertEqual(panel._playback_color_field, "")
            self.assertEqual(panel._selected_pipeline_field, "Displacement Magnitude")
            self.assertEqual(panel.field_label.text, "Field: Displacement Magnitude [m]")
            self.assertEqual(combo.itemText(1), "Displacement Magnitude [m]")
        finally:
            FreeCADMbDFEMResultsPanel._refresh_pipeline_fixed_color_range = original_refresh
            FreeCADMbDFEMResultsPanel._schedule_pipeline_fixed_color_range_refresh = original_schedule
            FreeCADMbDFEMResultsPanel._global_pipeline_scalar_range = original_global_range

    def test_results_panel_field_combo_reads_decorated_field_label_as_raw_field(self):
        class FakeCombo:
            def __init__(self):
                self._items = ["None", "Displacement Magnitude [m]", "von Mises Stress [Pa]"]
                self._data = {}
                self._current_index = 1

            def count(self):
                return len(self._items)

            def itemText(self, index):
                return self._items[index]

            def setItemText(self, index, text):
                self._items[index] = text

            def itemData(self, index, role):
                return self._data.get((index, role))

            def setItemData(self, index, value, role):
                self._data[(index, role)] = value

            def currentIndex(self):
                return self._current_index

            def currentText(self):
                return self._items[self._current_index]

        combo = FakeCombo()

        FreeCADMbDFEMResultsPanel._decorate_pipeline_field_combo(combo)

        self.assertEqual(
            FreeCADMbDFEMResultsPanel._pipeline_field_combo_value(combo),
            "Displacement Magnitude",
        )
        self.assertEqual(combo.itemText(1), "Displacement Magnitude [m]")

    def test_results_panel_clears_stale_fixed_legend_range_when_field_has_no_range(self):
        class FakeEnumProperty:
            def __init__(self, names, value):
                self.names = list(names)
                self.value = value

            def getEnumVector(self):
                return self.names

            def getValueAsString(self):
                return self.value

        class FakeViewObject:
            def __init__(self):
                self.Field = FakeEnumProperty(
                    ["None", "Displacement Magnitude", "von Mises Stress"],
                    "Displacement Magnitude",
                )
                self.UseFixedColorBarRange = True
                self.FixedColorBarMinimum = 32.0
                self.FixedColorBarMaximum = 141000.0
                self.update_material_count = 0
                self.update_color_bars_count = 0

            def setPropertyByName(self, name, value):
                setattr(self, name, value)

            def updateMaterial(self):
                self.update_material_count += 1

            def updateColorBars(self):
                self.update_color_bars_count += 1

        class FakeDocument:
            def recompute(self):
                pass

        class FakePostObject:
            def __init__(self):
                self.PropertiesList = []

            def addProperty(self, property_type, name, group, description):
                self.PropertiesList.append(name)
                setattr(self, name, None)

        class FakePipeline(FakePostObject):
            def __init__(self):
                super().__init__()
                self.ViewObject = FakeViewObject()
                self.Group = [FakePostObject()]
                self.Document = FakeDocument()

        class FakeFemPart:
            pass

        pipeline = FakePipeline()
        fem_part = FakeFemPart()
        fem_part.visual = pipeline
        pipeline.MbDFEMFixedColorBarRangeEnabled = True
        pipeline.MbDFEMFixedColorBarMinimum = 32.0
        pipeline.MbDFEMFixedColorBarMaximum = 141000.0
        pipeline.Group[0].MbDFEMFixedColorBarRangeEnabled = True
        pipeline.Group[0].MbDFEMFixedColorBarMinimum = 32.0
        pipeline.Group[0].MbDFEMFixedColorBarMaximum = 141000.0

        original_global_range = FreeCADMbDFEMResultsPanel._global_pipeline_scalar_range

        try:
            FreeCADMbDFEMResultsPanel._global_pipeline_scalar_range = lambda fem_part, field: None

            FreeCADMbDFEMResultsPanel._refresh_pipeline_fixed_color_range(fem_part, pipeline)

            self.assertFalse(pipeline.MbDFEMFixedColorBarRangeEnabled)
            self.assertFalse(pipeline.Group[0].MbDFEMFixedColorBarRangeEnabled)
            self.assertFalse(pipeline.ViewObject.UseFixedColorBarRange)
            self.assertEqual(pipeline.ViewObject.update_material_count, 1)
            self.assertEqual(pipeline.ViewObject.update_color_bars_count, 1)
        finally:
            FreeCADMbDFEMResultsPanel._global_pipeline_scalar_range = original_global_range

    def test_results_panel_global_scalar_range_skips_input_state_for_series(self):
        document = App.newDocument("MbDFEMGlobalResultRangeSkipsInputStateTest")

        try:
            assembly = document.addObject("MbDFEM::MbDAssembly", "Assembly")
            part = document.addObject("MbDFEM::MbDPart", "Part")
            fem_part = document.addObject("MbDFEM::FEMPart", "FEMPart")
            result_0 = document.addObject("Fem::FemResultObjectPython", "CCX_Results_0")
            result_1 = document.addObject("Fem::FemResultObjectPython", "CCX_Results_1")
            result_2 = document.addObject("Fem::FemResultObjectPython", "CCX_Results_2")
            assembly.addPart(part)
            fem_part.mbdItem = part
            assembly.times = [0.0, 0.1, 0.2]
            part.xs = [0.0, 1.0, 2.0]
            result_0.vonMises = [100.0, 200.0]
            result_1.vonMises = [2.0, 4.0]
            result_2.vonMises = [3.0, 5.0]
            FreeCADMbDFEMResultsPanel._set_result_state_metadata(fem_part, result_0, 0)
            FreeCADMbDFEMResultsPanel._set_result_state_metadata(fem_part, result_1, 1)
            FreeCADMbDFEMResultsPanel._set_result_state_metadata(fem_part, result_2, 2)
            fem_part.results = [result_0, result_1, result_2]

            self.assertEqual(
                FreeCADMbDFEMResultsPanel._global_pipeline_scalar_range(
                    fem_part,
                    "von Mises Stress",
                ),
                (2.0e6, 5.0e6),
            )
        finally:
            App.closeDocument(document.Name)

    def test_results_panel_frd_range_scan_skips_input_state_for_series(self):
        document = App.newDocument("MbDFEMFrdRangeSkipsInputStateTest")
        original_frd_file_for_state = FreeCADMbDFEMResultsPanel._frd_file_for_state
        original_frd_scalar_range = FreeCADMbDFEMResultsPanel._frd_scalar_range

        try:
            assembly = document.addObject("MbDFEM::MbDAssembly", "Assembly")
            part = document.addObject("MbDFEM::MbDPart", "Part")
            fem_part = document.addObject("MbDFEM::FEMPart", "FEMPart")
            assembly.addPart(part)
            fem_part.mbdItem = part
            assembly.times = [0.0, 0.1, 0.2]
            part.xs = [0.0, 1.0, 2.0]
            scanned_states = []

            def frd_file_for_state(runner_fem_part, state_index):
                self.assertIs(runner_fem_part, fem_part)
                return state_index

            def frd_scalar_range(state_index, field_name):
                self.assertEqual(field_name, "von Mises Stress")
                scanned_states.append(state_index)
                return (float(state_index), float(state_index + 10))

            FreeCADMbDFEMResultsPanel._frd_file_for_state = frd_file_for_state
            FreeCADMbDFEMResultsPanel._frd_scalar_range = frd_scalar_range

            self.assertEqual(
                FreeCADMbDFEMResultsPanel._solved_frd_scalar_ranges(
                    fem_part,
                    "von Mises Stress",
                ),
                [(1.0, 11.0), (2.0, 12.0)],
            )
            self.assertEqual(scanned_states, [1, 2])
        finally:
            FreeCADMbDFEMResultsPanel._frd_file_for_state = original_frd_file_for_state
            FreeCADMbDFEMResultsPanel._frd_scalar_range = original_frd_scalar_range
            App.closeDocument(document.Name)

    def test_results_panel_default_start_state_skips_input_state_when_available(self):
        self.assertEqual(FreeCADMbDFEMResultsPanel._default_results_panel_start_state(0), 0)
        self.assertEqual(FreeCADMbDFEMResultsPanel._default_results_panel_start_state(1), 1)
        self.assertEqual(FreeCADMbDFEMResultsPanel._default_results_panel_start_state(12), 1)

    def test_results_panel_reads_von_mises_range_from_frd_result_sets(self):
        result_set = {
            "stress": {
                1: (10.0, 10.0, 10.0, 0.0, 0.0, 0.0),
                2: (10.0, 0.0, 0.0, 0.0, 0.0, 0.0),
            },
        }

        self.assertEqual(
            FreeCADMbDFEMResultsPanel._finite_min_max(
                FreeCADMbDFEMResultsPanel._frd_scalar_values_for_result_set(
                    result_set,
                    "von Mises Stress",
                )
            ),
            (0.0, 10.0),
        )

    def test_results_panel_frd_range_scan_does_not_create_frame_directories(self):
        document = App.newDocument("MbDFEMRangeScanNoFrameDirCreateTest")

        try:
            fem_part = document.addObject("MbDFEM::FEMPart", "FEMPart")
            frame_dir = FreeCADMbDBackend.calculix_working_dir_path(fem_part, 26)
            self.assertFalse(frame_dir.exists())

            self.assertIsNone(FreeCADMbDFEMResultsPanel._frd_scalar_range(
                FreeCADMbDFEMResultsPanel._frd_file_for_state(fem_part, 26),
                "von Mises Stress",
            ))
            self.assertFalse(frame_dir.exists())
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

    def test_fem_part_calculix_panel_state_properties_save_and_reopen(self):
        embedded = self._load_embedded_module_for_app_test()

        with tempfile.TemporaryDirectory() as directory:
            filename = os.path.join(directory, "CalculixPanelState.FCStd")
            document = App.newDocument("MbDFEMCalculixPanelStateTest")
            try:
                fem_part = document.addObject("MbDFEM::FEMPart", "FEMPart")
                embedded._set_solver_panel_state(fem_part, "current", 8)
                embedded._set_solver_panel_state(fem_part, "start", 4)
                embedded._set_solver_panel_state(fem_part, "end", 8)

                self.assertIn("MbDFEMSolverPanelCurrentState", fem_part.PropertiesList)
                self.assertIn("MbDFEMSolverPanelStartState", fem_part.PropertiesList)
                self.assertIn("MbDFEMSolverPanelEndState", fem_part.PropertiesList)
                self.assertEqual(fem_part.MbDFEMSolverPanelCurrentState, 8)
                self.assertEqual(fem_part.MbDFEMSolverPanelStartState, 4)
                self.assertEqual(fem_part.MbDFEMSolverPanelEndState, 8)

                document.saveAs(filename)
            finally:
                App.closeDocument(document.Name)

            reopened = App.openDocument(filename)
            try:
                fem_part = reopened.getObject("FEMPart")
                self.assertEqual(fem_part.MbDFEMSolverPanelCurrentState, 8)
                self.assertEqual(fem_part.MbDFEMSolverPanelStartState, 4)
                self.assertEqual(fem_part.MbDFEMSolverPanelEndState, 8)
            finally:
                App.closeDocument(reopened.Name)

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

    def test_fem_part_import_state_reuses_existing_calculix_result(self):
        Embedded = self._load_embedded_module_for_app_test()
        document = App.newDocument("MbDFEMImportStateResultTest")

        try:
            with tempfile.TemporaryDirectory() as directory:
                document.saveAs(os.path.join(directory, "MyAssembly.FCStd"))

                assembly = document.addObject("MbDFEM::MbDAssembly", "Assembly")
                part = document.addObject("MbDFEM::MbDPart", "MbDPart001")
                fem_part = document.addObject("MbDFEM::FEMPart", "FEMPart")
                solver = document.addObject("Fem::FemSolverObjectPython", "Calculix")
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

                original_tools = Embedded.FEMPartCcxTools
                try:
                    Embedded.FEMPartCcxTools = FakeCcxTools
                    result = FreeCADMbDFEMResultsPanel.import_fem_part_state(fem_part, 1)
                finally:
                    Embedded.FEMPartCcxTools = original_tools

                self.assertEqual(calls["working_dir"], str(working_dir))
                self.assertEqual(calls["base_name"], FreeCADMbDBackend.CALCULIX_BASE_NAME)
                self.assertEqual(calls["inp_file_name"], str(working_dir / "calculix.inp"))
                self.assertEqual(result.MbDFEMStateIndex, 1)
                self.assertAlmostEqual(result.MbDFEMStateTime, 0.25)
                self.assertEqual(fem_part.results, [result])
        finally:
            App.closeDocument(document.Name)

    def test_fem_part_reimport_state_prunes_foreign_tree_links(self):
        document = App.newDocument("MbDFEMReimportStateTreeLinksTest")

        try:
            fem_part = document.addObject("MbDFEM::FEMPart", "FEMPart")
            actions = document.addObject("App::DocumentObjectGroup", "Actions")
            old_result = document.addObject("Fem::FemResultObjectPython", "OldImportedResult")
            new_result = document.addObject("Fem::FemResultObjectPython", "NewImportedResult")
            old_name = old_result.Name
            new_name = new_result.Name

            FreeCADMbDFEMResultsPanel._set_result_state_metadata(fem_part, old_result, 1)
            fem_part.results = [old_result]
            fem_part.synchronizeResultsFolder()
            actions.addObject(old_result)
            actions.addObject(new_result)

            assigned = FreeCADMbDFEMResultsPanel._assign_result_for_state(
                fem_part,
                1,
                new_result,
                base_results=[old_result],
            )

            self.assertIs(assigned, new_result)
            self.assertEqual(fem_part.results, [new_result])
            self.assertEqual(list(fem_part.getResultsFolder().Group), [new_result])
            self.assertNotIn(new_result, list(actions.Group))
            self.assertIsNone(document.getObject(old_name))
            self.assertIs(document.getObject(new_name), new_result)
        finally:
            App.closeDocument(document.Name)

    def test_fem_part_ccx_dat_results_are_not_tracked_as_document_objects(self):
        Embedded = self._load_embedded_module_for_app_test()
        import feminout.importCcxDatResults as importCcxDatResults

        document = App.newDocument("MbDFEMNoCcxDatFileDocumentObjectTest")
        original_import_dat = importCcxDatResults.import_dat

        try:
            fem_part = document.addObject("MbDFEM::FEMPart", "FEMPart")
            solver = document.addObject("Fem::FemSolverObjectPython", "Calculix")
            result = document.addObject("Fem::FemResultObjectPython", "CCX_Results")
            stale_dat = document.addObject("App::TextDocument", "ccx_dat_file")
            fem_part.solver = solver
            fem_part.results = [result]
            result.Eigenmode = 1
            stale_dat.Text = "previous CalculiX dat contents"

            with tempfile.TemporaryDirectory() as directory:
                inp_file = Path(directory) / "calculix.inp"
                dat_file = Path(directory) / "calculix.dat"
                inp_file.write_text("", encoding="utf-8")
                dat_file.write_text("CalculiX dat contents should stay on disk only", encoding="utf-8")

                def import_dat(dat_file_name, analysis=None):
                    self.assertEqual(dat_file_name, str(dat_file))
                    return [{"eigenmode": 1, "frequency": 42.5}]

                importCcxDatResults.import_dat = import_dat
                fea = Embedded.FEMPartCcxTools(fem_part, solver)
                fea.inp_file_name = str(inp_file)
                fea.load_results_ccxdat()

            self.assertAlmostEqual(result.EigenmodeFrequency, 42.5)
            self.assertFalse(
                [
                    obj
                    for obj in document.Objects
                    if obj.Name.startswith("ccx_dat_file")
                    or obj.isDerivedFrom("App::TextDocument")
                ]
            )
        finally:
            importCcxDatResults.import_dat = original_import_dat
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
                gravity.gravity = App.Vector(0, -9810.0, 0)
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
                animation_parameters.currentFrame = 8
                animation_parameters.startFrame = 2
                animation_parameters.endFrame = 10
                animation_parameters.playbackSpeed = 0.5
                animation_parameters.lengthScale = 4.0
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
                self.assertEqual(gravity.gravity, App.Vector(0, -9810.0, 0))
                self.assertEqual(simulation_parameters.endTime, 2.5)
                self.assertEqual(simulation_parameters.maxStepSize, 0.002)
                self.assertEqual(simulation_parameters.minStepSize, 1.0e-10)
                self.assertEqual(simulation_parameters.significantDigits, 8)
                self.assertEqual(simulation_parameters.maxIterations, 250)
                self.assertEqual(simulation_parameters.outputInterval, 0.02)
                self.assertEqual(animation_parameters.updateRate, 60)
                self.assertEqual(animation_parameters.currentFrame, 8)
                self.assertEqual(animation_parameters.startFrame, 2)
                self.assertEqual(animation_parameters.endFrame, 10)
                self.assertEqual(animation_parameters.playbackSpeed, 0.5)
                self.assertEqual(animation_parameters.lengthScale, 4.0)
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

    def test_part_fuses_multi_solid_compound_shape(self):
        document = App.newDocument("MbDFEMMassMarkerCompoundShapeTest")

        try:
            first = Part.makeBox(10, 10, 10)
            second = Part.makeBox(10, 10, 10, App.Vector(5, 0, 0))
            compound = Part.makeCompound([first, second])
            part = document.addObject("MbDFEM::MbDPart", "Part")

            part.Shape = compound

            marker = part.getMassMarker()
            self.assertEqual(part.Shape.ShapeType, "Solid")
            self.assertEqual(len(part.Shape.Solids), 1)
            self.assertAlmostEqual(part.Shape.Volume, 1500.0)
            self.assertIsNotNone(marker)
            self.assertTrue(marker.massMarkerFromShape)
            self.assertAlmostEqual(marker.mass, 1.5e-6)
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

    def test_freecadmbd_exporter_writes_asmt_length_quantities_in_si_units(self):
        with tempfile.TemporaryDirectory() as directory:
            document = App.newDocument("MbDFEMExportSIUnitsTest")

            try:
                assembly = document.addObject("MbDFEM::MbDAssembly", "Assembly")
                part = document.addObject("MbDFEM::MbDPart", "Part")
                marker = document.addObject("MbDFEM::MbDMarker", "Marker")
                mass_marker = part.ensureMassMarker()
                gravity = assembly.ensureGravity()

                part.Placement.Base = App.Vector(1200, 2300, 3400)
                part.velocity = App.Vector(4500, 5600, 6700)
                marker.Placement.Base = App.Vector(80, 90, 100)
                mass_marker.Placement.Base = App.Vector(110, 120, 130)
                mass_marker.material.setPhysicalValue("Density", "7850 kg/m^3")
                gravity.gravity = App.Vector(0, -9810.0, 0)
                assembly.addPart(part)
                part.addMarker(marker)

                filename = os.path.join(directory, "assembly.asmt")
                FreeCADMbDExporter.export_assembly(assembly, filename)
                with open(filename, encoding="utf-8") as file:
                    exported = file.read()

                self.assertIn("\t\t\t1.2\t2.3\t3.4\t\n", exported)
                self.assertIn("\t\t\t4.5\t5.6\t6.7\t\n", exported)
                self.assertIn("\t\t\t\t0.11\t0.12\t0.13\t\n", exported)
                self.assertIn("\t\t\t\t\t0.08\t0.09\t0.1\t\n", exported)
                self.assertIn("\t\tDensity\n\t\t\t7850\n", exported)
                self.assertIn("\tConstantGravity\n\t\t0\t-9.81\t0\t\n", exported)
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
                self.assertEqual(assembly.xs, [0.0, 1000.0, 2000.0, 3000.0])
                self.assertEqual(assembly.ys, [0.0, 4000.0, 5000.0, 6000.0])
                self.assertEqual(assembly.alpzs, [0.0, 7.0, 8.0, 9.0])
                self.assertEqual(part.xs, [0.0, 10000.0, 11000.0, 12000.0])
                self.assertEqual(part.zs, [0.0, 13000.0, 14000.0, 15000.0])
                self.assertEqual(part.omeys, [0.0, 16.0, 17.0, 18.0])
                self.assertEqual(joint.fxs, [0.0, 20.0, 21.0, 22.0])
                self.assertEqual(joint.fys, [0.0, 23.0, 24.0, 25.0])
                self.assertEqual(joint.fzs, [0.0, 26.0, 27.0, 28.0])
                self.assertEqual(joint.txs, [0.0, 29.0, 30.0, 31.0])
                self.assertEqual(joint.tys, [0.0, 32.0, 33.0, 34.0])
                self.assertEqual(joint.tzs, [0.0, 35.0, 36.0, 37.0])
            finally:
                App.closeDocument(document.Name)

    def test_freecadmbd_result_import_converts_asmt_si_length_quantities_to_document_units(self):
        with tempfile.TemporaryDirectory() as directory:
            document = App.newDocument("MbDFEMSolvedSIUnitsImportTest")

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
                                "Time\tInput\t0",
                                "PartSeries\t/Assembly/Part",
                                "X\t0\t1.2",
                                "VX\t0\t2.3",
                                "AX\t0\t4.5",
                                "OmegaX\t0\t6.7",
                                "AlphaX\t0\t8.9",
                                "RevoluteJointSeries\t/Assembly/Joint",
                                "FXonI\t0\t10.1",
                                "TXonI\t0\t11.2",
                                "",
                            ]
                        )
                    )

                imported = FreeCADMbDResults.import_results(assembly, result_file)

                self.assertEqual(imported, [part, joint])
                self.assertEqual(assembly.times, [-sys.float_info.max, 0.0])
                self.assertEqual(part.xs, [0.0, 1200.0])
                self.assertEqual(part.vxs, [0.0, 2300.0])
                self.assertEqual(part.axs, [0.0, 4500.0])
                self.assertEqual(part.omexs, [0.0, 6.7])
                self.assertEqual(part.alpxs, [0.0, 8.9])
                self.assertEqual(joint.fxs, [0.0, 10.1])
                self.assertEqual(joint.txs, [0.0, 11.2])
            finally:
                App.closeDocument(document.Name)

    def test_freecadmbd_animation_controller_scrubs_part_results(self):
        document = App.newDocument("MbDFEMAnimationScrubTest")

        try:
            assembly = document.addObject("MbDFEM::MbDAssembly", "Assembly")
            part = document.addObject("MbDFEM::MbDPart", "Part")
            assembly.addPart(part)
            assembly.times = [0.0, 0.5, 1.0]
            part.xs = [0.0, 500.0, 1000.0]
            part.ys = [1000.0, 1500.0, 2000.0]
            part.zs = [2000.0, 2500.0, 3000.0]
            part.vxs = [4000.0, 4500.0, 5000.0]
            part.vys = [5000.0, 5500.0, 6000.0]
            part.vzs = [6000.0, 6500.0, 7000.0]
            part.omexs = [7.0, 7.5, 8.0]
            part.omeys = [8.0, 8.5, 9.0]
            part.omezs = [9.0, 9.5, 10.0]
            part.axs = [10000.0, 10500.0, 11000.0]
            part.ays = [11000.0, 11500.0, 12000.0]
            part.azs = [12000.0, 12500.0, 13000.0]
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
            self.assertEqual(part.acceleration, App.Vector(10250.0, 11250.0, 12250.0))
            self.assertEqual(part.alpha, App.Vector(13.25, 14.25, 15.25))
            self.assertEqual(controller.current_frame, 0)

            controller.stepForward()

            self.assertEqual(controller.current_frame, 1)
            self.assertAlmostEqual(controller.current_time, 0.5)
            self.assertAlmostEqual(part.Placement.Base.x, 500.0)
        finally:
            App.closeDocument(document.Name)

    def test_free_body_diagram_scales_to_motion_bounding_box(self):
        document = App.newDocument("MbDFEMFreeBodyDiagramTest")

        try:
            assembly = document.addObject("MbDFEM::MbDAssembly", "Assembly")
            part = document.addObject("MbDFEM::MbDPart", "Part")
            second_part = document.addObject("MbDFEM::MbDPart", "SecondPart")
            marker = document.addObject("MbDFEM::MbDMarker", "Marker")
            second_marker = document.addObject("MbDFEM::MbDMarker", "SecondMarker")
            joint = document.addObject("MbDFEM::MbDJoint", "Joint")
            second_joint = document.addObject("MbDFEM::MbDJoint", "SecondJoint")
            mass_marker = part.ensureMassMarker()
            gravity = assembly.ensureGravity()

            part.Shape = Part.makeBox(3, 4, 12)
            second_part.Shape = Part.makeBox(3, 4, 12)
            mass_marker.Placement = App.Placement(App.Vector(0, 0, 1000), App.Rotation())
            mass_marker.mass = 5.0
            mass_marker.principalInertias = App.Vector(2, 3, 4)
            gravity.gravity = App.Vector(0, 0, -3000.0)
            part.addMarker(marker)
            second_part.addMarker(second_marker)
            assembly.addPart(part)
            assembly.addPart(second_part)
            assembly.addJoint(joint)
            assembly.addJoint(second_joint)
            joint.markerI = marker
            second_joint.markerI = second_marker
            assembly.joints = []

            assembly.times = [0.0, 1.0]
            part.xs = [0.0, 0.0]
            part.ys = [0.0, 0.0]
            part.zs = [0.0, 0.0]
            second_part.xs = [0.0, 0.0]
            second_part.ys = [0.0, 0.0]
            second_part.zs = [0.0, 0.0]
            part.axs = [1000.0, 2000.0]
            part.ays = [0.0, 0.0]
            part.azs = [0.0, 0.0]
            part.alpxs = [0.0, 0.0]
            part.alpys = [0.0, 1.0]
            part.alpzs = [0.0, 0.0]
            second_part.axs = [0.0, 0.0]
            second_part.ays = [0.0, 0.0]
            second_part.azs = [0.0, 0.0]
            joint.fxs = [0.0, 26.0]
            joint.fys = [0.0, 0.0]
            joint.fzs = [0.0, 0.0]
            joint.txs = [0.0, 0.0]
            joint.tys = [0.0, 0.0]
            joint.tzs = [0.0, 39.0]
            second_joint.fxs = [0.0, 52.0]
            second_joint.fys = [0.0, 0.0]
            second_joint.fzs = [0.0, 0.0]
            second_joint.txs = [0.0, 0.0]
            second_joint.tys = [0.0, 0.0]
            second_joint.tzs = [0.0, 0.0]
            document.recompute()

            force_scale, torque_scale = FreeCADMbDFreeBodyDiagram._diagram_scales(
                part,
                assembly,
            )
            vectors = FreeCADMbDFreeBodyDiagram._diagram_vectors(
                part,
                assembly,
                (1, 1, 0.0, 1),
            )

            self.assertAlmostEqual(force_scale, 1.3 / 52.0)
            self.assertAlmostEqual(torque_scale, 1.3 / 39.0)
            self.assertEqual(vectors[0].kind, "force")
            self.assertEqual(vectors[0].value, App.Vector(-15.0, 0.0, 0.0))
            self.assertEqual(vectors[2].kind, "gravity")
            self.assertEqual(vectors[2].value, App.Vector(0.0, 0.0, -15.0))
            self.assertEqual(vectors[3].kind, "force")
            self.assertEqual(vectors[3].value, App.Vector(26.0, 0.0, 0.0))
            self.assertEqual(vectors[4].kind, "torque")
            self.assertEqual(vectors[4].value, App.Vector(0.0, 0.0, 39.0))
            self.assertEqual(
                FreeCADMbDFreeBodyDiagram._scale_for_vector(
                    vectors[0].kind,
                    force_scale,
                    torque_scale,
                ),
                force_scale,
            )
            self.assertEqual(
                FreeCADMbDFreeBodyDiagram._scale_for_vector(
                    vectors[2].kind,
                    force_scale,
                    torque_scale,
                ),
                force_scale,
            )
            self.assertEqual(
                FreeCADMbDFreeBodyDiagram._scale_for_vector(
                    vectors[3].kind,
                    force_scale,
                    torque_scale,
                ),
                force_scale,
            )
            self.assertEqual(
                FreeCADMbDFreeBodyDiagram._scale_for_vector(
                    vectors[4].kind,
                    force_scale,
                    torque_scale,
                ),
                torque_scale,
            )
        finally:
            App.closeDocument(document.Name)

    def test_free_body_diagram_uses_assembly_view_scale_properties(self):
        class Assembly:
            pass

        class ViewObject:
            FreeBodyDiagramAutoScale = False
            FreeBodyDiagramForceScale = 2.5
            FreeBodyDiagramTorqueScale = 0.25

        assembly = Assembly()
        assembly.ViewObject = ViewObject()

        self.assertEqual(
            FreeCADMbDFreeBodyDiagram._diagram_scales(None, assembly),
            (2.5, 0.25),
        )

    def test_free_body_diagram_scale_is_prepared_once_for_animation(self):
        class Assembly:
            times = [0.0, 1.0]
            parts = []
            fixedparts = []

        class ViewObject:
            FreeBodyDiagramAutoScale = True
            FreeBodyDiagramForceScale = 2.5
            FreeBodyDiagramTorqueScale = 0.25

        assembly = Assembly()
        assembly.ViewObject = ViewObject()
        calls = []
        original_auto_scales = FreeCADMbDFreeBodyDiagram._assembly_auto_diagram_scales
        try:
            FreeCADMbDFreeBodyDiagram.reset_diagram_scales(assembly)
            FreeCADMbDFreeBodyDiagram._assembly_auto_diagram_scales = (
                lambda item: calls.append(item) or (10.0, 20.0)
            )

            self.assertEqual(
                FreeCADMbDFreeBodyDiagram.prepare_diagram_scales(assembly),
                (25.0, 5.0),
            )
            self.assertEqual(
                FreeCADMbDFreeBodyDiagram.prepare_diagram_scales(assembly),
                (25.0, 5.0),
            )
            self.assertEqual(calls, [assembly])

            assembly.ViewObject.FreeBodyDiagramForceScale = 10.0
            self.assertEqual(
                FreeCADMbDFreeBodyDiagram.prepare_diagram_scales(assembly),
                (100.0, 5.0),
            )
            self.assertEqual(calls, [assembly])

            controller = FreeCADMbDAnimation.AnimationController(assembly)
            controller._ensure_timer = lambda: None
            controller.play()

            self.assertEqual(calls, [assembly, assembly])
            self.assertEqual(
                FreeCADMbDFreeBodyDiagram.prepare_diagram_scales(assembly),
                (100.0, 5.0),
            )
            self.assertEqual(calls, [assembly, assembly])
        finally:
            FreeCADMbDFreeBodyDiagram._assembly_auto_diagram_scales = original_auto_scales
            FreeCADMbDFreeBodyDiagram.reset_diagram_scales(assembly)

    def test_free_body_diagram_coin_arrow_updates(self):
        from pivy import coin

        arrow = FreeCADMbDFreeBodyDiagram._make_arrow(coin)
        arrow.update(App.Vector(1, 2, 3), App.Vector(0, -40, 0), 2.0)

        self.assertAlmostEqual(arrow.length, 80.0)
        self.assertAlmostEqual(arrow.shaft_length, 65.0)
        self.assertAlmostEqual(arrow.head_length, 15.0)
        self.assertAlmostEqual(arrow.head_radius, 2.5)

        load_arrow = FreeCADMbDFreeBodyDiagram._make_arrow(coin, use_load_style=True)
        load_arrow._view = _FakeViewport()
        load_arrow.update(App.Vector(1, 2, 3), App.Vector(0, -40, 0), 2.0)
        self.assertAlmostEqual(load_arrow.length, 80.0)
        self.assertAlmostEqual(load_arrow.shaft_length, 74.0)
        self.assertAlmostEqual(load_arrow.head_length, 6.0)
        self.assertEqual(load_arrow.head_line_width, 3)
        self.assertEqual(load_arrow.dot_diameter, 0)
        load_arrow.update(App.Vector(1, 2, 3), App.Vector(0, -2, 0), 2.0)
        self.assertAlmostEqual(load_arrow.length, 4.0)
        self.assertAlmostEqual(load_arrow.shaft_length, 0.0)
        self.assertAlmostEqual(load_arrow.head_length, 0.0)
        self.assertEqual(load_arrow.dot_diameter, 3)
        self.assertEqual(
            FreeCADMbDFreeBodyDiagram._color_for_vector("gravity"),
            (0.0, 0.85, 0.95),
        )
        self.assertEqual(
            FreeCADMbDFreeBodyDiagram._color_for_vector("force"),
            (0.90, 0.10, 0.08),
        )
        self.assertEqual(
            FreeCADMbDFreeBodyDiagram._color_for_vector("torque"),
            (0.05, 0.25, 0.95),
        )

        arrow.hide()
        self.assertEqual(arrow.length, 0.0)

    def test_fem_part_dloads_vectors_use_visible_element_centroids(self):
        import Fem

        document = App.newDocument("MbDFEMFEMPartDLOADDiagramTest")

        try:
            mesh = Fem.FemMesh()
            mesh.addNode(0, 0, 0, 1)
            mesh.addNode(4, 0, 0, 2)
            mesh.addNode(0, 8, 0, 3)
            mesh.addNode(0, 0, 12, 4)
            mesh.addVolume([1, 2, 3, 4], 42)

            mesh_object = document.addObject("Fem::FemMeshObject", "Mesh")
            mesh_object.FemMesh = mesh
            assembly = document.addObject("MbDFEM::MbDAssembly", "Assembly")
            gravity = assembly.ensureGravity()
            gravity.gravity = App.Vector(0, -9810, 0)
            part = document.addObject("MbDFEM::MbDPart", "Part")
            fem_part = document.addObject("MbDFEM::FEMPart", "FEMPart")
            assembly.addPart(part)
            fem_part.mbdItem = part
            fem_part.mesh = mesh_object
            part.acceleration = App.Vector(25, 0, 0)
            document.recompute()

            vectors = FreeCADMbDFEMDLOADs._diagram_vectors(fem_part, assembly)

            self.assertEqual(len(vectors), 2)
            self.assertEqual(vectors[0].kind, "dalembert")
            self.assertEqual(vectors[1].kind, "gravity")
            self.assertLess(vectors[0].origin.distanceToPoint(App.Vector(1, 2, 3)), 1e-7)
            self.assertEqual(vectors[0].value, App.Vector(-25, 0, 0))
            self.assertEqual(vectors[1].value, App.Vector(0, -9810, 0))
        finally:
            App.closeDocument(document.Name)

    def test_fem_part_dloads_vectors_ignore_mesh_visibility(self):
        class MeshViewObject:
            Visibility = False

        class Mesh:
            Name = "Mesh"
            ViewObject = MeshViewObject()

        class MbDPart:
            def globalAccelerationOf(self, point):
                return App.Vector(25, 0, 0)

        class FEMPart:
            Visibility = True
            mesh = Mesh()
            mbdItem = MbDPart()

            def isElementVisible(self, name):
                return 0

            def elementCentroidLocal(self, element_id):
                return App.Vector(1, 2, 3)

            def elementCentroidGlobal(self, element_id):
                return App.Vector(4, 5, 6)

        original_visible_element_ids = FreeCADMbDFEMDLOADs._visible_element_ids
        try:
            FreeCADMbDFEMDLOADs._visible_element_ids = lambda fem_part: [42]

            fem_part = FEMPart()
            vectors = FreeCADMbDFEMDLOADs._diagram_vectors(fem_part, object())
            fem_part.Visibility = False
            hidden_vectors = FreeCADMbDFEMDLOADs._diagram_vectors(fem_part, object())

            self.assertEqual(len(vectors), 1)
            self.assertEqual(vectors[0].kind, "dalembert")
            self.assertEqual(vectors[0].origin, App.Vector(4, 5, 6))
            self.assertEqual(vectors[0].value, App.Vector(-25, 0, 0))
            self.assertEqual(hidden_vectors, [])
        finally:
            FreeCADMbDFEMDLOADs._visible_element_ids = original_visible_element_ids

    def test_fem_part_cloads_vectors_use_generated_nodal_loads(self):
        import Fem

        document = App.newDocument("MbDFEMFEMPartCLOADDiagramTest")

        try:
            mesh = Fem.FemMesh()
            node_data = {
                1: (1, 1, 1),
                2: (1, -1, 1),
                3: (1, 1, -3),
                4: (1, -1, 2),
                9: (1, -1, -2),
                5: (-1, 1, 1),
                6: (-1, -1, 1),
                7: (-1, 1, -1),
                8: (-1, -1, -1),
            }
            for node_id, coordinates in node_data.items():
                mesh.addNode(*coordinates, node_id)

            mesh_object = document.addObject("Fem::FemMeshObject", "Mesh")
            mesh_object.FemMesh = mesh
            assembly = document.addObject("MbDFEM::MbDAssembly", "Assembly")
            part = document.addObject("MbDFEM::MbDPart", "Part")
            part.Shape = Part.makeCylinder(
                math.sqrt(2.0),
                5.0,
                App.Vector(0, 0, -3),
                App.Vector(0, 0, 1),
            )
            fem_part = document.addObject("MbDFEM::FEMPart", "FEMPart")
            marker = document.addObject("MbDFEM::MbDMarker", "Marker")
            joint = document.addObject("MbDFEM::MbDJoint", "Joint")
            assembly.times = [0.0, 1.0]
            assembly.addPart(part)
            assembly.addJoint(joint)
            part.addMarker(marker)
            fem_part.mbdItem = part
            fem_part.mesh = mesh_object
            fem_part.Placement = App.Placement(App.Vector(10, 20, 30), App.Rotation())
            marker.Placement = App.Placement()
            marker.Geometry = (part, ["Face1"])
            joint.markerI = marker
            joint.fxs = [0.0, 80.0]
            joint.fys = [0.0, 0.0]
            joint.fzs = [0.0, 40.0]
            document.recompute()

            vectors = FreeCADMbDFEMCLOADs._diagram_vectors(
                fem_part,
                assembly,
                (1, 1, 0.0, 1),
            )

            self.assertEqual(len(vectors), 5)
            self.assertLess(vectors[0].origin.distanceToPoint(App.Vector(11, 21, 31)), 1e-7)
            self.assertLess(vectors[0].value.distanceToPoint(App.Vector(18.18181818182, 0, 0)), 1e-7)
            self.assertLess(vectors[3].origin.distanceToPoint(App.Vector(11, 21, 27)), 1e-7)
            self.assertLess(vectors[3].value.distanceToPoint(App.Vector(21.81818181818, 0, 0)), 1e-7)
        finally:
            App.closeDocument(document.Name)

    def test_fem_part_cloads_vectors_follow_animated_mesh_coordinates(self):
        import Fem

        document = App.newDocument("MbDFEMFEMPartCLOADAnimatedMeshTest")

        try:
            mesh = Fem.FemMesh()
            node_data = {
                1: (1, 1, 1),
                2: (1, -1, 1),
                3: (1, 1, -3),
                4: (1, -1, 2),
                9: (1, -1, -2),
                5: (-1, 1, 1),
                6: (-1, -1, 1),
                7: (-1, 1, -1),
                8: (-1, -1, -1),
            }
            for node_id, coordinates in node_data.items():
                mesh.addNode(*coordinates, node_id)

            mesh_object = document.addObject("Fem::FemMeshObject", "Mesh")
            mesh_object.FemMesh = mesh
            assembly = document.addObject("MbDFEM::MbDAssembly", "Assembly")
            part = document.addObject("MbDFEM::MbDPart", "Part")
            part.Shape = Part.makeCylinder(
                math.sqrt(2.0),
                5.0,
                App.Vector(0, 0, -3),
                App.Vector(0, 0, 1),
            )
            fem_part = document.addObject("MbDFEM::FEMPart", "FEMPart")
            marker = document.addObject("MbDFEM::MbDMarker", "Marker")
            joint = document.addObject("MbDFEM::MbDJoint", "Joint")
            assembly.times = [0.0, 1.0]
            assembly.addPart(part)
            assembly.addJoint(joint)
            part.addMarker(marker)
            part.xs = [0.0, 100.0]
            part.ys = [0.0, 200.0]
            part.zs = [0.0, 300.0]
            fem_part.mbdItem = part
            fem_part.mesh = mesh_object
            marker.Placement = App.Placement()
            marker.Geometry = (part, ["Face1"])
            joint.markerI = marker
            joint.fxs = [0.0, 80.0]
            joint.fys = [0.0, 0.0]
            joint.fzs = [0.0, 40.0]
            document.recompute()

            vectors = FreeCADMbDFEMCLOADs._diagram_vectors(
                fem_part,
                assembly,
                (1, 1, 0.0, 1),
            )

            self.assertEqual(len(vectors), 5)
            self.assertLess(
                vectors[0].origin.distanceToPoint(App.Vector(101, 201, 301)),
                1e-7,
            )
        finally:
            App.closeDocument(document.Name)

    def test_fem_part_dloads_ignore_face_and_edge_elements(self):
        import Fem

        document = App.newDocument("MbDFEMFEMPartDLOADVolumeOnlyTest")

        try:
            mesh = Fem.FemMesh()
            mesh.addNode(0, 0, 0, 1)
            mesh.addNode(4, 0, 0, 2)
            mesh.addNode(0, 8, 0, 3)
            mesh.addNode(0, 0, 12, 4)
            mesh.addNode(100, 0, 0, 5)
            mesh.addNode(100, 1, 0, 6)
            mesh.addNode(100, 0, 1, 7)
            mesh.addVolume([1, 2, 3, 4], 42)
            mesh.addFace([5, 6, 7], 84)
            mesh.addEdge([5, 6], 126)

            mesh_object = document.addObject("Fem::FemMeshObject", "Mesh")
            mesh_object.FemMesh = mesh
            assembly = document.addObject("MbDFEM::MbDAssembly", "Assembly")
            gravity = assembly.ensureGravity()
            gravity.gravity = App.Vector(0, -9810, 0)
            part = document.addObject("MbDFEM::MbDPart", "Part")
            fem_part = document.addObject("MbDFEM::FEMPart", "FEMPart")
            assembly.addPart(part)
            fem_part.mbdItem = part
            fem_part.mesh = mesh_object
            part.acceleration = App.Vector(25, 0, 0)
            document.recompute()

            self.assertEqual(FreeCADMbDFEMDLOADs._visible_element_ids(fem_part), [42])

            vectors = FreeCADMbDFEMDLOADs._diagram_vectors(fem_part, assembly)

            self.assertEqual(len(vectors), 2)
            self.assertLess(vectors[0].origin.distanceToPoint(App.Vector(1, 2, 3)), 1e-7)
        finally:
            App.closeDocument(document.Name)

    def test_fem_part_dloads_samples_at_most_display_limit(self):
        element_ids = list(range(1, 251))

        sampled = FreeCADMbDFEMDLOADs._sample_element_ids(element_ids, 20)

        self.assertEqual(len(sampled), 20)
        self.assertEqual(sampled[0], 1)
        self.assertEqual(sampled[-1], 250)
        self.assertEqual(len(set(sampled)), 20)
        self.assertEqual(
            FreeCADMbDFEMDLOADs._sample_element_ids(list(range(1, 15)), 20),
            list(range(1, 15)),
        )

    def test_fem_part_dload_elements_mesh_uses_sampled_volumes_only(self):
        import Fem

        document = App.newDocument("MbDFEMFEMPartDLOADElementsMeshTest")

        try:
            source = Fem.FemMesh()
            source.addNode(0, 0, 0, 1)
            source.addNode(4, 0, 0, 2)
            source.addNode(0, 8, 0, 3)
            source.addNode(0, 0, 12, 4)
            source.addNode(100, 0, 0, 5)
            source.addNode(104, 0, 0, 6)
            source.addNode(100, 8, 0, 7)
            source.addNode(100, 0, 12, 8)
            source.addVolume([1, 2, 3, 4], 42)
            source.addVolume([5, 6, 7, 8], 84)

            mesh_object = document.addObject("Fem::FemMeshObject", "Mesh")
            mesh_object.FemMesh = source

            sampled = FreeCADMbDFEMDLOADs._sampled_elements_fem_mesh(
                mesh_object,
                [42],
            )

            self.assertEqual(list(sampled.Volumes), [42])
            self.assertEqual(list(sampled.getElementNodes(42)), [1, 2, 3, 4])
            self.assertEqual(sorted(sampled.Nodes.keys()), [1, 2, 3, 4])
            self.assertEqual(sampled.getNodeById(2), App.Vector(4, 0, 0))
        finally:
            App.closeDocument(document.Name)

    def test_fem_part_dload_elements_placement_is_local_to_fem_part(self):
        document = App.newDocument("MbDFEMFEMPartDLOADElementsPlacementTest")

        try:
            assembly = document.addObject("MbDFEM::MbDAssembly", "Assembly")
            part = document.addObject("MbDFEM::MbDPart", "Part")
            fem_part = document.addObject("MbDFEM::FEMPart", "FEMPart")
            mesh_object = document.addObject("Fem::FemMeshObject", "Mesh")
            assembly.addPart(part)
            fem_part.mbdItem = part
            fem_part.mesh = mesh_object
            mesh_object.Placement = App.Placement(App.Vector(1, 2, 3), App.Rotation())
            part.Placement = App.Placement(App.Vector(10, 20, 30), App.Rotation())
            part.xs = [0.0, 100.0]
            part.ys = [0.0, 200.0]
            part.zs = [0.0, 300.0]
            document.recompute()

            placement = FreeCADMbDFEMDLOADs._sampled_elements_display_placement(
                fem_part,
                (1, 1, 0.0, 1),
            )

            self.assertLess(
                placement.Base.distanceToPoint(App.Vector(1, 2, 3)),
                1e-7,
            )
        finally:
            App.closeDocument(document.Name)

    def test_fem_part_dload_elements_update_with_animation_sample(self):
        document = App.newDocument("MbDFEMFEMPartDLOADElementsUpdateTest")

        try:
            assembly = document.addObject("MbDFEM::MbDAssembly", "Assembly")
            part = document.addObject("MbDFEM::MbDPart", "Part")
            fem_part = document.addObject("MbDFEM::FEMPart", "FEMPart")
            mesh_object = document.addObject("Fem::FemMeshObject", "Mesh")
            display_object = document.addObject("Fem::FemMeshObject", "Display")
            assembly.addPart(part)
            fem_part.mbdItem = part
            fem_part.mesh = mesh_object
            mesh_object.Placement = App.Placement(App.Vector(1, 2, 3), App.Rotation())
            part.xs = [0.0, 100.0]
            part.ys = [0.0, 200.0]
            part.zs = [0.0, 300.0]
            document.recompute()

            key = FreeCADMbDFEMDLOADs._diagram_key(fem_part)
            FreeCADMbDFEMDLOADs._sampled_element_view_states[key] = {
                "fem_part": fem_part,
                "display_object": display_object,
            }

            class Controller:
                pass

            controller = Controller()
            controller.assembly = assembly
            FreeCADMbDFEMDLOADs.update_active_diagrams(controller, (1, 1, 0.0, 1))

            self.assertLess(
                display_object.Placement.Base.distanceToPoint(App.Vector(1, 2, 3)),
                1e-7,
            )
        finally:
            FreeCADMbDFEMDLOADs._sampled_element_view_states.clear()
            App.closeDocument(document.Name)

    def test_fem_part_dload_elements_display_object_groups_under_fem_part(self):
        document = App.newDocument("MbDFEMFEMPartDLOADElementsGroupTest")

        try:
            fem_part = document.addObject("MbDFEM::FEMPart", "FEMPart")
            display_object = document.addObject("Fem::FemMeshObject", "Display")

            FreeCADMbDFEMDLOADs._add_to_fem_part_group(fem_part, display_object)
            self.assertIn(display_object, fem_part.Group)

            FreeCADMbDFEMDLOADs._remove_from_fem_part_group(fem_part, display_object)
            self.assertNotIn(display_object, fem_part.Group)
        finally:
            App.closeDocument(document.Name)

    def test_fem_part_dloads_sample_size_uses_view_property(self):
        class Part:
            pass

        class ViewObject:
            DLOADSampleSize = 37

        part = Part()
        self.assertEqual(FreeCADMbDFEMDLOADs._display_sample_size(part), 20)

        part.ViewObject = ViewObject()
        self.assertEqual(FreeCADMbDFEMDLOADs._display_sample_size(part), 37)

    def test_fem_part_dloads_scale_is_assembly_wide_tenth_diagonal(self):
        import Fem

        document = App.newDocument("MbDFEMFEMPartDLOADScaleTest")

        try:
            mesh = Fem.FemMesh()
            mesh.addNode(0, 0, 0, 1)
            mesh.addNode(4, 0, 0, 2)
            mesh.addNode(0, 8, 0, 3)
            mesh.addNode(0, 0, 12, 4)
            mesh.addVolume([1, 2, 3, 4], 42)

            mesh_object = document.addObject("Fem::FemMeshObject", "Mesh")
            mesh_object.FemMesh = mesh
            assembly = document.addObject("MbDFEM::MbDAssembly", "Assembly")
            fem_assembly = document.addObject("MbDFEM::FEMAssembly", "FEMAssembly")
            part = document.addObject("MbDFEM::MbDPart", "Part")
            second_part = document.addObject("MbDFEM::MbDPart", "SecondPart")
            fem_part = document.addObject("MbDFEM::FEMPart", "FEMPart")
            second_fem_part = document.addObject("MbDFEM::FEMPart", "SecondFEMPart")
            fem_assembly.mbdItem = assembly
            assembly.addPart(part)
            assembly.addPart(second_part)
            part.Shape = Part.makeBox(3, 4, 12)
            second_part.Shape = Part.makeBox(3, 4, 12)
            fem_part.mbdItem = part
            fem_part.mesh = mesh_object
            second_fem_part.mbdItem = second_part
            second_fem_part.mesh = mesh_object
            assembly.times = [0.0, 1.0]
            part.xs = [0.0, 0.0]
            part.ys = [0.0, 0.0]
            part.zs = [0.0, 0.0]
            second_part.xs = [0.0, 0.0]
            second_part.ys = [0.0, 0.0]
            second_part.zs = [0.0, 0.0]
            part.axs = [1000.0, 2000.0]
            part.ays = [0.0, 0.0]
            part.azs = [0.0, 0.0]
            second_part.axs = [0.0, 4000.0]
            second_part.ays = [0.0, 0.0]
            second_part.azs = [0.0, 0.0]
            document.recompute()

            try:
                fem_part.ViewObject.DLOADSampleSize = 1
                second_fem_part.ViewObject.DLOADSampleSize = 1
                fem_assembly.ViewObject.DLOADScale = 2.0
            except Exception:
                pass
            FreeCADMbDFEMDLOADs.reset_diagram_scales(assembly)

            self.assertAlmostEqual(
                FreeCADMbDFEMDLOADs._diagram_scale(fem_part, assembly),
                2.6 / 4000.0,
            )
            self.assertAlmostEqual(
                FreeCADMbDFEMDLOADs._diagram_scale(second_fem_part, assembly),
                2.6 / 4000.0,
            )
        finally:
            FreeCADMbDFEMDLOADs.reset_diagram_scales()
            App.closeDocument(document.Name)

    def test_fem_part_dloads_scale_uses_live_assembly_multiplier(self):
        class Assembly:
            times = [0.0, 1.0]
            parts = []
            fixedparts = []

        class ViewObject:
            DLOADAutoScale = True
            DLOADScale = 2.0

        assembly = Assembly()
        assembly.ViewObject = ViewObject()
        calls = []
        original_auto_scale = FreeCADMbDFEMDLOADs._assembly_auto_diagram_scale
        try:
            FreeCADMbDFEMDLOADs.reset_diagram_scales(assembly)
            FreeCADMbDFEMDLOADs._assembly_auto_diagram_scale = (
                lambda item: calls.append(item) or 10.0
            )

            self.assertEqual(FreeCADMbDFEMDLOADs.prepare_diagram_scale(assembly), 20.0)
            self.assertEqual(FreeCADMbDFEMDLOADs.prepare_diagram_scale(assembly), 20.0)
            self.assertEqual(calls, [assembly])

            assembly.ViewObject.DLOADScale = 3.0
            self.assertEqual(FreeCADMbDFEMDLOADs.prepare_diagram_scale(assembly), 30.0)
            self.assertEqual(calls, [assembly])

            controller = FreeCADMbDAnimation.AnimationController(assembly)
            controller._ensure_timer = lambda: None
            controller.play()

            self.assertEqual(calls, [assembly, assembly])
            self.assertEqual(FreeCADMbDFEMDLOADs.prepare_diagram_scale(assembly), 30.0)
            self.assertEqual(calls, [assembly, assembly])
        finally:
            FreeCADMbDFEMDLOADs._assembly_auto_diagram_scale = original_auto_scale
            FreeCADMbDFEMDLOADs.reset_diagram_scales(assembly)

    def test_fem_part_cloads_scale_uses_live_assembly_multiplier(self):
        class Assembly:
            times = [0.0, 1.0]
            parts = []
            fixedparts = []

        class ViewObject:
            CLOADAutoScale = True
            CLOADScale = 2.0

        assembly = Assembly()
        assembly.ViewObject = ViewObject()
        calls = []
        original_auto_scale = FreeCADMbDFEMCLOADs._assembly_auto_diagram_scale
        try:
            FreeCADMbDFEMCLOADs.reset_diagram_scales(assembly)
            FreeCADMbDFEMCLOADs._assembly_auto_diagram_scale = (
                lambda item: calls.append(item) or 10.0
            )

            self.assertEqual(FreeCADMbDFEMCLOADs.prepare_diagram_scale(assembly), 20.0)
            self.assertEqual(FreeCADMbDFEMCLOADs.prepare_diagram_scale(assembly), 20.0)
            self.assertEqual(calls, [assembly])

            assembly.ViewObject.CLOADScale = 3.0
            self.assertEqual(FreeCADMbDFEMCLOADs.prepare_diagram_scale(assembly), 30.0)
            self.assertEqual(calls, [assembly])

            controller = FreeCADMbDAnimation.AnimationController(assembly)
            controller._ensure_timer = lambda: None
            controller.play()

            self.assertEqual(calls, [assembly, assembly])
            self.assertEqual(FreeCADMbDFEMCLOADs.prepare_diagram_scale(assembly), 30.0)
            self.assertEqual(calls, [assembly, assembly])
        finally:
            FreeCADMbDFEMCLOADs._assembly_auto_diagram_scale = original_auto_scale
            FreeCADMbDFEMCLOADs.reset_diagram_scales(assembly)

    def test_fem_part_cloads_initial_scale_uses_current_vectors(self):
        class Assembly:
            times = [0.0, 1.0]
            parts = []
            fixedparts = []

        class ViewObject:
            CLOADAutoScale = True
            CLOADScale = 2.0

        assembly = Assembly()
        assembly.ViewObject = ViewObject()
        vectors = [
            FreeCADMbDFEMCLOADs._DiagramVector(
                App.Vector(),
                App.Vector(4.0, 0.0, 0.0),
            )
        ]
        original_auto_scale = FreeCADMbDFEMCLOADs._assembly_auto_diagram_scale
        try:
            FreeCADMbDFEMCLOADs.reset_diagram_scales(assembly)
            FreeCADMbDFEMCLOADs._assembly_auto_diagram_scale = (
                lambda item: self.fail("initial CLOAD scale should not scan all frames")
            )

            self.assertAlmostEqual(
                FreeCADMbDFEMCLOADs._diagram_scale(None, assembly, vectors),
                0.05,
            )
        finally:
            FreeCADMbDFEMCLOADs._assembly_auto_diagram_scale = original_auto_scale
            FreeCADMbDFEMCLOADs.reset_diagram_scales(assembly)

    def test_fem_part_cloads_vectors_reuse_load_nodes(self):
        class Mesh:
            def getGlobalPlacement(self):
                return App.Placement()

        class FEMPart:
            Visibility = True
            mesh = Mesh()

        nodes = {
            1: App.Vector(1.0, 2.0, 3.0),
            2: App.Vector(4.0, 5.0, 6.0),
        }
        loads = [
            {
                "nodes": nodes,
                "x_axis": App.Vector(1.0, 0.0, 0.0),
                "octants": {"U1": [1, 2], "U4": [], "L1": [], "L4": []},
                "nodal_values": {"U1": 3.0, "U4": 0.0, "L1": 0.0, "L4": 0.0},
            }
        ]
        original_loads = FreeCADMbDFEMCLOADs._mbd_joint_cylindrical_hole_loads
        original_nodes = FreeCADMbDFEMEmbedded._fem_mesh_nodes
        try:
            FreeCADMbDFEMCLOADs._mbd_joint_cylindrical_hole_loads = (
                lambda fem_part, assembly, sample: loads
            )
            FreeCADMbDFEMEmbedded._fem_mesh_nodes = (
                lambda mesh_object: self.fail("render should reuse load node map")
            )

            vectors = FreeCADMbDFEMCLOADs._diagram_vectors(FEMPart(), object())

            self.assertEqual(len(vectors), 2)
            self.assertLess(vectors[0].origin.distanceToPoint(nodes[1]), 1e-7)
            self.assertLess(vectors[1].origin.distanceToPoint(nodes[2]), 1e-7)
        finally:
            FreeCADMbDFEMCLOADs._mbd_joint_cylindrical_hole_loads = original_loads
            FreeCADMbDFEMEmbedded._fem_mesh_nodes = original_nodes

    def test_fem_part_cloads_vectors_use_cpp_cload_records(self):
        class Mesh:
            def getGlobalPlacement(self):
                return App.Placement()

        class FEMPart:
            Visibility = True
            mesh = Mesh()

        nodes = {1: App.Vector(1.0, 2.0, 3.0)}
        loads = [{"nodes": nodes, "cloads": [(1, 1, 4.0), (1, 3, -2.0)]}]
        original_loads = FreeCADMbDFEMCLOADs._mbd_joint_cylindrical_hole_loads
        try:
            FreeCADMbDFEMCLOADs._mbd_joint_cylindrical_hole_loads = (
                lambda fem_part, assembly, sample: loads
            )

            vectors = FreeCADMbDFEMCLOADs._diagram_vectors(FEMPart(), object())

            self.assertEqual(len(vectors), 1)
            self.assertLess(vectors[0].origin.distanceToPoint(nodes[1]), 1e-7)
            self.assertLess(vectors[0].value.distanceToPoint(App.Vector(4, 0, -2)), 1e-7)
        finally:
            FreeCADMbDFEMCLOADs._mbd_joint_cylindrical_hole_loads = original_loads

    def test_fem_part_cloads_vectors_read_inp_with_matching_sidecar(self):
        fd, inp_file_name = tempfile.mkstemp(suffix=".inp")
        os.close(fd)

        class FemMesh:
            Nodes = {
                1: App.Vector(1.0, 2.0, 3.0),
                2: App.Vector(4.0, 5.0, 6.0),
            }

        class Mesh:
            Name = "Mesh"
            FemMesh = FemMesh()

            def getGlobalPlacement(self):
                return App.Placement()

        class FEMPart:
            Visibility = True
            mesh = Mesh()

        original_inp = FreeCADMbDFEMCLOADs._sample_inp_file_name
        original_loads = FreeCADMbDFEMCLOADs._mbd_joint_cylindrical_hole_loads
        try:
            signature = FreeCADMbDFEMEmbedded._fem_mesh_signature(Mesh())
            Path(inp_file_name).write_text(
                "{}"
                "*CLOAD\n"
                "2,1,5.0\n"
                "1,2,-3.0\n".format(
                    FreeCADMbDFEMEmbedded._MBD_JOINT_CYLINDER_LOAD_MARKER,
                ),
                encoding="utf-8",
            )
            FreeCADMbDFEMEmbedded._write_frame_metadata_sidecar(
                FreeCADMbDFEMEmbedded._frame_metadata_sidecar_file_name_for_inp(inp_file_name),
                {
                    "schema": 1,
                    "artifacts": {
                        FreeCADMbDFEMEmbedded._MBD_CLOAD_ARTIFACT: {
                            "algorithm": FreeCADMbDFEMEmbedded._MBD_CLOAD_ALGORITHM,
                            "mesh_signature": signature,
                            "source": os.path.basename(inp_file_name),
                        },
                    },
                },
            )
            FreeCADMbDFEMCLOADs._sample_inp_file_name = lambda fem_part, sample: inp_file_name
            FreeCADMbDFEMCLOADs._mbd_joint_cylindrical_hole_loads = (
                lambda fem_part, assembly, sample: self.fail("matching inp should be used")
            )

            vectors = FreeCADMbDFEMCLOADs._diagram_vectors(FEMPart(), object(), (1, 1, 0.0, 1))

            self.assertEqual(len(vectors), 2)
            self.assertLess(vectors[0].origin.distanceToPoint(App.Vector(1, 2, 3)), 1e-7)
            self.assertLess(vectors[0].value.distanceToPoint(App.Vector(0, -3, 0)), 1e-7)
            self.assertLess(vectors[1].origin.distanceToPoint(App.Vector(4, 5, 6)), 1e-7)
            self.assertLess(vectors[1].value.distanceToPoint(App.Vector(5, 0, 0)), 1e-7)
        finally:
            FreeCADMbDFEMCLOADs._sample_inp_file_name = original_inp
            FreeCADMbDFEMCLOADs._mbd_joint_cylindrical_hole_loads = original_loads
            sidecar_name = FreeCADMbDFEMEmbedded._frame_metadata_sidecar_file_name_for_inp(inp_file_name)
            if os.path.exists(sidecar_name):
                os.remove(sidecar_name)
            os.remove(inp_file_name)

    def test_fem_part_cloads_vectors_recompute_when_sidecar_signature_differs(self):
        fd, inp_file_name = tempfile.mkstemp(suffix=".inp")
        os.close(fd)

        class FemMesh:
            Nodes = {
                1: App.Vector(1.0, 2.0, 3.0),
                2: App.Vector(4.0, 5.0, 6.0),
            }

        class Mesh:
            Name = "Mesh"
            FemMesh = FemMesh()

            def getGlobalPlacement(self):
                return App.Placement()

        class FEMPart:
            Visibility = True
            mesh = Mesh()

        loads = [
            {
                "nodes": FemMesh.Nodes,
                "x_axis": App.Vector(1.0, 0.0, 0.0),
                "octants": {"U1": [1], "U4": [], "L1": [], "L4": []},
                "nodal_values": {"U1": 7.0, "U4": 0.0, "L1": 0.0, "L4": 0.0},
            }
        ]
        original_inp = FreeCADMbDFEMCLOADs._sample_inp_file_name
        original_loads = FreeCADMbDFEMCLOADs._mbd_joint_cylindrical_hole_loads
        try:
            Path(inp_file_name).write_text(
                "{}"
                "*CLOAD\n"
                "2,1,5.0\n".format(
                    FreeCADMbDFEMEmbedded._MBD_JOINT_CYLINDER_LOAD_MARKER,
                ),
                encoding="utf-8",
            )
            FreeCADMbDFEMEmbedded._write_frame_metadata_sidecar(
                FreeCADMbDFEMEmbedded._frame_metadata_sidecar_file_name_for_inp(inp_file_name),
                {
                    "schema": 1,
                    "artifacts": {
                        FreeCADMbDFEMEmbedded._MBD_CLOAD_ARTIFACT: {
                            "algorithm": FreeCADMbDFEMEmbedded._MBD_CLOAD_ALGORITHM,
                            "mesh_signature": "stale",
                            "source": os.path.basename(inp_file_name),
                        },
                    },
                },
            )
            FreeCADMbDFEMCLOADs._sample_inp_file_name = lambda fem_part, sample: inp_file_name
            FreeCADMbDFEMCLOADs._mbd_joint_cylindrical_hole_loads = (
                lambda fem_part, assembly, sample: loads
            )

            vectors = FreeCADMbDFEMCLOADs._diagram_vectors(FEMPart(), object(), (1, 1, 0.0, 1))

            self.assertEqual(len(vectors), 1)
            self.assertLess(vectors[0].origin.distanceToPoint(App.Vector(1, 2, 3)), 1e-7)
            self.assertLess(vectors[0].value.distanceToPoint(App.Vector(7, 0, 0)), 1e-7)
        finally:
            FreeCADMbDFEMCLOADs._sample_inp_file_name = original_inp
            FreeCADMbDFEMCLOADs._mbd_joint_cylindrical_hole_loads = original_loads
            sidecar_name = FreeCADMbDFEMEmbedded._frame_metadata_sidecar_file_name_for_inp(inp_file_name)
            if os.path.exists(sidecar_name):
                os.remove(sidecar_name)
            os.remove(inp_file_name)

    def test_fem_part_cloads_vectors_ignore_mesh_visibility(self):
        class ViewObject:
            Visibility = False

        class Mesh:
            ViewObject = ViewObject()

            def getGlobalPlacement(self):
                return App.Placement()

        class FEMPart:
            Visibility = True
            mesh = Mesh()

            def isElementVisible(self, name):
                return 0

        nodes = {
            1: App.Vector(1.0, 2.0, 3.0),
            2: App.Vector(4.0, 5.0, 6.0),
        }
        loads = [
            {
                "nodes": nodes,
                "x_axis": App.Vector(1.0, 0.0, 0.0),
                "octants": {"U1": [1, 2], "U4": [], "L1": [], "L4": []},
                "nodal_values": {"U1": 3.0, "U4": 0.0, "L1": 0.0, "L4": 0.0},
            }
        ]
        original_loads = FreeCADMbDFEMCLOADs._mbd_joint_cylindrical_hole_loads
        try:
            FreeCADMbDFEMCLOADs._mbd_joint_cylindrical_hole_loads = (
                lambda fem_part, assembly, sample: loads
            )

            fem_part = FEMPart()
            vectors = FreeCADMbDFEMCLOADs._diagram_vectors(fem_part, object())
            fem_part.Visibility = False
            hidden_vectors = FreeCADMbDFEMCLOADs._diagram_vectors(fem_part, object())

            self.assertEqual(len(vectors), 2)
            self.assertEqual(hidden_vectors, [])
        finally:
            FreeCADMbDFEMCLOADs._mbd_joint_cylindrical_hole_loads = original_loads

    def test_fem_part_cload_faces_mesh_uses_volume_boundary_facets(self):
        import Fem

        document = App.newDocument("MbDFEMFEMPartCLOADFacesMeshTest")

        try:
            source = Fem.FemMesh()
            source.addNode(0, 0, 0, 1)
            source.addNode(1, 0, 0, 2)
            source.addNode(1, 1, 0, 3)
            source.addNode(0, 1, 0, 4)
            source.addNode(0, 0, 1, 5)
            source.addNode(1, 0, 1, 6)
            source.addNode(1, 1, 1, 7)
            source.addNode(0, 1, 1, 8)
            source.addVolume([1, 2, 3, 4, 5, 6, 7, 8], 42)

            mesh_object = document.addObject("Fem::FemMeshObject", "Mesh")
            mesh_object.FemMesh = source
            load = {
                "octants": {
                    "U1": [1],
                    "U2": [2],
                    "U3": [3],
                    "U4": [4],
                    "L1": [],
                    "L2": [],
                    "L3": [],
                    "L4": [],
                },
            }

            display_mesh = FreeCADMbDFEMCLOADs._cload_faces_fem_mesh(mesh_object, [load])

            self.assertEqual(list(display_mesh.Faces), [1])
            self.assertEqual(list(display_mesh.getElementNodes(1)), [1, 2, 3, 4])
            self.assertEqual(sorted(display_mesh.Nodes.keys()), [1, 2, 3, 4])
        finally:
            App.closeDocument(document.Name)

    def test_fem_part_cload_faces_use_joint_marker_even_when_force_is_zero(self):
        import Fem

        document = App.newDocument("MbDFEMFEMPartCLOADFacesZeroForceTest")

        try:
            mesh = Fem.FemMesh()
            node_data = {
                1: (1, 0, -1),
                2: (0, 1, -1),
                3: (-1, 0, -1),
                4: (0, -1, -1),
                5: (1, 0, 1),
                6: (0, 1, 1),
                7: (-1, 0, 1),
                8: (0, -1, 1),
                9: (0, 0, -1),
                10: (0, 0, 1),
            }
            for node_id, coordinates in node_data.items():
                mesh.addNode(*coordinates, node_id)
            mesh.addVolume([1, 2, 9, 5], 101)
            mesh.addVolume([2, 6, 9, 5], 102)
            mesh.addVolume([2, 3, 9, 6], 103)
            mesh.addVolume([3, 7, 9, 6], 104)
            mesh.addVolume([3, 4, 9, 7], 105)
            mesh.addVolume([4, 8, 9, 7], 106)
            mesh.addVolume([4, 1, 9, 8], 107)
            mesh.addVolume([1, 5, 9, 8], 108)

            mesh_object = document.addObject("Fem::FemMeshObject", "Mesh")
            mesh_object.FemMesh = mesh
            assembly = document.addObject("MbDFEM::MbDAssembly", "Assembly")
            part = document.addObject("MbDFEM::MbDPart", "Part")
            part.Shape = Part.makeCylinder(1.0, 2.0, App.Vector(0, 0, -1), App.Vector(0, 0, 1))
            fem_part = document.addObject("MbDFEM::FEMPart", "FEMPart")
            marker = document.addObject("MbDFEM::MbDMarker", "Marker")
            joint = document.addObject("MbDFEM::MbDJoint", "Joint")
            assembly.addPart(part)
            assembly.addJoint(joint)
            part.addMarker(marker)
            fem_part.mbdItem = part
            fem_part.mesh = mesh_object
            marker.Placement = App.Placement()
            marker.Geometry = (part, ["Face1"])
            joint.markerI = marker
            joint.fxs = [0.0]
            joint.fys = [0.0]
            joint.fzs = [0.0]
            document.recompute()

            self.assertEqual(
                FreeCADMbDFEMCLOADs._mbd_joint_cylindrical_hole_loads(
                    fem_part,
                    assembly,
                    (0, 0, 0.0, 0),
                ),
                [],
            )

            face_regions = FreeCADMbDFEMCLOADs._mbd_joint_cylindrical_face_regions(
                fem_part,
                assembly,
            )
            display_mesh = FreeCADMbDFEMCLOADs._cload_faces_fem_mesh(mesh_object, face_regions)

            self.assertEqual(len(face_regions), 1)
            self.assertGreater(display_mesh.FaceCount, 0)
            self.assertTrue(
                set(display_mesh.Nodes.keys()).issubset({1, 2, 3, 4, 5, 6, 7, 8})
            )
        finally:
            App.closeDocument(document.Name)

    def test_fem_part_cload_faces_update_with_animation_sample(self):
        import Fem

        document = App.newDocument("MbDFEMFEMPartCLOADFacesUpdateTest")
        original_loads = FreeCADMbDFEMCLOADs._mbd_joint_cylindrical_hole_loads
        original_face_regions = FreeCADMbDFEMCLOADs._mbd_joint_cylindrical_face_regions

        try:
            source = Fem.FemMesh()
            source.addNode(0, 0, 0, 1)
            source.addNode(1, 0, 0, 2)
            source.addNode(1, 1, 0, 3)
            source.addNode(0, 1, 0, 4)
            source.addNode(0, 0, 1, 5)
            source.addNode(1, 0, 1, 6)
            source.addNode(1, 1, 1, 7)
            source.addNode(0, 1, 1, 8)
            source.addVolume([1, 2, 3, 4, 5, 6, 7, 8], 42)

            assembly = document.addObject("MbDFEM::MbDAssembly", "Assembly")
            part = document.addObject("MbDFEM::MbDPart", "Part")
            fem_part = document.addObject("MbDFEM::FEMPart", "FEMPart")
            mesh_object = document.addObject("Fem::FemMeshObject", "Mesh")
            display_object = document.addObject("Fem::FemMeshObject", "Display")
            mesh_object.FemMesh = source
            assembly.addPart(part)
            fem_part.mbdItem = part
            fem_part.mesh = mesh_object
            part.xs = [0.0, 100.0]
            part.ys = [0.0, 200.0]
            part.zs = [0.0, 300.0]
            document.recompute()

            face_region = {"surface_node_ids": [1, 2, 3, 4]}
            key = FreeCADMbDFEMDLOADs._diagram_key(fem_part)
            FreeCADMbDFEMCLOADs._face_view_states[key] = {
                "fem_part": fem_part,
                "mesh_object": mesh_object,
                "display_object": display_object,
            }
            FreeCADMbDFEMCLOADs._mbd_joint_cylindrical_hole_loads = (
                lambda fem_part, assembly, sample: []
            )
            FreeCADMbDFEMCLOADs._mbd_joint_cylindrical_face_regions = (
                lambda fem_part, assembly: [face_region]
            )

            class Controller:
                pass

            controller = Controller()
            controller.assembly = assembly
            FreeCADMbDFEMCLOADs.update_active_diagrams(controller, (1, 1, 0.0, 1))

            self.assertEqual(list(display_object.FemMesh.getElementNodes(1)), [1, 2, 3, 4])
            self.assertLess(
                display_object.Placement.Base.distanceToPoint(App.Vector(0, 0, 0)),
                1e-7,
            )
        finally:
            FreeCADMbDFEMCLOADs._mbd_joint_cylindrical_hole_loads = original_loads
            FreeCADMbDFEMCLOADs._mbd_joint_cylindrical_face_regions = original_face_regions
            FreeCADMbDFEMCLOADs._face_view_states.clear()
            App.closeDocument(document.Name)

    def test_fem_part_cload_faces_display_object_groups_under_fem_part(self):
        document = App.newDocument("MbDFEMFEMPartCLOADFacesGroupTest")

        try:
            fem_part = document.addObject("MbDFEM::FEMPart", "FEMPart")
            display_object = document.addObject("Fem::FemMeshObject", "Display")

            FreeCADMbDFEMCLOADs._add_to_fem_part_group(fem_part, display_object)
            self.assertIn(display_object, fem_part.Group)

            FreeCADMbDFEMCLOADs._remove_from_fem_part_group(fem_part, display_object)
            self.assertNotIn(display_object, fem_part.Group)
        finally:
            App.closeDocument(document.Name)

    def test_animation_controller_updates_fem_part_dload_diagrams(self):
        document = App.newDocument("MbDFEMFEMPartDLOADAnimationTest")

        try:
            assembly = document.addObject("MbDFEM::MbDAssembly", "Assembly")
            part = document.addObject("MbDFEM::MbDPart", "Part")
            assembly.addPart(part)
            assembly.times = [0.0, 1.0]
            part.xs = [0.0, 0.0]
            part.ys = [0.0, 0.0]
            part.zs = [0.0, 0.0]
            part.axs = [10.0, 20.0]
            part.ays = [0.0, 0.0]
            part.azs = [0.0, 0.0]

            calls = []
            original_update = FreeCADMbDFEMDLOADs.update_active_diagrams
            FreeCADMbDFEMDLOADs.update_active_diagrams = (
                lambda controller, sample: calls.append((controller.assembly, sample))
            )
            try:
                controller = FreeCADMbDAnimation.controller(assembly)
                controller.setFrame(1)
            finally:
                FreeCADMbDFEMDLOADs.update_active_diagrams = original_update

            self.assertEqual(calls, [(assembly, (1, 1, 0.0, 1))])
        finally:
            App.closeDocument(document.Name)

    def test_animation_controller_updates_fem_part_cload_diagrams(self):
        document = App.newDocument("MbDFEMFEMPartCLOADAnimationTest")

        try:
            assembly = document.addObject("MbDFEM::MbDAssembly", "Assembly")
            part = document.addObject("MbDFEM::MbDPart", "Part")
            assembly.addPart(part)
            assembly.times = [0.0, 1.0]
            part.xs = [0.0, 0.0]
            part.ys = [0.0, 0.0]
            part.zs = [0.0, 0.0]

            calls = []
            original_update = FreeCADMbDFEMCLOADs.update_active_diagrams
            FreeCADMbDFEMCLOADs.update_active_diagrams = (
                lambda controller, sample: calls.append((controller.assembly, sample))
            )
            try:
                controller = FreeCADMbDAnimation.controller(assembly)
                controller.setFrame(1)
            finally:
                FreeCADMbDFEMCLOADs.update_active_diagrams = original_update

            self.assertEqual(calls, [(assembly, (1, 1, 0.0, 1))])
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
            part.xs = [0.0, 1000.0, 2000.0, 3000.0]
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

    def test_freecadmbd_animation_controller_counts_frames_without_copying_series(self):
        class ResultSeries:
            def __init__(self, values):
                self.values = values
                self.iterations = 0

            def __len__(self):
                return len(self.values)

            def __getitem__(self, index):
                return self.values[index]

            def __iter__(self):
                self.iterations += 1
                raise AssertionError("frame count should not copy result series")

        class Assembly:
            times = ResultSeries([0.0, 0.5, 1.0])

        class Part:
            xs = ResultSeries([0.0, 1000.0, 2000.0])
            ys = []
            zs = []

        controller = FreeCADMbDAnimation.AnimationController(Assembly(), objects=[Part()])

        self.assertEqual(controller.source_frame_count, 3)
        self.assertEqual(controller.source_frame_count, 3)
        self.assertEqual(Assembly.times.iterations, 0)
        self.assertEqual(Part.xs.iterations, 0)

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

    def test_freecadmbd_animation_controller_uses_frame_rate_for_tick(self):
        document = App.newDocument("MbDFEMAnimationTickTest")

        try:
            assembly = document.addObject("MbDFEM::MbDAssembly", "Assembly")
            part = document.addObject("MbDFEM::MbDPart", "Part")
            assembly.addPart(part)
            parameters = assembly.ensureAnimationParameters()
            parameters.updateRate = 10
            parameters.startFrame = 0
            parameters.lengthScale = 3.0
            parameters.loop = False
            assembly.times = [0.0, 0.1, 0.2, 0.3]
            part.xs = [0.0, 1000.0, 2000.0, 3000.0]
            part.ys = [0.0, 0.0, 0.0, 0.0]
            part.zs = [0.0, 0.0, 0.0, 0.0]

            controller = FreeCADMbDAnimation.AnimationController(assembly)
            controller.beginPlayback()

            self.assertEqual(controller.frame_rate, 10.0)
            self.assertEqual(controller.update_rate, 10.0)
            self.assertAlmostEqual(controller.playback_speed, 1.0)
            self.assertEqual(controller.length_scale, 3.0)
            controller.tick(0.25)
            self.assertEqual(controller.current_frame, 2)
            self.assertAlmostEqual(controller.current_time, 0.2)
            self.assertAlmostEqual(part.Placement.Base.x, 6000.0)
            self.assertEqual(controller.frames_skipped, 1)

            controller.tick(0.5)

            self.assertEqual(controller.current_frame, 3)
            self.assertAlmostEqual(controller.current_time, 0.3)
            self.assertAlmostEqual(part.Placement.Base.x, 9000.0)
            self.assertFalse(controller.is_playing)
            self.assertEqual(controller.frames_skipped, 0)
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
