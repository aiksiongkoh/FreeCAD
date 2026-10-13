// SPDX-License-Identifier: LGPL-2.1-or-later

#include "CylCylFacePair.h"
#include "FEMHole2PinFlangeJoint.h"
#include "FEMHolePinJoint.h"
#include "JointLoadUtils.h"
#include "MbDJoint.h"
#include "MbDPart.h"
#include "MbDMarker.h"
#include "MbDAssembly.h"
#include <App/Document.h>
#include <Base/Matrix.h>
#include <BRepAdaptor_Surface.hxx>
#include <BRep_Tool.hxx>
#include <TopExp_Explorer.hxx>
#include <TopoDS.hxx>
#include <gp_Cylinder.hxx>
#include <unordered_set>

#include <BRepBuilderAPI_MakeVertex.hxx>
#include <BRepBuilderAPI_Transform.hxx>
#include <BRepExtrema_DistShapeShape.hxx>
#include <TopoDS_Face.hxx>

#include <algorithm>
#include <cmath>
#include <limits>
#include <sstream>
#include <string>
#include <utility>
#include <gp_Pnt.hxx>
#include <Eigen/SVD>
#include <stdexcept>
#include <unordered_map>

PROPERTY_SOURCE(MbDFEM::CylCylFacePair, MbDFEM::FacePair)

const char* MbDFEM::CylCylFacePair::LoadCostEnums[] = {"C", "C2", nullptr};

MbDFEM::CylCylFacePair::CylCylFacePair()
{
    loadCost.setEnums(LoadCostEnums);
    ADD_PROPERTY_TYPE(
        loadCost,
        (long(1)),
        "MbDFEM",
        App::Prop_None,
        "C: minimum region coefficient; C2: minimum nodal magnitude"
    );
}

