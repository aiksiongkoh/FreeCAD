# SPDX-License-Identifier: LGPL-2.1-or-later

import math
import os
import tempfile
import unittest

import FreeCAD as App
import MbDFEM
import Part


class AnnuAnnuFacePairTest(unittest.TestCase):
    def setUp(self):
        self.document = App.newDocument("AnnulusFacePairTest")
        self.first = self.document.addObject("Part::Feature", "First")
        self.second = self.document.addObject("Part::Feature", "Second")
        self.pair = self.document.addObject("MbDFEM::AnnuAnnuFacePair", "Pair")
        self.pair.faceI = (self.first, ["Face1"])
        self.pair.faceJ = (self.second, ["Face1"])

    def tearDown(self):
        App.closeDocument(self.document.Name)

    @staticmethod
    def disk(radius, center=None, split=False):
        center = center or App.Vector()
        if split:
            circle = Part.Circle(center, App.Vector(0, 0, 1), radius)
            wire = Part.Wire([circle.toShape(0, math.pi), circle.toShape(math.pi, 2 * math.pi)])
        else:
            wire = Part.Wire([Part.makeCircle(radius, center)])
        return Part.Face(wire)

    @classmethod
    def annulus(cls, inner=2, outer=5, split=False):
        return cls.disk(outer, split=split).cut(cls.disk(inner, split=split))

    def validate(self):
        return MbDFEM.annuAnnuValidateGeometry(self.pair)

    def test_annulus_on_either_side_and_opposite_normals(self):
        self.first.Shape = self.annulus()
        self.second.Shape = self.disk(6).reversed()
        result = self.validate()
        self.assertEqual(result["annulusSide"], "I")
        self.assertAlmostEqual(result["innerRadius"], 2)
        self.assertAlmostEqual(result["outerRadius"], 5)
        self.pair.faceI, self.pair.faceJ = self.pair.faceJ, self.pair.faceI
        self.assertEqual(self.validate()["annulusSide"], "J")

    def test_split_circular_wires_and_coincident_boundaries(self):
        self.first.Shape = self.annulus(split=True)
        self.second.Shape = self.disk(5)
        self.assertEqual(self.validate()["annulusSide"], "I")
        self.second.Shape = self.first.Shape.copy()
        self.assertEqual(self.validate()["annulusSide"], "I")

    def test_smaller_annulus_selected_by_area(self):
        self.first.Shape = self.annulus(1, 6)
        self.second.Shape = self.annulus(2, 5)
        self.assertEqual(self.validate()["annulusSide"], "J")

    def test_requires_true_annulus(self):
        self.second.Shape = self.disk(10)
        for shape in (self.disk(5), self.disk(5).cut(self.disk(1, App.Vector(1, 0, 0))),
                      self.annulus().common(Part.makeBox(10, 10, 2, App.Vector(0, -5, -1)))):
            with self.subTest(shape=shape):
                self.first.Shape = shape
                with self.assertRaisesRegex(RuntimeError, "annulus face"):
                    self.validate()

    def test_requires_coplanarity(self):
        self.first.Shape = self.annulus()
        self.second.Shape = self.disk(6)
        for placement in (App.Placement(App.Vector(0, 0, 1), App.Rotation()),
                          App.Placement(App.Vector(), App.Rotation(App.Vector(1, 0, 0), 5))):
            self.second.Placement = placement
            with self.assertRaisesRegex(RuntimeError, "coplanar"):
                self.validate()
        self.second.Shape = Part.makeCylinder(6, 1)
        with self.assertRaisesRegex(RuntimeError, "coplanar"):
            self.validate()

    def test_entire_region_must_be_contained(self):
        self.first.Shape = self.annulus()
        # The offset hole is entirely inside the ring: outer-boundary sampling
        # would miss it. A larger central hole also removes annular material.
        for other in (self.disk(4), self.disk(6).cut(self.disk(0.25, App.Vector(3, 0, 0))),
                      self.annulus(3, 6), self.disk(6, App.Vector(3, 0, 0))):
            with self.subTest(other=other):
                self.second.Shape = other
                with self.assertRaisesRegex(RuntimeError, "bounded"):
                    self.validate()

    def test_nested_placements_use_common_coordinates(self):
        assembly = self.document.addObject("App::Part", "Assembly")
        assembly.addObject(self.first)
        self.first.Shape = self.annulus()
        assembly.Placement = App.Placement(App.Vector(10, 20, 30),
                                            App.Rotation(App.Vector(1, 0, 0), 90))
        self.second.Shape = self.disk(6)
        self.second.Placement = assembly.Placement
        result = self.validate()
        self.assertLess(result["center"].distanceToPoint(App.Vector(10, 20, 30)), 1e-7)
        self.second.Placement = App.Placement()
        with self.assertRaisesRegex(RuntimeError, "coplanar"):
            self.validate()

    def test_recompute_rechecks_changed_geometry(self):
        self.first.Shape = self.annulus()
        self.second.Shape = self.disk(6)
        self.document.recompute()
        self.assertNotIn("Invalid", self.pair.State)
        self.second.Shape = self.disk(4)
        self.document.recompute()
        self.assertIn("Invalid", self.pair.State)
        self.second.Shape = self.disk(6)
        self.document.recompute()
        self.assertNotIn("Invalid", self.pair.State)
        self.second.Placement.Base = App.Vector(0, 0, 1)
        self.document.recompute()
        self.assertIn("Invalid", self.pair.State)

    def test_invalid_references_and_tolerances(self):
        with self.assertRaisesRegex(RuntimeError, "valid face"):
            self.validate()
        self.first.Shape = self.annulus()
        self.second.Shape = self.disk(6)
        self.pair.faceJ = (self.second, ["Face1", "Face1"])
        with self.assertRaisesRegex(RuntimeError, "exactly one"):
            self.validate()
        self.pair.faceJ = (self.second, ["Face1"])
        for tolerance in (0, float("nan"), float("inf")):
            with self.assertRaisesRegex(RuntimeError, "tolerances"):
                MbDFEM.annuAnnuValidateGeometry(self.pair, tolerance)

    @staticmethod
    def contact_nodes(uneven=False):
        nodes = []
        for quadrant in range(4):
            count = quadrant + 2 if uneven else 4
            for index in range(count):
                angle = quadrant * math.pi / 2 + (index + 1) * math.pi / (2 * (count + 1))
                radius = 3 + 0.15 * index
                nodes.append((len(nodes) + 1, App.Vector(radius * math.cos(angle),
                                                         radius * math.sin(angle), 0)))
        return nodes

    def configure_contact(self):
        self.first.Shape = self.annulus()
        self.second.Shape = self.disk(6).reversed()

    def face_load(self, nodes, force=None, torque=None, origin=None, part=None):
        return MbDFEM.annuAnnuFaceLoad(self.pair, part or self.first, nodes,
                                      force or App.Vector(), torque or App.Vector(),
                                      origin or App.Vector())

    def assert_wrench(self, records, nodes, origin, force, torque):
        positions = dict(nodes)
        resultant, moment = App.Vector(), App.Vector()
        for node, dof, value in records:
            vector = App.Vector()
            vector[dof - 1] = value
            resultant += vector
            moment += (positions[node] - origin).cross(vector)
        self.assertLess(resultant.distanceToPoint(force), 1e-8)
        self.assertLess(moment.distanceToPoint(torque), 1e-8)

    def test_combined_wrench_components_and_quadrant_profiles(self):
        self.configure_contact()
        nodes = self.contact_nodes(uneven=True)
        force, torque = App.Vector(7, -3, 11), App.Vector(13, 5, -17)
        marker = App.Vector(1, -2, 3)
        for cost in ("C", "C2"):
            with self.subTest(cost=cost):
                self.pair.loadCost = cost
                load = self.face_load(nodes, force, torque, marker)
                expected_torque = torque + marker.cross(force)
                self.assert_wrench(load["cloads"], nodes, load["origin"], force, expected_torque)
                self.assertEqual(len(load["cloads"]), len({(n, d) for n, d, _ in load["cloads"]}))
                z = load["z_axis"]
                components = {
                    "transverse_force": (force - z * force.dot(z), App.Vector()),
                    "axial_force": (z * force.dot(z), App.Vector()),
                    "bending_torque": (App.Vector(), expected_torque - z * expected_torque.dot(z)),
                    "axial_torque": (App.Vector(), z * expected_torque.dot(z)),
                }
                summed = {}
                for name, records in load["cload_components"].items():
                    self.assert_wrench(records, nodes, load["origin"], *components[name])
                    vectors = {}
                    for node, dof, value in records:
                        summed[node, dof] = summed.get((node, dof), 0) + value
                        vector = vectors.setdefault(node, App.Vector())
                        vector[dof - 1] += value
                    regions = load["force_quadrants" if name.endswith("force") else "torque_quadrants"]
                    for ids in regions.values():
                        magnitudes = []
                        for node in ids:
                            if name == "transverse_force":
                                basis = load["x_axis"]
                            elif name == "axial_torque":
                                radial = dict(nodes)[node] - load["origin"]
                                basis = z.cross(radial) / radial.Length
                            else:
                                basis = z
                            magnitude = vectors.get(node, App.Vector()).dot(basis)
                            if name == "bending_torque":
                                node_x = (dict(nodes)[node] - load["origin"]).dot(load["torque_x_axis"])
                                if abs(node_x) < 1e-12:
                                    self.assertLess(abs(magnitude), 1e-9)
                                    continue
                                magnitude /= node_x
                            magnitudes.append(magnitude)
                        if magnitudes:
                            self.assertLess(max(magnitudes) - min(magnitudes), 1e-9)
                for node, dof, value in load["cloads"]:
                    self.assertAlmostEqual(value, summed[node, dof], places=10)

    def test_bending_node_x_profile_on_both_contact_sides(self):
        import numpy as np

        self.configure_contact()
        nodes = self.contact_nodes(uneven=True) + [(100, App.Vector(0, 3, 0)),
                                                  (101, App.Vector(0, -4, 0))]
        positions = dict(nodes)
        for part in (self.first, self.second):
            for requested in (13, -13):
                costs = {}
                for cost in ("C", "C2"):
                    with self.subTest(part=part.Name, torque=requested, cost=cost):
                        self.pair.loadCost = cost
                        torque = App.Vector(0, requested, 0)
                        load = self.face_load(nodes, torque=torque, part=part)
                        records = load["cload_components"]["bending_torque"]
                        self.assert_wrench(records, nodes, load["origin"], App.Vector(), torque)
                        vectors = {}
                        for node, dof, value in records:
                            vectors.setdefault(node, App.Vector())[dof - 1] += value
                        matrix = np.zeros((6, 4))
                        coefficients, weights = np.zeros(4), np.zeros(4)
                        for q, ids in enumerate(load["torque_quadrants"].values()):
                            ratios = []
                            for node in ids:
                                relative = positions[node] - load["origin"]
                                node_x = relative.dot(load["torque_x_axis"])
                                basis = load["z_axis"] * node_x
                                vector = vectors.get(node, App.Vector())
                                self.assertLess(vector.cross(load["z_axis"]).Length, 1e-9)
                                matrix[:, q] += tuple(basis) + tuple(relative.cross(basis))
                                weights[q] += node_x * node_x
                                if abs(node_x) < 1e-12:
                                    self.assertLess(vector.Length, 1e-9)
                                else:
                                    ratios.append(vector.dot(load["z_axis"]) / node_x)
                            self.assertLess(max(ratios) - min(ratios), 1e-9)
                            coefficients[q] = ratios[0]
                        # Every feasible coefficient perturbation lies in this
                        # null space; the selected objective must be stationary.
                        _, singular, vh = np.linalg.svd(matrix, full_matrices=True)
                        rank = sum(singular > 1e-10)
                        gradient = coefficients if cost == "C" else coefficients * weights
                        self.assertLess(np.linalg.norm(vh[rank:] @ gradient), 1e-8)
                        costs[cost] = sum(vector.dot(vector) for vector in vectors.values())
                self.assertLessEqual(costs["C2"], costs["C"] + 1e-9)

    def test_c2_default_cost_choice_and_persistence(self):
        self.configure_contact()
        self.assertEqual(self.pair.loadCost, "C2")
        nodes = self.contact_nodes(uneven=True)
        force = App.Vector(10, 0, 0)
        c2 = self.face_load(nodes, force)["cloads"]
        self.pair.loadCost = "C"
        c = self.face_load(nodes, force)["cloads"]
        self.assertGreater(max(abs(a[2] - b[2]) for a, b in zip(c, c2)), 1e-4)
        self.assertLessEqual(sum(v * v for _, _, v in c2), sum(v * v for _, _, v in c) + 1e-9)
        with tempfile.TemporaryDirectory() as directory:
            filename = os.path.join(directory, "AnnularLoadCost.FCStd")
            self.document.saveAs(filename)
            pair_name = self.pair.Name
            App.closeDocument(self.document.Name)
            self.document = App.openDocument(filename)
            self.pair = self.document.getObject(pair_name)
            self.first = self.document.getObject("First")
            self.second = self.document.getObject("Second")
            self.assertEqual(self.pair.loadCost, "C")
            self.assertEqual(self.face_load(nodes, force)["cloads"], c)

    def test_contact_band_boundary_partition_and_other_face(self):
        self.configure_contact()
        nodes = [(1, App.Vector(2, 0, 0)), (2, App.Vector(0, 5, 0)),
                 (3, App.Vector(-2, 0, 0)), (4, App.Vector(0, -5, 0)),
                 (5, App.Vector(0, 0, 0)), (6, App.Vector(5.5, 0, 0)),
                 (7, App.Vector(3, 0, 1))]
        for part in (self.first, self.second):
            load = self.face_load(nodes, App.Vector(0, 0, 12), part=part)
            for key in ("force_quadrants", "torque_quadrants"):
                ids = [node for region in load[key].values() for node in region]
                self.assertEqual(sorted(ids), [1, 2, 3, 4])
                self.assertEqual(len(set(ids)), len(ids))
            self.assert_wrench(load["cloads"], nodes, load["origin"], App.Vector(0, 0, 12), App.Vector())

    def test_sparse_feasible_redundant_constraints_and_infeasible_mesh(self):
        self.configure_contact()
        nodes = [(1, App.Vector(3, 3, 0)), (2, App.Vector(-3, -3, 0))]
        load = self.face_load(nodes, App.Vector(0, 0, 10))
        self.assert_wrench(load["cloads"], nodes, load["origin"], App.Vector(0, 0, 10), App.Vector())
        self.assertEqual(self.face_load([])["cloads"], [])
        for sparse, force, torque in (([], App.Vector(0, 0, 1), App.Vector()),
                                     (nodes[:1], App.Vector(0, 0, 1), App.Vector()),
                                     (nodes, App.Vector(), App.Vector(1, 0, 0))):
            with self.assertRaisesRegex(RuntimeError, "equilibrium"):
                self.face_load(sparse, force, torque)

    def test_rotated_part_frames_fallback_and_reversed_face_order(self):
        self.configure_contact()
        common = App.Placement(App.Vector(10, 20, 30), App.Rotation(App.Vector(1, 2, 3), 47))
        self.first.Placement = common
        self.second.Placement = common * App.Placement(App.Vector(), App.Rotation(App.Vector(0, 0, 1), 31))
        for part in (self.first, self.second):
            nodes = self.contact_nodes()
            for force, torque in ((App.Vector(), App.Vector()),
                                  (App.Vector(0, 0, 6), App.Vector(0, 0, 9)),
                                  (App.Vector(), App.Vector(2, 3, 0)),
                                  (App.Vector(4, 5, 6), App.Vector(7, 8, 9))):
                load = self.face_load(nodes, force, torque, part=part)
                self.assert_wrench(load["cloads"], nodes, load["origin"], force, torque)
                self.assertLess(load["x_axis"].cross(load["y_axis"]).distanceToPoint(load["z_axis"]), 1e-9)
                self.assertLess(load["torque_x_axis"].cross(load["torque_y_axis"]).distanceToPoint(load["z_axis"]), 1e-9)
        self.pair.faceI, self.pair.faceJ = self.pair.faceJ, self.pair.faceI
        load = self.face_load(self.contact_nodes(), App.Vector(1, 2, 3))
        self.assertEqual(load["annulusSide"], "J")
        self.assert_wrench(load["cloads"], self.contact_nodes(), load["origin"], App.Vector(1, 2, 3), App.Vector())

    def test_bad_nodes_and_changed_geometry_rejected_before_loading(self):
        self.configure_contact()
        for nodes in ([(1, App.Vector(3, 0, 0)), (1, App.Vector(-3, 0, 0))],
                      [(0, App.Vector(3, 0, 0))], [(1, App.Vector(float("nan"), 0, 0))]):
            with self.assertRaisesRegex(RuntimeError, "distinct positive IDs"):
                self.face_load(nodes)
        with self.assertRaisesRegex(RuntimeError, "finite"):
            self.face_load(self.contact_nodes(), App.Vector(float("inf"), 0, 0))
        self.second.Shape = self.disk(4)
        with self.assertRaisesRegex(RuntimeError, "bounded"):
            self.face_load(self.contact_nodes(), App.Vector(1, 0, 0))

    def test_joint_samples_shares_signs_and_export_preserve_marker_wrench(self):
        from TestMbDFEMApp import MbDFEMAssemblyTest
        Embedded = MbDFEMAssemblyTest._load_embedded_module_for_app_test()
        assembly = self.document.addObject("MbDFEM::MbDAssembly", "Assembly")
        assembly.Placement = App.Placement(App.Vector(10, -20, 30), App.Rotation(13, 27, 41))
        ring = self.document.addObject("MbDFEM::MbDPart", "Ring")
        other = self.document.addObject("MbDFEM::MbDPart", "Other")
        ring.Shape = Part.makeCylinder(5, 1, App.Vector(0, 0, -1)).cut(
            Part.makeCylinder(2, 1, App.Vector(0, 0, -1)))
        # A shoulder supplies both a containing annulus and a matching pin.
        other.Shape = Part.makeCylinder(6, 1).fuse(Part.makeCylinder(2, 1, App.Vector(0, 0, -1)))
        assembly.addPart(ring)
        assembly.addPart(other)
        contact = lambda part: next("Face" + str(i + 1) for i, face in enumerate(part.Shape.Faces)
                                    if face.Surface.TypeId == "Part::GeomPlane"
                                    and abs(face.CenterOfMass.z) < 1e-8)
        marker_i = self.document.addObject("MbDFEM::MbDMarker", "MarkerI")
        marker_j = self.document.addObject("MbDFEM::MbDMarker", "MarkerJ")
        ring.addMarker(marker_i)
        other.addMarker(marker_j)
        marker_i.Placement.Base = App.Vector(1, 2, 3)
        joint = self.document.addObject("MbDFEM::MbDJoint", "Joint")
        joint.markerI, joint.markerJ = marker_i, marker_j
        joint.fxs, joint.fys, joint.fzs = [6, 10], [-2, 4], [3, 7]
        joint.txs, joint.tys, joint.tzs = [11, 15], [8, 12], [-3, 5]
        for part in (ring, other):
            part.xs, part.ys, part.zs = [1, 5], [2, 6], [3, 7]
            part.bryxs, part.bryys, part.bryzs = [0.1, 0.3], [0.2, 0.4], [0.3, 0.5]
        second_pair = self.document.addObject("MbDFEM::AnnuAnnuFacePair", "SecondPair")
        self.pair.faceI, self.pair.faceJ = (ring, [contact(ring)]), (other, [contact(other)])
        # Reverse the second pair's stored links; marker-I signs must remain unchanged.
        second_pair.faceI, second_pair.faceJ = self.pair.faceJ, self.pair.faceI
        pairs = [self.pair, second_pair]
        nodes = self.contact_nodes(uneven=True)
        for sample in ((-1, -1, 0.0), (0, 1, 0.4)):
            lower, upper, ratio = sample
            for target, sign in ((ring, 1), (other, -1)):
                generate = (MbDFEM.annuAnnuJointAnnulusLoad if target is ring
                            else MbDFEM.annuAnnuJointOtherAnnulusLoad)
                wrong_role = (MbDFEM.annuAnnuJointOtherAnnulusLoad if target is ring
                              else MbDFEM.annuAnnuJointAnnulusLoad)
                with self.assertRaisesRegex(RuntimeError, "Requested FacePair side"):
                    wrong_role(self.pair, joint, target, nodes, pairs, *sample)
                loads = [generate(pair, joint, target, nodes, pairs + [pair], *sample)
                         for pair in pairs]
                state = loads[0]["joint_state"]
                if lower < 0:
                    placement = target.getGlobalPlacement()
                    expected_force, expected_torque = App.Vector(6, -2, 3), App.Vector(11, 8, -3)
                else:
                    rotation = lambda i: (App.Rotation(App.Vector(0, 0, 1), math.degrees(target.bryzs[i]))
                                          * App.Rotation(App.Vector(0, 1, 0), math.degrees(target.bryys[i]))
                                          * App.Rotation(App.Vector(1, 0, 0), math.degrees(target.bryxs[i])))
                    local = App.Placement(App.Vector(2.6, 3.6, 4.6), rotation(0).slerp(rotation(1), ratio))
                    placement = assembly.getGlobalPlacement() * local
                    expected_force, expected_torque = App.Vector(7.6, 0.4, 4.6), App.Vector(12.6, 9.6, 0.2)
                expected_marker = placement.multVec(marker_i.Placement.Base)
                self.assertLess(state["forceOnFaceIatOrigin"].distanceToPoint(expected_force * 0.5), 1e-8)
                expected_origin_torque = (expected_torque * 1000
                    + (expected_marker - state["forceCoord"].Base).cross(expected_force)) * 0.5
                self.assertLess(state["torqueOnFaceIatOrigin"].distanceToPoint(expected_origin_torque), 1e-8)
                local_force = placement.Rotation.inverted().multVec(expected_force * sign)
                local_torque = placement.Rotation.inverted().multVec(expected_torque * (sign * 1000))
                exported = []
                for load in loads:
                    self.assert_wrench(load["cloads"], nodes, marker_i.Placement.Base,
                                       local_force * 0.5, local_torque * 0.5)
                    for name in ("forceCoord", "torqueCoord"):
                        self.assertLess(load["joint_state"][name].Base.distanceToPoint(state[name].Base), 1e-8)
                        self.assertTrue(load["joint_state"][name].Rotation.isSame(state[name].Rotation, 1e-8))
                    for line in Embedded._format_joint_face_pair_cloads(load).splitlines():
                        if not line.startswith("*"):
                            n, d, v = line.split(",")
                            exported.append((int(n), int(d), float(v)))
                self.assert_wrench(exported, nodes, marker_i.Placement.Base, local_force, local_torque)
                original_pairs = Embedded._joint_face_pairs
                try:
                    Embedded._joint_face_pairs = lambda _joint: [
                        {"type": "AnnuAnnu", "partI": ring, "partJ": other,
                         "faceI": ring.Shape.getElement(contact(ring)),
                         "faceJ": other.Shape.getElement(contact(other)), "object": pair}
                        for pair in pairs]
                    bridged = Embedded._joint_loads_for_fem_part(joint, target, dict(nodes), sample=sample)
                    self.assertEqual(len(bridged), 2)
                    self.assertTrue(all(load["face_role"] == ("annulus" if target is ring else "other")
                                        for load in bridged))
                    self.assertIn("FQ1", Embedded._format_joint_face_pair_nsets(bridged[0]))
                    from types import SimpleNamespace
                    original_loads = Embedded._mbd_joint_loads
                    try:
                        Embedded._mbd_joint_loads = lambda *_args, **_kwargs: bridged
                        with tempfile.TemporaryDirectory() as directory:
                            filename = os.path.join(directory, "annular.inp")
                            with open(filename, "w", encoding="utf-8") as stream:
                                stream.write("*HEADING\nAnnular contact\n*STEP\n*STATIC\n*END STEP\n")
                            Embedded._add_mbd_joint_loads_to_inp(filename, SimpleNamespace(mesh=None))
                            with open(filename, encoding="utf-8") as stream:
                                content = stream.read()
                            self.assertIn("NSET=NS{}_FQ1".format(self.pair.Name), content)
                            self.assertIn("NSET=NS{}_FQ1".format(second_pair.Name), content)
                            self.assertIn("annular combined force and torque", content)
                            cloads = []
                            in_cload = False
                            for line in content.splitlines():
                                if line.startswith("**"):
                                    continue
                                if line.startswith("*"):
                                    in_cload = line.startswith("*CLOAD")
                                elif in_cload and line.strip():
                                    n, d, v = line.split(",")
                                    cloads.append((int(n), int(d), float(v)))
                            self.assert_wrench(cloads, nodes, marker_i.Placement.Base, local_force, local_torque)
                    finally:
                        Embedded._mbd_joint_loads = original_loads
                    with self.assertRaisesRegex(RuntimeError, "equilibrium"):
                        Embedded._joint_loads_for_fem_part(joint, target, {1: nodes[0][1]}, sample=sample)
                finally:
                    Embedded._joint_face_pairs = original_pairs
        cylinder_pair = self.document.addObject("MbDFEM::CylCylFacePair", "CylinderPair")
        cylinder_face = lambda part: next("Face" + str(i + 1) for i, face in enumerate(part.Shape.Faces)
                                         if face.Surface.TypeId == "Part::GeomCylinder"
                                         and abs(face.Surface.Radius - 2) < 1e-8)
        cylinder_pair.faceI = (ring, [cylinder_face(ring)])
        cylinder_pair.faceJ = (other, [cylinder_face(other)])
        mixed_nodes = dict(nodes)
        for height in (-0.75, -0.25):
            for i in range(32):
                angle = 2 * math.pi * (i + 0.5) / 32
                mixed_nodes[100 + len(mixed_nodes)] = App.Vector(2 * math.cos(angle), 2 * math.sin(angle), height)
        original_pairs = Embedded._joint_face_pairs
        try:
            descriptions = []
            for pair in (self.pair, cylinder_pair):
                index_i, index_j = int(pair.faceI[1][0][4:]), int(pair.faceJ[1][0][4:])
                description = Embedded._make_joint_face_pair(
                    ring, index_i, ring.Shape.Faces[index_i - 1],
                    other, index_j, other.Shape.Faces[index_j - 1])
                description["object"] = pair
                descriptions.append(description)
            Embedded._joint_face_pairs = lambda _joint: descriptions
            mixed = Embedded._joint_loads_for_fem_part(joint, ring, mixed_nodes)
            self.assertEqual(len(mixed), 2)
            expected_force = ring.getGlobalPlacement().Rotation.inverted().multVec(App.Vector(6, -2, 3))
            expected_torque = ring.getGlobalPlacement().Rotation.inverted().multVec(App.Vector(11, 8, -3) * 1000)
            exported = []
            for load in mixed:
                self.assertLess(load["force"].distanceToPoint(expected_force * 0.5), 1e-8)
                for line in Embedded._format_joint_face_pair_cloads(load).splitlines():
                    if not line.startswith("*"):
                        n, d, v = line.split(",")
                        exported.append((int(n), int(d), float(v)))
            self.assert_wrench(exported, list(mixed_nodes.items()), marker_i.Placement.Base,
                               expected_force, expected_torque)
        finally:
            Embedded._joint_face_pairs = original_pairs
        with self.assertRaisesRegex(RuntimeError, "interpolation ratio"):
            MbDFEM.annuAnnuJointAnnulusLoad(self.pair, joint, ring, nodes, pairs, 0, 1, 1.5)
        with self.assertRaisesRegex(RuntimeError, "participant"):
            MbDFEM.annuAnnuJointAnnulusLoad(self.pair, joint, ring, nodes, [])
        other.zs = [4, 8]
        with self.assertRaisesRegex(RuntimeError, "coplanar"):
            MbDFEM.annuAnnuJointAnnulusLoad(self.pair, joint, ring, nodes, pairs, 0, 1, 0.4)