namespace
{
// Contact-node distances are measured in millimetres.
constexpr double contactNodeTolerance = 0.001;


Base::Vector3d normalizedPerpendicularAxis(const Base::Vector3d& axis, const Base::Vector3d& preferred)
{
    Base::Vector3d result = preferred - axis * preferred.Dot(axis);
    if (result.Length() <= Base::Vector3d::epsilon()) {
        const Base::Vector3d fallback = std::abs(axis.Dot(Base::Vector3d::UnitX)) < 0.9
            ? Base::Vector3d::UnitX
            : Base::Vector3d::UnitY;
        result = fallback - axis * fallback.Dot(axis);
    }
    if (result.Length() <= Base::Vector3d::epsilon()) {
        return Base::Vector3d();
    }
    result.Normalize();
    return result;
}

void appendCLOADs(
    std::vector<MbDFEM::CylCylFacePair::CLOAD>& cloads,
    const std::vector<MbDFEM::CylCylFacePair::NodalForce>& nodalForces,
    double tolerance
)
{
    // tolerance is geometric (millimetres), so it must not be used to filter
    // force components.  Doing so changes the resultant on fine meshes where
    // valid per-node forces can be smaller than the geometry tolerance.
    (void)tolerance;
    for (const MbDFEM::CylCylFacePair::NodalForce& nodalForce : nodalForces) {
        const double components[3] = {nodalForce.force.x, nodalForce.force.y, nodalForce.force.z};
        for (int index = 0; index < 3; ++index) {
            if (components[index] != 0.0) {
                cloads.push_back({nodalForce.nodeId, index + 1, components[index]});
            }
        }
    }
}

bool pointTouchesFace(const Base::Vector3d& point, const TopoDS_Face& face, double tolerance)
{
    if (face.IsNull()) {
        return false;
    }
    BRepBuilderAPI_MakeVertex builder(gp_Pnt(point.x, point.y, point.z));
    if (!builder.IsDone()) {
        return false;
    }
    BRepExtrema_DistShapeShape distance(face, builder.Vertex());
    return distance.IsDone() && distance.Value() <= tolerance;
}

using Pair = MbDFEM::CylCylFacePair;

struct CylinderReference
{
    Pair::CylindricalFaceGeometry geometry;
    double radius;
};

CylinderReference cylinderReference(const App::PropertyLinkSub& link)
{
    const auto* part = freecad_cast<MbDFEM::MbDPart*>(link.getValue());
    if (!part || link.getSubValues().empty()) {
        throw std::runtime_error("Cylindrical FacePair requires two part face references.");
    }
    const auto face = TopoDS::Face(
        part->Shape.getShape().getSubShape(link.getSubValues().front().c_str())
    );
    BRepAdaptor_Surface surface(face);
    if (surface.GetType() != GeomAbs_Cylinder) {
        throw std::runtime_error("FacePair reference is not cylindrical.");
    }
    const auto cylinder = surface.Cylinder();
    const auto point = cylinder.Location();
    const auto axis = cylinder.Axis().Direction();
    CylinderReference result;
    auto& geometry = result.geometry;
    geometry.axisPoint = Base::Vector3d(point.X(), point.Y(), point.Z());
    geometry.axisDirection = Base::Vector3d(axis.X(), axis.Y(), axis.Z());
    result.radius = cylinder.Radius();
    geometry.axialMin = std::numeric_limits<double>::infinity();
    geometry.axialMax = -geometry.axialMin;
    for (TopExp_Explorer vertices(face, TopAbs_VERTEX); vertices.More(); vertices.Next()) {
        const auto p = BRep_Tool::Pnt(TopoDS::Vertex(vertices.Current()));
        const double z
            = (Base::Vector3d(p.X(), p.Y(), p.Z()) - geometry.axisPoint).Dot(geometry.axisDirection);
        geometry.axialMin = std::min(geometry.axialMin, z);
        geometry.axialMax = std::max(geometry.axialMax, z);
    }
    if (!std::isfinite(geometry.axialMin) || !std::isfinite(geometry.axialMax)) {
        throw std::runtime_error("Cylinder has no bounded axial span.");
    }
    gp_Pnt sample;
    gp_Vec du, dv;
    surface.D1(
        (surface.FirstUParameter() + surface.LastUParameter()) * 0.5,
        (surface.FirstVParameter() + surface.LastVParameter()) * 0.5,
        sample,
        du,
        dv
    );
    auto normal = du.Crossed(dv);
    if (face.Orientation() == TopAbs_REVERSED) {
        normal.Reverse();
    }
    geometry.samplePoint = Base::Vector3d(sample.X(), sample.Y(), sample.Z());
    geometry.outwardNormal = Base::Vector3d(normal.X(), normal.Y(), normal.Z());
    const double midpoint = (geometry.axialMin + geometry.axialMax) * 0.5;
    geometry.axisPoint += geometry.axisDirection * midpoint;
    geometry.axialMin -= midpoint;
    geometry.axialMax -= midpoint;
    return result;
}

using MbDFEM::JointLoadUtils::markerPart;
using MbDFEM::JointLoadUtils::sampledPlacement;
using MbDFEM::JointLoadUtils::sampleValue;

// Check the wrench without coalescing the records used for debugging/export.
void checkWrench(
    const std::vector<Pair::HoleNode>& nodes,
    const Base::Vector3d& center,
    const std::vector<Pair::CLOAD>& loads,
    const Base::Vector3d& force,
    const Base::Vector3d& torque,
    const char* component
)
{
    std::unordered_map<int, Base::Vector3d> positions;
    double length = 0.0;
    for (const auto& node : nodes) {
        positions.emplace(node.id, node.position);
        length = std::max(length, (node.position - center).Length());
    }
    Base::Vector3d resultant;
    Base::Vector3d moment;
    for (const auto& load : loads) {
        Base::Vector3d value;
        value[load.dof - 1] = load.value;
        resultant += value;
        moment += (positions.at(load.nodeId) - center).Cross(value);
    }
    // Scale accuracy with the requested wrench so small loads still trigger
    // the nodal fallback when region coefficients cannot satisfy equilibrium.
    const double forceTolerance = 1.0e-8
            * std::max(force.Length(), torque.Length() / std::max(1.0, length))
        + 1.0e-12;
    const double momentTolerance = 1.0e-8 * std::max(torque.Length(), force.Length() * length)
        + 1.0e-12;
    if (!std::isfinite(resultant.Length()) || !std::isfinite(moment.Length())
        || (resultant - force).Length() > forceTolerance
        || (moment - torque).Length() > momentTolerance) {
        throw std::runtime_error(
            std::string("Hole ") + component
            + " cannot satisfy force/moment equilibrium; refine the face mesh."
        );
    }
}

// Minimize the actual nodal force magnitudes in the supplied admissible directions.
// This does not relax equilibrium or introduce nodes outside the contact patch.
std::vector<Pair::CLOAD> minimumNodalCLOADs(
    const std::vector<Pair::HoleNode>& nodes,
    const Base::Vector3d& center,
    const std::vector<Pair::NodalForce>& bases,
    const Base::Vector3d& force,
    const Base::Vector3d& torque,
    const char* component
)
{
    std::unordered_map<int, Base::Vector3d> positions;
    double length = 1.0;
    for (const auto& node : nodes) {
        positions.emplace(node.id, node.position);
        length = std::max(length, (node.position - center).Length());
    }
    if (bases.empty()) {
        checkWrench(nodes, center, {}, force, torque, component);
        return {};
    }
    Eigen::MatrixXd matrix = Eigen::MatrixXd::Zero(6, bases.size());
    std::vector<Base::Vector3d> unitBases;
    unitBases.reserve(bases.size());
    for (size_t column = 0; column < bases.size(); ++column) {
        auto basis = bases[column].force;
        const double norm = basis.Length();
        if (norm > 0.0) {
            basis /= norm;
        }
        unitBases.push_back(basis);
        const auto moment = (positions.at(bases[column].nodeId) - center).Cross(basis);
        for (int row = 0; row < 3; ++row) {
            matrix(row, column) = basis[row];
            matrix(row + 3, column) = moment[row] / length;
        }
    }
    Eigen::VectorXd rhs = Eigen::VectorXd::Zero(6);
    for (int row = 0; row < 3; ++row) {
        rhs[row] = force[row];
        rhs[row + 3] = torque[row] / length;
    }
    const Eigen::VectorXd coefficients
        = matrix.jacobiSvd(Eigen::ComputeThinU | Eigen::ComputeThinV).solve(rhs);
    std::vector<Pair::NodalForce> forces;
    for (size_t column = 0; column < bases.size(); ++column) {
        forces.push_back({bases[column].nodeId, unitBases[column] * coefficients[column]});
    }
    std::vector<Pair::CLOAD> result;
    appendCLOADs(result, forces, 0.0);
    checkWrench(nodes, center, result, force, torque, component);
    return result;
}

// Each column is one region's nodal force basis. Solve all six equilibrium
// rows (identically zero rows are harmless). Scale each column by its nodal
// basis norm for C2; unscaled columns implement C.
std::vector<Pair::CLOAD> torqueCLOADs(
    const std::vector<Pair::HoleNode>& nodes,
    const Base::Vector3d& center,
    const Base::Vector3d& xAxis,
    const Base::Vector3d& zAxis,
    const Base::Vector3d& torque,
    bool axial,
    bool nodalCost
)
{
    const Base::Vector3d yAxis = zAxis.Cross(xAxis);
    const int count = axial ? 8 : 4;
    Eigen::MatrixXd matrix = Eigen::MatrixXd::Zero(6, count);
    Eigen::VectorXd weights = Eigen::VectorXd::Zero(count);
    struct Basis
    {
        int node;
        int region;
        Base::Vector3d force;
    };
    std::vector<Basis> bases;
    double length = 0.0;
    for (const auto& node : nodes) {
        const Base::Vector3d relative = node.position - center;
        length = std::max(length, relative.Length());
        const double x = relative.Dot(xAxis);
        const double y = relative.Dot(yAxis);
        const double z = relative.Dot(zAxis);
        const double radius = std::hypot(x, y);
        if (radius == 0.0) {
            continue;
        }
        int region;
        Base::Vector3d basis;
        if (axial) {
            const int quadrant = x >= 0.0 ? (y >= 0.0 ? 0 : 3) : (y >= 0.0 ? 1 : 2);
            region = quadrant + (z >= 0.0 ? 0 : 4);
            basis = zAxis.Cross(relative - zAxis * z) / radius;
        }
        else {
            if ((z >= 0.0 && x < 0.0) || (z < 0.0 && x >= 0.0)) {
                continue;
            }
            region = (z >= 0.0 ? 0 : 2) + (y >= 0.0 ? 0 : 1);
            basis = xAxis * (z * x / radius);
        }
        const Base::Vector3d moment = relative.Cross(basis);
        for (int row = 0; row < 3; ++row) {
            matrix(row, region) += basis[row];
            matrix(row + 3, region) += moment[row];
        }
        bases.push_back({node.id, region, basis});
        weights[region] += basis.Sqr();
    }
    length = length > 0.0 ? length : 1.0;
    matrix.bottomRows(3) /= length;
    for (int region = 0; region < count; ++region) {
        weights[region] = nodalCost && weights[region] > 0.0 ? std::sqrt(weights[region]) : 1.0;
        matrix.col(region) /= weights[region];
    }
    Eigen::VectorXd rhs = Eigen::VectorXd::Zero(6);
    for (int row = 0; row < 3; ++row) {
        rhs[row + 3] = torque[row] / length;
    }
    const Eigen::VectorXd coefficients
        = matrix.jacobiSvd(Eigen::ComputeThinU | Eigen::ComputeThinV).solve(rhs);
    std::vector<Pair::NodalForce> forces;
    for (const auto& basis : bases) {
        forces.push_back(
            {basis.node, basis.force * (coefficients[basis.region] / weights[basis.region])}
        );
    }
    std::vector<Pair::CLOAD> result;
    appendCLOADs(result, forces, 0.0);
    const char* component = axial ? "axial torque" : "bending torque";
    try {
        checkWrench(nodes, center, result, Base::Vector3d(), torque, component);
        return result;
    }
    catch (const std::runtime_error&) {
        if (!nodalCost || bases.empty()) {
            throw;
        }
    }
    // A partial contact patch may have too few populated regions to satisfy
    // all equilibrium rows with one coefficient per region. C2 can instead
    // minimize the individual nodal forces on the same eligible contact nodes.
    std::vector<Pair::NodalForce> nodalBases;
    for (const auto& basis : bases) {
        nodalBases.push_back({basis.node, basis.force});
    }
    return minimumNodalCLOADs(nodes, center, nodalBases, Base::Vector3d(), torque, component);
}

}  // namespace

void MbDFEM::CylCylFacePair::updateJointState(
    const MbDJoint& joint,
    int lower,
    int upper,
    double ratio,
    int participatingPairCount
)
{
    if (participatingPairCount <= 0) {
        throw std::runtime_error("Participating FacePair count must be positive.");
    }
    const auto* markerI = freecad_cast<MbDMarker*>(joint.markerI.getValue());
    const auto* markerJ = freecad_cast<MbDMarker*>(joint.markerJ.getValue());
    const auto* partI = markerPart(markerI);
    const auto* partJ = markerPart(markerJ);
    if (partI == partJ
        || !(
            (faceI.getValue() == partI && faceJ.getValue() == partJ)
            || (faceI.getValue() == partJ && faceJ.getValue() == partI)
        )) {
        throw std::runtime_error("FacePair does not identify the two sides of this joint.");
    }
    if (upper < 0) {
        upper = lower;
    }
    if (!std::isfinite(ratio) || ratio < 0.0 || ratio > 1.0) {
        throw std::runtime_error("Joint sample interpolation ratio must be between zero and one.");
    }
    const auto referenceI = cylinderReference(faceI);
    const auto referenceJ = cylinderReference(faceJ);
    const auto roles = classifyFaces(referenceI.geometry, referenceJ.geometry);
    if (!roles.hasHoleAndPin()) {
        throw std::runtime_error("Cylindrical FacePair requires one hole and one pin.");
    }
    coordsOnFace = roles.faceIIsHole() ? IJUkn::I : IJUkn::J;
    const auto& hole = coordsOnFace == IJUkn::I ? referenceI : referenceJ;
    const auto* holePart = freecad_cast<MbDPart*>(
        coordsOnFace == IJUkn::I ? faceI.getValue() : faceJ.getValue()
    );
    const auto holePlacement = sampledPlacement(*holePart, lower, upper, ratio);
    const auto markerPlacement = sampledPlacement(*partI, lower, upper, ratio)
        * markerI->Placement.getValue();
    const auto sample = [=](const auto& series) {
        return sampleValue(series, lower) * (1.0 - ratio) + sampleValue(series, upper) * ratio;
    };
    const Base::Vector3d force(sample(joint.fxs), sample(joint.fys), sample(joint.fzs));
    const Base::Vector3d torque(sample(joint.txs), sample(joint.tys), sample(joint.tzs));
    Base::Vector3d origin, zAxis;
    holePlacement.multVec(hole.geometry.axisPoint, origin);
    holePlacement.getRotation().multVec(hole.geometry.axisDirection, zAxis);
    zAxis.Normalize();
    // Transfer the marker-I moment to the common hole origin before orienting
    // the torque frame and storing the face-origin wrench.
    const auto torqueAtOrigin = torque * JointLoadUtils::siTorqueToFEMTorque
        + (markerPlacement.getPosition() - origin).Cross(force);
    const auto forceSide = force - zAxis * force.Dot(zAxis);
    const auto forceXAxis = normalizedPerpendicularAxis(
        zAxis,
        forceSide.Length() > 1.0e-12 ? forceSide : torqueAtOrigin.Cross(zAxis)
    );
    const auto torqueXAxis = normalizedPerpendicularAxis(zAxis, torqueAtOrigin.Cross(zAxis));
    const auto frame = [&origin, &zAxis](const Base::Vector3d& xAxis) {
        const auto yAxis = zAxis.Cross(xAxis);
        Base::Matrix4D matrix;
        for (int row = 0; row < 3; ++row) {
            matrix[row][0] = xAxis[row];
            matrix[row][1] = yAxis[row];
            matrix[row][2] = zAxis[row];
        }
        return Base::Placement(origin, Base::Rotation(matrix));
    };
    // Commit only after geometry and sample validation have succeeded.
    forceCoord = frame(forceXAxis);
    torqueCoord = frame(torqueXAxis);
    forceOnFaceIatOrigin = force / static_cast<double>(participatingPairCount);
    torqueOnFaceIatOrigin = torqueAtOrigin / static_cast<double>(participatingPairCount);
}

MbDFEM::CylCylFacePair::JointHoleLoad MbDFEM::CylCylFacePair::jointHoleLoad(
    const MbDJoint& joint,
    const MbDPart& part,
    const std::vector<HoleNode>& nodes,
    const std::vector<FacePair*>& participatingPairs,
    int lower,
    int upper,
    double ratio
)
{
    return jointLoad(joint, part, nodes, participatingPairs, lower, upper, ratio, true);
}

MbDFEM::CylCylFacePair::JointHoleLoad MbDFEM::CylCylFacePair::jointPinLoad(
    const MbDJoint& joint,
    const MbDPart& part,
    const std::vector<HoleNode>& nodes,
    const std::vector<FacePair*>& participatingPairs,
    int lower,
    int upper,
    double ratio
)
{
    return jointLoad(joint, part, nodes, participatingPairs, lower, upper, ratio, false);
}

MbDFEM::CylCylFacePair::JointHoleLoad MbDFEM::CylCylFacePair::jointLoad(
    const MbDJoint& joint,
    const MbDPart& part,
    const std::vector<HoleNode>& nodes,
    const std::vector<FacePair*>& participatingPairs,
    int lower,
    int upper,
    double ratio,
    bool holeSide
)
{
    const auto* markerI = freecad_cast<MbDMarker*>(joint.markerI.getValue());
    const auto* markerJ = freecad_cast<MbDMarker*>(joint.markerJ.getValue());
    const auto* partI = markerPart(markerI);
    const auto* partJ = markerPart(markerJ);
    if (partI == partJ || (&part != partI && &part != partJ)) {
        throw std::runtime_error("Hole part does not identify one side of the joint.");
    }
    std::unordered_set<const FacePair*> participants;
    for (const auto* pair : participatingPairs) {
        if (pair
            && ((pair->faceI.getValue() == partI && pair->faceJ.getValue() == partJ)
                || (pair->faceI.getValue() == partJ && pair->faceJ.getValue() == partI))) {
            participants.insert(pair);
        }
    }
    if (participants.find(this) == participants.end()) {
        throw std::runtime_error("Hole FacePair is not a participant of this joint.");
    }
    if (!FEMHole2PinFlangeJoint::updateParticipatingPairs(joint, participatingPairs, lower, upper, ratio)
        && !FEMHolePinJoint::updateParticipatingPairs(joint, participatingPairs, lower, upper, ratio)) {
        updateJointState(joint, lower, upper, ratio, static_cast<int>(participants.size()));
    }
    const auto referenceI = cylinderReference(faceI);
    const auto referenceJ = cylinderReference(faceJ);
    const bool sideI = faceI.getValue() == &part;
    const bool requestedHole = (coordsOnFace == IJUkn::I && sideI)
        || (coordsOnFace == IJUkn::J && !sideI);
    if (requestedHole != holeSide) {
        throw std::runtime_error(
            holeSide ? "Requested FacePair side is not a cylindrical hole."
                     : "Requested FacePair side is not a cylindrical pin."
        );
    }
    const auto& reference = coordsOnFace == IJUkn::I ? referenceI : referenceJ;
    const auto& geometry = reference.geometry;
    if (upper < 0) {
        upper = lower;
    }
    if (!std::isfinite(ratio) || ratio < 0.0 || ratio > 1.0) {
        throw std::runtime_error("Joint sample interpolation ratio must be between zero and one.");
    }
    const auto placement = sampledPlacement(part, lower, upper, ratio);
    const auto inverse = placement.inverse();
    const double sign = &part == partI ? 1.0 : -1.0;
    JointHoleLoad result;
    inverse.multVec(forceCoord.getPosition(), result.origin);
    const auto globalAxis = forceCoord.getRotation().multVec(Base::Vector3d::UnitZ);
    inverse.getRotation().multVec(globalAxis, result.zAxis);
    inverse.getRotation().multVec(forceOnFaceIatOrigin * sign, result.force);
    inverse.getRotation().multVec(torqueOnFaceIatOrigin * sign, result.torque);
    // Select contact regions using the hole reaction on both sides. The pin
    // receives the opposite traction at the same contact patch, rather than
    // a hole-style load on the opposite half of the cylinder.
    const double contactSign = holeSide ? 1.0 : -1.0;
    const auto holeForce = result.force * contactSign;
    const auto holeTorque = result.torque * contactSign;
    const auto forceSide = holeForce - result.zAxis * holeForce.Dot(result.zAxis);
    result.xAxis = normalizedPerpendicularAxis(
        result.zAxis,
        forceSide.Length() > 1.0e-12 ? forceSide : holeTorque.Cross(result.zAxis)
    );
    result.yAxis = result.zAxis.Cross(result.xAxis);
    auto surfaceNodes = holeSurfaceNodes(
        nodes,
        result.origin,
        result.zAxis,
        reference.radius,
        geometry.axialMin,
        geometry.axialMax
    );
    if (!holeSide) {
        // Intersect the pin surface with the actual bounded hole face. This
        // excludes pin overhangs and respects circumferential face trimming.
        const auto& pinReference = sideI ? referenceI : referenceJ;
        const auto pinNodes = holeSurfaceNodes(
            nodes,
            pinReference.geometry.axisPoint,
            pinReference.geometry.axisDirection,
            pinReference.radius,
            pinReference.geometry.axialMin,
            pinReference.geometry.axialMax
        );
        std::unordered_set<int> pinIds;
        for (const auto& node : pinNodes) {
            pinIds.insert(node.id);
        }
        const auto& holeLink = coordsOnFace == IJUkn::I ? faceI : faceJ;
        const auto* holePart = freecad_cast<MbDPart*>(holeLink.getValue());
        const auto matrix = (inverse * sampledPlacement(*holePart, lower, upper, ratio)).toMatrix();
        gp_Trsf transform;
        transform.SetValues(
            matrix[0][0],
            matrix[0][1],
            matrix[0][2],
            matrix[0][3],
            matrix[1][0],
            matrix[1][1],
            matrix[1][2],
            matrix[1][3],
            matrix[2][0],
            matrix[2][1],
            matrix[2][2],
            matrix[2][3]
        );
        const auto holeFace = holePart->Shape.getShape().getSubShape(
            holeLink.getSubValues().front().c_str()
        );
        const auto contactFace = TopoDS::Face(
            BRepBuilderAPI_Transform(holeFace, transform, true).Shape()
        );
        const double tolerance = contactNodeTolerance;
        surfaceNodes.erase(
            std::remove_if(
                surfaceNodes.begin(),
                surfaceNodes.end(),
                [&](const auto& node) {
                    return !pinIds.count(node.id)
                        || !pointTouchesFace(node.position, contactFace, tolerance);
                }
            ),
            surfaceNodes.end()
        );
    }
    for (const auto& node : surfaceNodes) {
        const auto relative = node.position - result.origin;
        const double x = relative.Dot(result.xAxis), y = relative.Dot(result.yAxis);
        const int quadrant = x >= 0.0 ? (y >= 0.0 ? 0 : 3) : (y >= 0.0 ? 1 : 2);
        result.octants[quadrant + (relative.Dot(result.zAxis) >= 0.0 ? 0 : 4)].push_back(node.id);
    }
    result.components = holeCLOADs(
        surfaceNodes,
        result.origin,
        result.zAxis,
        reference.radius,
        geometry.axialMin,
        geometry.axialMax,
        holeForce,
        holeTorque
    );
    if (!holeSide) {
        for (auto* component :
             {&result.components.transverseForce,
              &result.components.axialForce,
              &result.components.bendingTorque,
              &result.components.axialTorque}) {
            for (auto& load : *component) {
                load.value = -load.value;
            }
        }
    }
    return result;
}

MbDFEM::CylCylFacePair::CylCylFacePair(
    App::DocumentObject* objectI,
    std::string subNameI,
    App::DocumentObject* objectJ,
    std::string subNameJ
)
    : CylCylFacePair()
{
    faceI.setValue(objectI, std::vector<std::string> {std::move(subNameI)});
    faceJ.setValue(objectJ, std::vector<std::string> {std::move(subNameJ)});
}

bool MbDFEM::CylCylFacePair::FaceRoles::hasHoleAndPin() const
{
    return (faceI == CylindricalFaceRole::Hole && faceJ == CylindricalFaceRole::Pin)
        || (faceI == CylindricalFaceRole::Pin && faceJ == CylindricalFaceRole::Hole);
}

bool MbDFEM::CylCylFacePair::FaceRoles::faceIIsHole() const
{
    return faceI == CylindricalFaceRole::Hole && faceJ == CylindricalFaceRole::Pin;
}

bool MbDFEM::CylCylFacePair::FaceRoles::faceJIsHole() const
{
    return faceJ == CylindricalFaceRole::Hole && faceI == CylindricalFaceRole::Pin;
}

MbDFEM::CylCylFacePair::CylindricalFaceRole MbDFEM::CylCylFacePair::cylindricalFaceRole(
    const CylindricalFaceGeometry& geometry,
    double tolerance
)
{
    Base::Vector3d axis = geometry.axisDirection;
    if (axis.Length() <= Base::Vector3d::epsilon()) {
        return CylindricalFaceRole::Unknown;
    }
    axis.Normalize();

    Base::Vector3d normal = geometry.outwardNormal;
    if (normal.Length() <= Base::Vector3d::epsilon()) {
        return CylindricalFaceRole::Unknown;
    }
    normal.Normalize();

    Base::Vector3d radial = geometry.samplePoint - geometry.axisPoint;
    radial -= axis * radial.Dot(axis);
    if (radial.Length() <= Base::Vector3d::epsilon()) {
        return CylindricalFaceRole::Unknown;
    }
    radial.Normalize();

    if (tolerance < 0.0) {
        tolerance = 1.0e-7;
    }

    const double alignment = normal.Dot(radial);
    if (alignment > tolerance) {
        return CylindricalFaceRole::Pin;
    }
    if (alignment < -tolerance) {
        return CylindricalFaceRole::Hole;
    }
    return CylindricalFaceRole::Unknown;
}

MbDFEM::CylCylFacePair::FaceRoles MbDFEM::CylCylFacePair::classifyFaces(
    const CylindricalFaceGeometry& faceIGeometry,
    const CylindricalFaceGeometry& faceJGeometry,
    double tolerance
)
{
    FaceRoles roles;
    roles.faceI = cylindricalFaceRole(faceIGeometry, tolerance);
    roles.faceJ = cylindricalFaceRole(faceJGeometry, tolerance);
    if (!roles.hasHoleAndPin()) {
        roles.faceI = CylindricalFaceRole::Unknown;
        roles.faceJ = CylindricalFaceRole::Unknown;
    }
    return roles;
}

std::vector<MbDFEM::CylCylFacePair::HoleNode> MbDFEM::CylCylFacePair::holeSurfaceNodes(
    const std::vector<HoleNode>& nodes,
    const Base::Vector3d& holeCenter,
    const Base::Vector3d& holeAxis,
    double holeRadius,
    double axialMin,
    double axialMax,
    double tolerance
) const
{
    Base::Vector3d axis = holeAxis;
    if (axis.Length() <= Base::Vector3d::epsilon() || holeRadius <= 0.0) {
        return {};
    }
    axis.Normalize();

    if (axialMin > axialMax) {
        std::swap(axialMin, axialMax);
    }

    if (tolerance < 0.0) {
        tolerance = contactNodeTolerance;
    }

    std::vector<HoleNode> surfaceNodes;
    for (const HoleNode& node : nodes) {
        const Base::Vector3d relative = node.position - holeCenter;
        const double axial = relative.Dot(axis);
        if (axial < axialMin - tolerance || axial > axialMax + tolerance) {
            continue;
        }

        const Base::Vector3d radial = relative - axis * axial;
        if (std::abs(radial.Length() - holeRadius) <= tolerance) {
            surfaceNodes.push_back(node);
        }
    }

    std::sort(surfaceNodes.begin(), surfaceNodes.end(), [](const HoleNode& left, const HoleNode& right) {
        return left.id < right.id;
    });
    return surfaceNodes;
}

void MbDFEM::CylCylFacePair::updatePinCoverage(
    const CylindricalFaceGeometry& faceIGeometry,
    const CylindricalFaceGeometry& faceJGeometry,
    double tolerance
)
{
    pinCoverage = {};
    pinCoverageWarning.clear();

    const FaceRoles roles = classifyFaces(faceIGeometry, faceJGeometry, tolerance);
    if (!roles.hasHoleAndPin()) {
        pinCoverageWarning = "Pin coverage cannot be checked because the cylindrical faces are not "
                             "a clear hole-pin pair.";
        return;
    }

    const CylindricalFaceGeometry& holeGeometry = roles.faceIIsHole() ? faceIGeometry : faceJGeometry;
    const CylindricalFaceGeometry& pinGeometry = roles.faceIIsHole() ? faceJGeometry : faceIGeometry;

    Base::Vector3d zAxis = holeGeometry.axisDirection;
    if (zAxis.Length() <= Base::Vector3d::epsilon()) {
        pinCoverageWarning
            = "Pin coverage cannot be checked because the hole force frame Z axis is invalid.";
        return;
    }
    zAxis.Normalize();

    Base::Vector3d pinAxis = pinGeometry.axisDirection;
    if (pinAxis.Length() <= Base::Vector3d::epsilon()) {
        pinCoverageWarning
            = "Pin coverage cannot be checked because the pin cylinder axis is invalid.";
        return;
    }
    pinAxis.Normalize();

    if (tolerance < 0.0) {
        tolerance = std::max(
                        {std::abs(holeGeometry.axialMax - holeGeometry.axialMin),
                         std::abs(pinGeometry.axialMax - pinGeometry.axialMin),
                         1.0}
                    )
            * 1.0e-6;
    }

    const double holeZ0
        = (holeGeometry.axisPoint + zAxis * holeGeometry.axialMin - holeGeometry.axisPoint).Dot(zAxis);
    const double holeZ1
        = (holeGeometry.axisPoint + zAxis * holeGeometry.axialMax - holeGeometry.axisPoint).Dot(zAxis);
    const double pinZ0
        = (pinGeometry.axisPoint + pinAxis * pinGeometry.axialMin - holeGeometry.axisPoint).Dot(zAxis);
    const double pinZ1
        = (pinGeometry.axisPoint + pinAxis * pinGeometry.axialMax - holeGeometry.axisPoint).Dot(zAxis);

    pinCoverage.hasGeometry = true;
    pinCoverage.holeZMin = std::min(holeZ0, holeZ1);
    pinCoverage.holeZMax = std::max(holeZ0, holeZ1);
    pinCoverage.pinZMin = std::min(pinZ0, pinZ1);
    pinCoverage.pinZMax = std::max(pinZ0, pinZ1);

    pinCoverage.coversHole = pinCoverage.pinZMin <= pinCoverage.holeZMin + tolerance
        && pinCoverage.pinZMax >= pinCoverage.holeZMax - tolerance;
    if (pinCoverage.coversHole) {
        return;
    }

    std::ostringstream message;
    message << "Pin cylindrical face does not fully cover the hole contact span in the hole force "
               "frame. "
            << "Hole z range: [" << pinCoverage.holeZMin << ", " << pinCoverage.holeZMax
            << "]. Pin z coverage: [" << pinCoverage.pinZMin << ", " << pinCoverage.pinZMax
            << "]. CLOADs will be applied only to the overlapping pin region.";
    pinCoverageWarning = message.str();
}

std::vector<MbDFEM::CylCylFacePair::NodalForce> MbDFEM::CylCylFacePair::holeNodalForces(
    const std::vector<HoleNode>& nodes,
    const Base::Vector3d& holeCenter,
    const Base::Vector3d& holeAxis,
    double holeRadius,
    double axialMin,
    double axialMax,
    const Base::Vector3d& centerForce,
    double tolerance
) const
{
    Base::Vector3d zAxis = holeAxis;
    if (zAxis.Length() <= Base::Vector3d::epsilon()) {
        return {};
    }
    zAxis.Normalize();

    const double nodeTolerance = tolerance < 0.0 ? contactNodeTolerance : tolerance;
    if (tolerance < 0.0) {
        tolerance = std::max({std::abs(holeRadius), std::abs(axialMax - axialMin), 1.0}) * 1.0e-6;
    }

    const Base::Vector3d axialForce = zAxis * centerForce.Dot(zAxis);
    Base::Vector3d xAxis = centerForce - axialForce;
    const double sideForce = xAxis.Length();
    if (sideForce <= tolerance) {
        return {};
    }
    xAxis /= sideForce;

    Base::Vector3d yAxis = zAxis.Cross(xAxis);
    if (yAxis.Length() <= Base::Vector3d::epsilon()) {
        return {};
    }
    yAxis.Normalize();
    xAxis = yAxis.Cross(zAxis);
    if (xAxis.Length() <= Base::Vector3d::epsilon()) {
        return {};
    }
    xAxis.Normalize();

    struct Candidate
    {
        HoleNode node;
        double localY = 0.0;
        double localZ = 0.0;
        double cosine = 0.0;
        int region = 0;
    };

    std::vector<Candidate> regions[4];
    for (const HoleNode& node :
         holeSurfaceNodes(nodes, holeCenter, zAxis, holeRadius, axialMin, axialMax, nodeTolerance)) {
        const Base::Vector3d relative = node.position - holeCenter;
        const double localX = relative.Dot(xAxis);
        if (localX < -tolerance) {
            continue;
        }
        const double localY = relative.Dot(yAxis);
        const double localZ = relative.Dot(zAxis);
        const double radialLength = std::hypot(localX, localY);
        if (radialLength <= tolerance) {
            continue;
        }
        const int region = (localZ < 0.0 ? 2 : 0) + (localY < 0.0 ? 1 : 0);
        regions[region].push_back({node, localY, localZ, localX / radialLength, region});
    }

    if (std::any_of(std::begin(regions), std::end(regions), [](const auto& region) {
            return region.empty();
        })) {
        return {};
    }

    // Use one coefficient for each axial/circumferential region and cosine
    // weighting within a region.  This keeps the bearing-pressure pattern
    // nearly symmetric even on an irregular mesh, while the three constraints
    // preserve the exact resultant and zero moments about the face center.
    double constraints[3][4] = {};
    for (int region = 0; region < 4; ++region) {
        for (const Candidate& candidate : regions[region]) {
            constraints[0][region] += candidate.cosine;
            constraints[1][region] += candidate.localZ * candidate.cosine;
            constraints[2][region] += candidate.localY * candidate.cosine;
        }
    }

    // A region coefficient multiplies each node's cosine basis. C2 must
    // account for those actual nodal magnitudes, not just the node count.
    double weights[4];
    for (int region = 0; region < 4; ++region) {
        double squaredBasis = 0.0;
        for (const auto& candidate : regions[region]) {
            squaredBasis += candidate.cosine * candidate.cosine;
        }
        weights[region] = loadCost.getValue() == 1 && squaredBasis > 0.0 ? std::sqrt(squaredBasis)
                                                                         : 1.0;
        for (int row = 0; row < 3; ++row) {
            constraints[row][region] /= weights[region];
        }
    }

    double gram[3][3] = {};
    for (int row = 0; row < 3; ++row) {
        for (int other = 0; other < 3; ++other) {
            for (int region = 0; region < 4; ++region) {
                gram[row][other] += constraints[row][region] * constraints[other][region];
            }
        }
    }

    const double rhs[3] = {sideForce, 0.0, 0.0};
    double multipliers[3] = {};
    if (!solve3x3(gram, rhs, multipliers, tolerance)) {
        return {};
    }

    double values[4] = {};
    for (int region = 0; region < 4; ++region) {
        for (int row = 0; row < 3; ++row) {
            values[region] += constraints[row][region] * multipliers[row];
        }
        values[region] /= weights[region];
    }

    std::vector<NodalForce> nodalForces;
    for (const auto& region : regions) {
        for (const Candidate& candidate : region) {
            const double value = values[candidate.region] * candidate.cosine;
            // tolerance is a length tolerance, not a force threshold.
            if (value == 0.0) {
                continue;
            }
            nodalForces.push_back({candidate.node.id, xAxis * value});
        }
    }
    return nodalForces;
}

std::vector<MbDFEM::CylCylFacePair::NodalForce> MbDFEM::CylCylFacePair::holeAxisNodalForces(
    const std::vector<HoleNode>& nodes,
    const Base::Vector3d& holeCenter,
    const Base::Vector3d& holeAxis,
    const Base::Vector3d& forceXAxis,
    double holeRadius,
    double axialMin,
    double axialMax,
    double forceAxis,
    double tolerance
) const
{
    Base::Vector3d zAxis = holeAxis;
    if (zAxis.Length() <= Base::Vector3d::epsilon()) {
        return {};
    }
    zAxis.Normalize();

    const double nodeTolerance = tolerance < 0.0 ? contactNodeTolerance : tolerance;
    if (tolerance < 0.0) {
        tolerance = std::max({std::abs(holeRadius), std::abs(axialMax - axialMin), 1.0}) * 1.0e-6;
    }
    if (std::abs(forceAxis) <= tolerance) {
        return {};
    }

    Base::Vector3d xAxis = normalizedPerpendicularAxis(zAxis, forceXAxis);
    if (xAxis.Length() <= Base::Vector3d::epsilon()) {
        return {};
    }

    Base::Vector3d yAxis = zAxis.Cross(xAxis);
    if (yAxis.Length() <= Base::Vector3d::epsilon()) {
        return {};
    }
    yAxis.Normalize();
    xAxis = yAxis.Cross(zAxis);
    xAxis.Normalize();

    struct Candidate
    {
        HoleNode node;
        double localX = 0.0;
        double localY = 0.0;
    };

    std::vector<Candidate> quadrants[4];
    for (const HoleNode& node :
         holeSurfaceNodes(nodes, holeCenter, zAxis, holeRadius, axialMin, axialMax, nodeTolerance)) {
        const Base::Vector3d relative = node.position - holeCenter;
        const double localX = relative.Dot(xAxis);
        const double localY = relative.Dot(yAxis);
        int quadrant = 0;
        if (localX >= 0.0 && localY >= 0.0) {
            quadrant = 0;
        }
        else if (localX < 0.0 && localY >= 0.0) {
            quadrant = 1;
        }
        else if (localX < 0.0 && localY < 0.0) {
            quadrant = 2;
        }
        else {
            quadrant = 3;
        }
        quadrants[quadrant].push_back({node, localX, localY});
    }

    if (std::any_of(std::begin(quadrants), std::end(quadrants), [](const auto& quadrant) {
            return quadrant.empty();
        })) {
        return {};
    }

    double constraints[3][4] = {};
    for (int quadrant = 0; quadrant < 4; ++quadrant) {
        constraints[0][quadrant] = static_cast<double>(quadrants[quadrant].size());
        for (const Candidate& candidate : quadrants[quadrant]) {
            constraints[1][quadrant] += candidate.localY;
            constraints[2][quadrant] += candidate.localX;
        }
    }

    double weights[4];
    for (int quadrant = 0; quadrant < 4; ++quadrant) {
        weights[quadrant] = loadCost.getValue() == 1 ? std::sqrt(double(quadrants[quadrant].size()))
                                                     : 1.0;
        for (int row = 0; row < 3; ++row) {
            constraints[row][quadrant] /= weights[quadrant];
        }
    }

    double gram[3][3] = {};
    for (int row = 0; row < 3; ++row) {
        for (int other = 0; other < 3; ++other) {
            for (int column = 0; column < 4; ++column) {
                gram[row][other] += constraints[row][column] * constraints[other][column];
            }
        }
    }

    const double rhs[3] = {forceAxis, 0.0, 0.0};
    double multipliers[3] = {};
    if (!solve3x3(gram, rhs, multipliers, tolerance)) {
        return {};
    }

    double values[4] = {};
    for (int quadrant = 0; quadrant < 4; ++quadrant) {
        for (int row = 0; row < 3; ++row) {
            values[quadrant] += constraints[row][quadrant] * multipliers[row];
        }
        values[quadrant] /= weights[quadrant];
    }

    std::vector<NodalForce> nodalForces;
    for (int quadrant = 0; quadrant < 4; ++quadrant) {
        if (std::abs(values[quadrant]) <= tolerance) {
            continue;
        }
        for (const Candidate& candidate : quadrants[quadrant]) {
            nodalForces.push_back({candidate.node.id, zAxis * values[quadrant]});
        }
    }
    return nodalForces;
}

std::vector<MbDFEM::CylCylFacePair::CLOAD> MbDFEM::CylCylFacePair::holeCLOADs(
    const std::vector<HoleNode>& nodes,
    const Base::Vector3d& holeCenter,
    const Base::Vector3d& holeAxis,
    double holeRadius,
    double axialMin,
    double axialMax,
    const Base::Vector3d& centerForce,
    double tolerance
) const
{
    // Compatibility API: the finalized overload validates the full wrench.
    try {
        auto loads = holeCLOADs(
            nodes,
            holeCenter,
            holeAxis,
            holeRadius,
            axialMin,
            axialMax,
            centerForce,
            Base::Vector3d(),
            tolerance
        );
        loads.transverseForce
            .insert(loads.transverseForce.end(), loads.axialForce.begin(), loads.axialForce.end());
        return loads.transverseForce;
    }
    catch (const std::runtime_error&) {
        return {};
    }
}

MbDFEM::CylCylFacePair::HoleLoadComponents MbDFEM::CylCylFacePair::holeCLOADs(
    const std::vector<HoleNode>& nodes,
    const Base::Vector3d& holeCenter,
    const Base::Vector3d& holeAxis,
    double holeRadius,
    double axialMin,
    double axialMax,
    const Base::Vector3d& centerForce,
    const Base::Vector3d& centerTorque,
    double tolerance
) const
{
    if (holeAxis.Length() <= Base::Vector3d::epsilon() || holeRadius <= 0.0) {
        throw std::runtime_error("Invalid cylindrical hole geometry.");
    }
    Base::Vector3d zAxis = holeAxis;
    zAxis.Normalize();
    const auto surface
        = holeSurfaceNodes(nodes, holeCenter, zAxis, holeRadius, axialMin, axialMax, tolerance);
    const double forceZ = centerForce.Dot(zAxis);
    const Base::Vector3d forceSide = centerForce - zAxis * forceZ;
    const double torqueZ = centerTorque.Dot(zAxis);
    const Base::Vector3d torqueSide = centerTorque - zAxis * torqueZ;
    const Base::Vector3d preferredX = forceSide.Length() > 1.0e-12 ? forceSide
                                                                   : torqueSide.Cross(zAxis);
    const Base::Vector3d xAxis = normalizedPerpendicularAxis(zAxis, preferredX);
    HoleLoadComponents result;
    if (forceSide.Length() > 1.0e-12) {
        appendCLOADs(
            result.transverseForce,
            holeNodalForces(surface, holeCenter, zAxis, holeRadius, axialMin, axialMax, centerForce, tolerance),
            0.0
        );
    }
    if (std::abs(forceZ) > 1.0e-12) {
        appendCLOADs(
            result.axialForce,
            holeAxisNodalForces(surface, holeCenter, zAxis, xAxis, holeRadius, axialMin, axialMax, forceZ, tolerance),
            0.0
        );
    }
    if (torqueSide.Length() > 1.0e-12) {
        Base::Vector3d torqueXAxis = torqueSide.Cross(zAxis);
        torqueXAxis.Normalize();
        result.bendingTorque = torqueCLOADs(
            surface,
            holeCenter,
            torqueXAxis,
            zAxis,
            torqueSide,
            false,
            loadCost.getValue() == 1
        );
    }
    if (std::abs(torqueZ) > 1.0e-12) {
        result.axialTorque = torqueCLOADs(
            surface,
            holeCenter,
            xAxis,
            zAxis,
            zAxis * torqueZ,
            true,
            loadCost.getValue() == 1
        );
    }
    const auto validateForce = [&](std::vector<CLOAD>& records,
                                   const Base::Vector3d& requestedForce,
                                   bool transverse,
                                   const char* component) {
        try {
            checkWrench(surface, holeCenter, records, requestedForce, Base::Vector3d(), component);
            return;
        }
        catch (const std::runtime_error&) {
            if (loadCost.getValue() != 1) {
                throw;
            }
        }
        const double contactTolerance = tolerance < 0.0 ? contactNodeTolerance : tolerance;
        std::vector<NodalForce> bases;
        for (const auto& node : surface) {
            const auto relative = node.position - holeCenter;
            // Transverse bearing forces remain on the loaded half-cylinder.
            if (transverse && relative.Dot(xAxis) <= contactTolerance) {
                continue;
            }
            bases.push_back({node.id, transverse ? xAxis : zAxis});
        }
        records
            = minimumNodalCLOADs(surface, holeCenter, bases, requestedForce, Base::Vector3d(), component);
    };
    validateForce(result.transverseForce, forceSide, true, "transverse force");
    validateForce(result.axialForce, zAxis * forceZ, false, "axial force");
    // Validate the combined wrench while retaining every separate CLOAD record.
    auto all = result.transverseForce;
    all.insert(all.end(), result.axialForce.begin(), result.axialForce.end());
    all.insert(all.end(), result.bendingTorque.begin(), result.bendingTorque.end());
    all.insert(all.end(), result.axialTorque.begin(), result.axialTorque.end());
    checkWrench(surface, holeCenter, all, centerForce, centerTorque, "combined load");
    return result;
}

std::vector<MbDFEM::CylCylFacePair::CLOAD> MbDFEM::CylCylFacePair::holeAxisCLOADs(
    const std::vector<HoleNode>& nodes,
    const Base::Vector3d& holeCenter,
    const Base::Vector3d& holeAxis,
    const Base::Vector3d& forceXAxis,
    double holeRadius,
    double axialMin,
    double axialMax,
    double forceAxis,
    double tolerance
) const
{
    std::vector<CLOAD> cloads;
    appendCLOADs(
        cloads,
        holeAxisNodalForces(
            nodes,
            holeCenter,
            holeAxis,
            forceXAxis,
            holeRadius,
            axialMin,
            axialMax,
            forceAxis,
            tolerance
        ),
        tolerance
    );
    return cloads;
}

bool MbDFEM::CylCylFacePair::solve3x3(
    double matrix[3][3],
    const double rhs[3],
    double solution[3],
    double tolerance
)
{
    // The caller's tolerance is geometric (millimetres) and is not a valid
    // threshold for dimensionless Gaussian-elimination pivots.  Using it here
    // made otherwise valid fine-mesh constraint systems appear singular.
    (void)tolerance;
    constexpr double pivotTolerance = std::numeric_limits<double>::epsilon() * 128.0;
    double rows[3][4] = {};
    for (int row = 0; row < 3; ++row) {
        for (int column = 0; column < 3; ++column) {
            rows[row][column] = matrix[row][column];
        }
        rows[row][3] = rhs[row];
    }

    for (int column = 0; column < 3; ++column) {
        int pivot = column;
        for (int row = column + 1; row < 3; ++row) {
            if (std::abs(rows[row][column]) > std::abs(rows[pivot][column])) {
                pivot = row;
            }
        }

        if (std::abs(rows[pivot][column]) <= pivotTolerance) {
            return false;
        }

        if (pivot != column) {
            for (int index = column; index < 4; ++index) {
                std::swap(rows[column][index], rows[pivot][index]);
            }
        }

        const double pivotValue = rows[column][column];
        for (int index = column; index < 4; ++index) {
            rows[column][index] /= pivotValue;
        }

        for (int row = 0; row < 3; ++row) {
            if (row == column) {
                continue;
            }
            const double factor = rows[row][column];
            if (std::abs(factor) <= pivotTolerance) {
                continue;
            }
            for (int index = column; index < 4; ++index) {
                rows[row][index] -= factor * rows[column][index];
            }
        }
    }

    for (int row = 0; row < 3; ++row) {
        solution[row] = rows[row][3];
    }
    return true;
}
