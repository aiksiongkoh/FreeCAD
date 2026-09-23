// SPDX-License-Identifier: LGPL-2.1-or-later

#include "CylCylFacePair.h"
#include "MbDJoint.h"
#include "MbDPart.h"
#include "MbDMarker.h"
#include "MbDAssembly.h"
#include <App/Document.h>
#include <BRepAdaptor_Surface.hxx>
#include <BRep_Tool.hxx>
#include <TopExp_Explorer.hxx>
#include <TopoDS.hxx>
#include <gp_Cylinder.hxx>
#include <unordered_set>

#include <BRepBuilderAPI_MakeVertex.hxx>
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

namespace
{

Base::Vector3d normalizedPerpendicularAxis(const Base::Vector3d& axis, const Base::Vector3d& preferred)
{
    Base::Vector3d result = preferred - axis * preferred.Dot(axis);
    if (result.Length() <= Base::Vector3d::epsilon()) {
        const Base::Vector3d fallback =
            std::abs(axis.Dot(Base::Vector3d::UnitX)) < 0.9 ? Base::Vector3d::UnitX : Base::Vector3d::UnitY;
        result = fallback - axis * fallback.Dot(axis);
    }
    if (result.Length() <= Base::Vector3d::epsilon()) {
        return Base::Vector3d();
    }
    result.Normalize();
    return result;
}

void appendCLOADs(std::vector<MbDFEM::CylCylFacePair::CLOAD>& cloads,
                  const std::vector<MbDFEM::CylCylFacePair::NodalForce>& nodalForces,
                  double tolerance)
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
    const auto face = TopoDS::Face(part->Shape.getShape().getSubShape(link.getSubValues().front().c_str()));
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
        const double z = (Base::Vector3d(p.X(), p.Y(), p.Z()) - geometry.axisPoint).Dot(geometry.axisDirection);
        geometry.axialMin = std::min(geometry.axialMin, z);
        geometry.axialMax = std::max(geometry.axialMax, z);
    }
    if (!std::isfinite(geometry.axialMin) || !std::isfinite(geometry.axialMax)) {
        throw std::runtime_error("Cylinder has no bounded axial span.");
    }
    gp_Pnt sample;
    gp_Vec du, dv;
    surface.D1((surface.FirstUParameter() + surface.LastUParameter()) * 0.5,
               (surface.FirstVParameter() + surface.LastVParameter()) * 0.5, sample, du, dv);
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

const MbDFEM::MbDPart* markerPart(const MbDFEM::MbDMarker* marker)
{
    if (marker) {
        for (const auto* object : marker->getDocument()->getObjects()) {
            const auto* part = freecad_cast<const MbDFEM::MbDPart*>(object);
            if (part) {
                const auto& markers = part->markers.getValues();
                if (std::find(markers.begin(), markers.end(), marker) != markers.end()) {
                    return part;
                }
            }
        }
    }
    throw std::runtime_error("Joint marker has no owning MbDPart.");
}

double sampleValue(const App::PropertyFloatList& series, int index)
{
    const auto& values = series.getValues();
    return values.empty() ? 0.0 : values[std::clamp(index, 0, static_cast<int>(values.size()) - 1)];
}

Base::Placement sampledPlacement(const MbDFEM::MbDPart& part, int lower, int upper, double ratio)
{
    Base::Placement result = part.globalPlacement();
    if (lower < 0) {
        return result;
    }
    Base::Placement assemblyPlacement;
    for (const auto* object : part.getDocument()->getObjects()) {
        const auto* assembly = freecad_cast<const MbDFEM::MbDAssembly*>(object);
        if (assembly) {
            const auto contains = [&part](const auto& list) {
                const auto& items = list.getValues();
                return std::find(items.begin(), items.end(), &part) != items.end();
            };
            if (contains(assembly->parts) || contains(assembly->fixedparts)) {
                assemblyPlacement = assembly->globalPlacement();
                break;
            }
        }
    }
    const auto sample = [=](const auto& series) {
        return sampleValue(series, lower) * (1.0 - ratio) + sampleValue(series, upper) * ratio;
    };
    if (!part.xs.getValues().empty() && !part.ys.getValues().empty() && !part.zs.getValues().empty()) {
        Base::Vector3d position(sample(part.xs), sample(part.ys), sample(part.zs));
        assemblyPlacement.multVec(position, position);
        result.setPosition(position);
    }
    if (!part.bryxs.getValues().empty() && !part.bryys.getValues().empty() && !part.bryzs.getValues().empty()) {
        const auto rotation = [&part](int index) {
            return Base::Rotation(Base::Vector3d::UnitZ, sampleValue(part.bryzs, index))
                * Base::Rotation(Base::Vector3d::UnitY, sampleValue(part.bryys, index))
                * Base::Rotation(Base::Vector3d::UnitX, sampleValue(part.bryxs, index));
        };
        result.setRotation(assemblyPlacement.getRotation()
                           * Base::Rotation::slerp(rotation(lower), rotation(upper), ratio));
    }
    return result;
}

// Check the wrench without coalescing the records used for debugging/export.
void checkWrench(const std::vector<Pair::HoleNode>& nodes,
                 const Base::Vector3d& center,
                 const std::vector<Pair::CLOAD>& loads,
                 const Base::Vector3d& force,
                 const Base::Vector3d& torque,
                 const char* component)
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
    const double forceTolerance = 1.0e-9 * std::max(1.0, force.Length());
    const double momentTolerance = 1.0e-9 * std::max({1.0, torque.Length(), force.Length() * length});
    if (!std::isfinite(resultant.Length()) || !std::isfinite(moment.Length())
        || (resultant - force).Length() > forceTolerance
        || (moment - torque).Length() > momentTolerance) {
        throw std::runtime_error(std::string("Hole ") + component
                                 + " cannot satisfy force/moment equilibrium; refine the face mesh.");
    }
}

// Each column is one region's nodal force basis. Solve all six equilibrium
// rows (identically zero rows are harmless) for minimum coefficient norm.
std::vector<Pair::CLOAD> torqueCLOADs(const std::vector<Pair::HoleNode>& nodes,
                                     const Base::Vector3d& center,
                                     const Base::Vector3d& xAxis,
                                     const Base::Vector3d& zAxis,
                                     const Base::Vector3d& torque,
                                     bool axial)
{
    const Base::Vector3d yAxis = zAxis.Cross(xAxis);
    const int count = axial ? 8 : 4;
    Eigen::MatrixXd matrix = Eigen::MatrixXd::Zero(6, count);
    struct Basis { int node; int region; Base::Vector3d force; };
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
    }
    length = length > 0.0 ? length : 1.0;
    matrix.bottomRows(3) /= length;
    Eigen::VectorXd rhs = Eigen::VectorXd::Zero(6);
    for (int row = 0; row < 3; ++row) {
        rhs[row + 3] = torque[row] / length;
    }
    const Eigen::VectorXd coefficients = matrix.jacobiSvd(Eigen::ComputeThinU | Eigen::ComputeThinV).solve(rhs);
    std::vector<Pair::NodalForce> forces;
    for (const auto& basis : bases) {
        forces.push_back({basis.node, basis.force * coefficients[basis.region]});
    }
    std::vector<Pair::CLOAD> result;
    appendCLOADs(result, forces, 0.0);
    checkWrench(nodes, center, result, Base::Vector3d(), torque, axial ? "axial torque" : "bending torque");
    return result;
}

}  // namespace

MbDFEM::CylCylFacePair::JointHoleLoad MbDFEM::CylCylFacePair::jointHoleLoad(
    const MbDJoint& joint, const MbDPart& part, const std::vector<HoleNode>& nodes,
    const std::vector<CylCylFacePair*>& participatingPairs, int lower, int upper, double ratio) const
{
    const auto* markerI = freecad_cast<MbDMarker*>(joint.markerI.getValue());
    const auto* markerJ = freecad_cast<MbDMarker*>(joint.markerJ.getValue());
    const auto* partI = markerPart(markerI);
    const auto* partJ = markerPart(markerJ);
    if (partI == partJ || (&part != partI && &part != partJ)) {
        throw std::runtime_error("Hole part does not identify one side of the joint.");
    }
    std::unordered_set<const CylCylFacePair*> participants;
    for (const auto* pair : participatingPairs) {
        if (pair && ((pair->faceI.getValue() == partI && pair->faceJ.getValue() == partJ)
                     || (pair->faceI.getValue() == partJ && pair->faceJ.getValue() == partI))) {
            participants.insert(pair);
        }
    }
    if (participants.find(this) == participants.end()) {
        throw std::runtime_error("Hole FacePair is not a participant of this joint.");
    }
    const auto referenceI = cylinderReference(faceI);
    const auto referenceJ = cylinderReference(faceJ);
    const auto roles = classifyFaces(referenceI.geometry, referenceJ.geometry);
    const bool sideI = faceI.getValue() == &part;
    if (!(sideI ? roles.faceIIsHole() : roles.faceJIsHole())) {
        throw std::runtime_error("Requested FacePair side is not a cylindrical hole.");
    }
    const auto& reference = sideI ? referenceI : referenceJ;
    const auto& geometry = reference.geometry;
    if (upper < 0) {
        upper = lower;
    }
    if (!std::isfinite(ratio) || ratio < 0.0 || ratio > 1.0) {
        throw std::runtime_error("Joint sample interpolation ratio must be between zero and one.");
    }
    const auto sample = [=](const auto& series) {
        return sampleValue(series, lower) * (1.0 - ratio) + sampleValue(series, upper) * ratio;
    };
    const auto placement = sampledPlacement(part, lower, upper, ratio);
    const auto sourcePlacement = sampledPlacement(*partI, lower, upper, ratio);
    const auto inverse = placement.inverse();
    Base::Vector3d markerOrigin;
    sourcePlacement.multVec(markerI->Placement.getValue().getPosition(), markerOrigin);
    inverse.multVec(markerOrigin, markerOrigin);
    const double share = (&part == partI ? 1.0 : -1.0) / static_cast<double>(participants.size());
    JointHoleLoad result;
    result.origin = geometry.axisPoint;
    result.zAxis = geometry.axisDirection;
    inverse.getRotation().multVec(Base::Vector3d(sample(joint.fxs), sample(joint.fys), sample(joint.fzs)) * share,
                                  result.force);
    inverse.getRotation().multVec(Base::Vector3d(sample(joint.txs), sample(joint.tys), sample(joint.tzs)) * share,
                                  result.torque);
    result.torque += (markerOrigin - result.origin).Cross(result.force);
    const auto forceSide = result.force - result.zAxis * result.force.Dot(result.zAxis);
    result.xAxis = normalizedPerpendicularAxis(result.zAxis,
        forceSide.Length() > 1.0e-12 ? forceSide : result.torque.Cross(result.zAxis));
    result.yAxis = result.zAxis.Cross(result.xAxis);
    for (const auto& node : holeSurfaceNodes(nodes, result.origin, result.zAxis, reference.radius,
                                            geometry.axialMin, geometry.axialMax)) {
        const auto relative = node.position - result.origin;
        const double x = relative.Dot(result.xAxis), y = relative.Dot(result.yAxis);
        const int quadrant = x >= 0.0 ? (y >= 0.0 ? 0 : 3) : (y >= 0.0 ? 1 : 2);
        result.octants[quadrant + (relative.Dot(result.zAxis) >= 0.0 ? 0 : 4)].push_back(node.id);
    }
    result.components = holeCLOADs(nodes, result.origin, result.zAxis, reference.radius,
                                   geometry.axialMin, geometry.axialMax, result.force, result.torque);
    return result;
}

MbDFEM::CylCylFacePair::CylCylFacePair(App::DocumentObject* objectI,
                                       std::string subNameI,
                                       App::DocumentObject* objectJ,
                                       std::string subNameJ)
    : FacePair(objectI, std::move(subNameI), objectJ, std::move(subNameJ))
{}

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

MbDFEM::CylCylFacePair::CylindricalFaceRole
MbDFEM::CylCylFacePair::cylindricalFaceRole(const CylindricalFaceGeometry& geometry,
                                            double tolerance)
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

MbDFEM::CylCylFacePair::FaceRoles
MbDFEM::CylCylFacePair::classifyFaces(const CylindricalFaceGeometry& faceIGeometry,
                                      const CylindricalFaceGeometry& faceJGeometry,
                                      double tolerance)
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

std::vector<MbDFEM::CylCylFacePair::HoleNode>
MbDFEM::CylCylFacePair::holeSurfaceNodes(const std::vector<HoleNode>& nodes,
                                         const Base::Vector3d& holeCenter,
                                         const Base::Vector3d& holeAxis,
                                         double holeRadius,
                                         double axialMin,
                                         double axialMax,
                                         double tolerance) const
{
    Base::Vector3d axis = holeAxis;
    if (axis.Length() <= Base::Vector3d::epsilon() || holeRadius <= 0.0) {
        return {};
    }
    axis.Normalize();

    if (axialMin > axialMax) {
        std::swap(axialMin, axialMax);
    }

    const double axialSpan = std::abs(axialMax - axialMin);
    if (tolerance < 0.0) {
        tolerance = std::max({std::abs(holeRadius), axialSpan, 1.0}) * 1.0e-6;
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

void MbDFEM::CylCylFacePair::updatePinCoverage(const CylindricalFaceGeometry& faceIGeometry,
                                               const CylindricalFaceGeometry& faceJGeometry,
                                               double tolerance)
{
    pinCoverage = {};
    pinCoverageWarning.clear();

    const FaceRoles roles = classifyFaces(faceIGeometry, faceJGeometry, tolerance);
    if (!roles.hasHoleAndPin()) {
        pinCoverageWarning = "Pin coverage cannot be checked because the cylindrical faces are not a clear hole-pin pair.";
        return;
    }

    const CylindricalFaceGeometry& holeGeometry = roles.faceIIsHole() ? faceIGeometry : faceJGeometry;
    const CylindricalFaceGeometry& pinGeometry = roles.faceIIsHole() ? faceJGeometry : faceIGeometry;

    Base::Vector3d zAxis = holeGeometry.axisDirection;
    if (zAxis.Length() <= Base::Vector3d::epsilon()) {
        pinCoverageWarning = "Pin coverage cannot be checked because the hole force frame Z axis is invalid.";
        return;
    }
    zAxis.Normalize();

    Base::Vector3d pinAxis = pinGeometry.axisDirection;
    if (pinAxis.Length() <= Base::Vector3d::epsilon()) {
        pinCoverageWarning = "Pin coverage cannot be checked because the pin cylinder axis is invalid.";
        return;
    }
    pinAxis.Normalize();

    if (tolerance < 0.0) {
        tolerance = std::max({std::abs(holeGeometry.axialMax - holeGeometry.axialMin),
                              std::abs(pinGeometry.axialMax - pinGeometry.axialMin),
                              1.0})
            * 1.0e-6;
    }

    const double holeZ0 =
        (holeGeometry.axisPoint + zAxis * holeGeometry.axialMin - holeGeometry.axisPoint).Dot(zAxis);
    const double holeZ1 =
        (holeGeometry.axisPoint + zAxis * holeGeometry.axialMax - holeGeometry.axisPoint).Dot(zAxis);
    const double pinZ0 =
        (pinGeometry.axisPoint + pinAxis * pinGeometry.axialMin - holeGeometry.axisPoint).Dot(zAxis);
    const double pinZ1 =
        (pinGeometry.axisPoint + pinAxis * pinGeometry.axialMax - holeGeometry.axisPoint).Dot(zAxis);

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
    message << "Pin cylindrical face does not fully cover the hole contact span in the hole force frame. "
            << "Hole z range: [" << pinCoverage.holeZMin << ", " << pinCoverage.holeZMax
            << "]. Pin z coverage: [" << pinCoverage.pinZMin << ", " << pinCoverage.pinZMax
            << "]. CLOADs will be applied only to the overlapping pin region.";
    pinCoverageWarning = message.str();
}

std::vector<MbDFEM::CylCylFacePair::NodalForce>
MbDFEM::CylCylFacePair::holeNodalForces(const std::vector<HoleNode>& nodes,
                                        const Base::Vector3d& holeCenter,
                                        const Base::Vector3d& holeAxis,
                                        double holeRadius,
                                        double axialMin,
                                        double axialMax,
                                        const Base::Vector3d& centerForce,
                                        double tolerance) const
{
    Base::Vector3d zAxis = holeAxis;
    if (zAxis.Length() <= Base::Vector3d::epsilon()) {
        return {};
    }
    zAxis.Normalize();

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
         holeSurfaceNodes(nodes, holeCenter, zAxis, holeRadius, axialMin, axialMax, tolerance)) {
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

std::vector<MbDFEM::CylCylFacePair::NodalForce>
MbDFEM::CylCylFacePair::holeAxisNodalForces(const std::vector<HoleNode>& nodes,
                                            const Base::Vector3d& holeCenter,
                                            const Base::Vector3d& holeAxis,
                                            const Base::Vector3d& forceXAxis,
                                            double holeRadius,
                                            double axialMin,
                                            double axialMax,
                                            double forceAxis,
                                            double tolerance) const
{
    Base::Vector3d zAxis = holeAxis;
    if (zAxis.Length() <= Base::Vector3d::epsilon()) {
        return {};
    }
    zAxis.Normalize();

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
         holeSurfaceNodes(nodes, holeCenter, zAxis, holeRadius, axialMin, axialMax, tolerance)) {
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

std::vector<MbDFEM::CylCylFacePair::CLOAD>
MbDFEM::CylCylFacePair::holeCLOADs(const std::vector<HoleNode>& nodes,
                                   const Base::Vector3d& holeCenter,
                                   const Base::Vector3d& holeAxis,
                                   double holeRadius,
                                   double axialMin,
                                   double axialMax,
                                   const Base::Vector3d& centerForce,
                                   double tolerance) const
{
    // Compatibility API: the finalized overload validates the full wrench.
    try {
        auto loads = holeCLOADs(nodes, holeCenter, holeAxis, holeRadius, axialMin,
                                axialMax, centerForce, Base::Vector3d(), tolerance);
        loads.transverseForce.insert(loads.transverseForce.end(),
                                     loads.axialForce.begin(), loads.axialForce.end());
        return loads.transverseForce;
    }
    catch (const std::runtime_error&) {
        return {};
    }
}

MbDFEM::CylCylFacePair::HoleLoadComponents
MbDFEM::CylCylFacePair::holeCLOADs(const std::vector<HoleNode>& nodes,
                                 const Base::Vector3d& holeCenter,
                                 const Base::Vector3d& holeAxis,
                                 double holeRadius,
                                 double axialMin,
                                 double axialMax,
                                 const Base::Vector3d& centerForce,
                                 const Base::Vector3d& centerTorque,
                                 double tolerance) const
{
    if (holeAxis.Length() <= Base::Vector3d::epsilon() || holeRadius <= 0.0) {
        throw std::runtime_error("Invalid cylindrical hole geometry.");
    }
    Base::Vector3d zAxis = holeAxis;
    zAxis.Normalize();
    const auto surface = holeSurfaceNodes(nodes, holeCenter, zAxis, holeRadius,
                                          axialMin, axialMax, tolerance);
    const double forceZ = centerForce.Dot(zAxis);
    const Base::Vector3d forceSide = centerForce - zAxis * forceZ;
    const double torqueZ = centerTorque.Dot(zAxis);
    const Base::Vector3d torqueSide = centerTorque - zAxis * torqueZ;
    const Base::Vector3d preferredX = forceSide.Length() > 1.0e-12
        ? forceSide : torqueSide.Cross(zAxis);
    const Base::Vector3d xAxis = normalizedPerpendicularAxis(zAxis, preferredX);
    HoleLoadComponents result;
    if (forceSide.Length() > 1.0e-12) {
        appendCLOADs(result.transverseForce,
                     holeNodalForces(surface, holeCenter, zAxis, holeRadius,
                                     axialMin, axialMax, centerForce, tolerance), 0.0);
    }
    if (std::abs(forceZ) > 1.0e-12) {
        appendCLOADs(result.axialForce,
                     holeAxisNodalForces(surface, holeCenter, zAxis, xAxis, holeRadius,
                                         axialMin, axialMax, forceZ, tolerance), 0.0);
    }
    if (torqueSide.Length() > 1.0e-12) {
        Base::Vector3d torqueXAxis = torqueSide.Cross(zAxis);
        torqueXAxis.Normalize();
        result.bendingTorque = torqueCLOADs(surface, holeCenter, torqueXAxis, zAxis, torqueSide, false);
    }
    if (std::abs(torqueZ) > 1.0e-12) {
        result.axialTorque = torqueCLOADs(surface, holeCenter, xAxis, zAxis, zAxis * torqueZ, true);
    }
    checkWrench(surface, holeCenter, result.transverseForce, forceSide, Base::Vector3d(), "transverse force");
    checkWrench(surface, holeCenter, result.axialForce, zAxis * forceZ, Base::Vector3d(), "axial force");
    // Validate the combined wrench while retaining every separate CLOAD record.
    auto all = result.transverseForce;
    all.insert(all.end(), result.axialForce.begin(), result.axialForce.end());
    all.insert(all.end(), result.bendingTorque.begin(), result.bendingTorque.end());
    all.insert(all.end(), result.axialTorque.begin(), result.axialTorque.end());
    checkWrench(surface, holeCenter, all, centerForce, centerTorque, "combined load");
    return result;
}

std::vector<MbDFEM::CylCylFacePair::CLOAD>
MbDFEM::CylCylFacePair::holeAxisCLOADs(const std::vector<HoleNode>& nodes,
                                       const Base::Vector3d& holeCenter,
                                       const Base::Vector3d& holeAxis,
                                       const Base::Vector3d& forceXAxis,
                                       double holeRadius,
                                       double axialMin,
                                       double axialMax,
                                       double forceAxis,
                                       double tolerance) const
{
    if (tolerance < 0.0) {
        tolerance = std::max({std::abs(holeRadius), std::abs(axialMax - axialMin), 1.0}) * 1.0e-6;
    }

    std::vector<CLOAD> cloads;
    appendCLOADs(cloads,
                 holeAxisNodalForces(nodes,
                                      holeCenter,
                                      holeAxis,
                                      forceXAxis,
                                      holeRadius,
                                      axialMin,
                                      axialMax,
                                      forceAxis,
                                      tolerance),
                 tolerance);
    return cloads;
}

std::vector<MbDFEM::CylCylFacePair::NodalForce>
MbDFEM::CylCylFacePair::pinNodalForces(const std::vector<HoleNode>& pinNodes,
                                       const Base::Vector3d& pinCenter,
                                       const Base::Vector3d& pinAxis,
                                       double pinRadius,
                                       double pinAxialMin,
                                       double pinAxialMax,
                                       const TopoDS_Face& holeContactFace,
                                       const Base::Vector3d& pinForceFrameOrigin,
                                       const Base::Vector3d& pinForceFrameXAxis,
                                       const Base::Vector3d& pinForceFrameYAxis,
                                       const Base::Vector3d& pinForceFrameZAxis,
                                       const Base::Vector3d& forceOnPin,
                                       double tolerance) const
{
    Base::Vector3d xAxis = pinForceFrameXAxis;
    Base::Vector3d yAxis = pinForceFrameYAxis;
    Base::Vector3d zAxis = pinForceFrameZAxis;
    if (xAxis.Length() <= Base::Vector3d::epsilon() || yAxis.Length() <= Base::Vector3d::epsilon()
        || zAxis.Length() <= Base::Vector3d::epsilon()) {
        return {};
    }
    xAxis.Normalize();
    yAxis.Normalize();
    zAxis.Normalize();

    if (tolerance < 0.0) {
        tolerance = std::max({std::abs(pinRadius), std::abs(pinAxialMax - pinAxialMin), 1.0}) * 1.0e-6;
    }

    const double sideForce = forceOnPin.Dot(xAxis);
    if (std::abs(sideForce) <= tolerance) {
        return {};
    }

    struct Candidate
    {
        HoleNode node;
        double localY = 0.0;
        double localZ = 0.0;
    };

    std::vector<Candidate> candidates;
    for (const HoleNode& node :
         holeSurfaceNodes(pinNodes, pinCenter, pinAxis, pinRadius, pinAxialMin, pinAxialMax, tolerance)) {
        if (!pointTouchesFace(node.position, holeContactFace, tolerance)) {
            continue;
        }
        const Base::Vector3d relative = node.position - pinForceFrameOrigin;
        const double localZ = relative.Dot(zAxis);
        if (relative.Dot(xAxis) < -tolerance) {
            continue;
        }
        candidates.push_back({node, relative.Dot(yAxis), localZ});
    }

    if (candidates.empty()) {
        return {};
    }

    double gram[3][3] = {};
    for (const Candidate& candidate : candidates) {
        const double column[3] = {1.0, candidate.localZ, candidate.localY};
        for (int row = 0; row < 3; ++row) {
            for (int other = 0; other < 3; ++other) {
                gram[row][other] += column[row] * column[other];
            }
        }
    }

    const double rhs[3] = {sideForce, 0.0, 0.0};
    double multipliers[3] = {};
    if (!solve3x3(gram, rhs, multipliers, tolerance)) {
        return {};
    }

    std::vector<NodalForce> nodalForces;
    nodalForces.reserve(candidates.size());
    for (const Candidate& candidate : candidates) {
        const double value =
            multipliers[0] + candidate.localZ * multipliers[1] + candidate.localY * multipliers[2];
        if (std::abs(value) <= tolerance) {
            continue;
        }
        nodalForces.push_back({candidate.node.id, xAxis * value});
    }
    return nodalForces;
}

std::vector<MbDFEM::CylCylFacePair::NodalForce>
MbDFEM::CylCylFacePair::pinAxisNodalForces(const std::vector<HoleNode>& pinNodes,
                                           const Base::Vector3d& pinCenter,
                                           const Base::Vector3d& pinAxis,
                                           double pinRadius,
                                           double pinAxialMin,
                                           double pinAxialMax,
                                           const TopoDS_Face& holeContactFace,
                                           const Base::Vector3d& pinForceFrameOrigin,
                                           const Base::Vector3d& pinForceFrameXAxis,
                                           const Base::Vector3d& pinForceFrameYAxis,
                                           const Base::Vector3d& pinForceFrameZAxis,
                                           double forceOnPinAxis,
                                           double tolerance) const
{
    Base::Vector3d xAxis = pinForceFrameXAxis;
    Base::Vector3d yAxis = pinForceFrameYAxis;
    Base::Vector3d zAxis = pinForceFrameZAxis;
    if (xAxis.Length() <= Base::Vector3d::epsilon() || yAxis.Length() <= Base::Vector3d::epsilon()
        || zAxis.Length() <= Base::Vector3d::epsilon()) {
        return {};
    }
    xAxis.Normalize();
    yAxis.Normalize();
    zAxis.Normalize();

    if (tolerance < 0.0) {
        tolerance = std::max({std::abs(pinRadius), std::abs(pinAxialMax - pinAxialMin), 1.0}) * 1.0e-6;
    }
    if (std::abs(forceOnPinAxis) <= tolerance) {
        return {};
    }

    struct Candidate
    {
        HoleNode node;
        double localX = 0.0;
        double localY = 0.0;
    };

    std::vector<Candidate> quadrants[4];
    for (const HoleNode& node :
         holeSurfaceNodes(pinNodes, pinCenter, pinAxis, pinRadius, pinAxialMin, pinAxialMax, tolerance)) {
        if (!pointTouchesFace(node.position, holeContactFace, tolerance)) {
            continue;
        }
        const Base::Vector3d relative = node.position - pinForceFrameOrigin;
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

    double gram[3][3] = {};
    for (int row = 0; row < 3; ++row) {
        for (int other = 0; other < 3; ++other) {
            for (int column = 0; column < 4; ++column) {
                gram[row][other] += constraints[row][column] * constraints[other][column];
            }
        }
    }

    const double rhs[3] = {forceOnPinAxis, 0.0, 0.0};
    double multipliers[3] = {};
    if (!solve3x3(gram, rhs, multipliers, tolerance)) {
        return {};
    }

    double values[4] = {};
    for (int quadrant = 0; quadrant < 4; ++quadrant) {
        for (int row = 0; row < 3; ++row) {
            values[quadrant] += constraints[row][quadrant] * multipliers[row];
        }
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

std::vector<MbDFEM::CylCylFacePair::CLOAD>
MbDFEM::CylCylFacePair::pinCLOADs(const std::vector<HoleNode>& pinNodes,
                                  const Base::Vector3d& pinCenter,
                                  const Base::Vector3d& pinAxis,
                                  double pinRadius,
                                  double pinAxialMin,
                                  double pinAxialMax,
                                  const TopoDS_Face& holeContactFace,
                                  const Base::Vector3d& pinForceFrameOrigin,
                                  const Base::Vector3d& pinForceFrameXAxis,
                                  const Base::Vector3d& pinForceFrameYAxis,
                                  const Base::Vector3d& pinForceFrameZAxis,
                                  const Base::Vector3d& forceOnPin,
                                  double tolerance) const
{
    Base::Vector3d zAxis = pinForceFrameZAxis;
    if (zAxis.Length() <= Base::Vector3d::epsilon()) {
        return {};
    }
    zAxis.Normalize();

    if (tolerance < 0.0) {
        tolerance = std::max({std::abs(pinRadius), std::abs(pinAxialMax - pinAxialMin), 1.0}) * 1.0e-6;
    }

    std::vector<CLOAD> cloads;
    appendCLOADs(cloads,
                 pinNodalForces(pinNodes,
                                 pinCenter,
                                 pinAxis,
                                 pinRadius,
                                 pinAxialMin,
                                 pinAxialMax,
                                 holeContactFace,
                                 pinForceFrameOrigin,
                                 pinForceFrameXAxis,
                                 pinForceFrameYAxis,
                                 zAxis,
                                 forceOnPin,
                                 tolerance),
                 tolerance);
    appendCLOADs(cloads,
                 pinAxisNodalForces(pinNodes,
                                     pinCenter,
                                     pinAxis,
                                     pinRadius,
                                     pinAxialMin,
                                     pinAxialMax,
                                     holeContactFace,
                                     pinForceFrameOrigin,
                                     pinForceFrameXAxis,
                                     pinForceFrameYAxis,
                                     zAxis,
                                     forceOnPin.Dot(zAxis),
                                     tolerance),
                 tolerance);
    return cloads;
}

std::vector<MbDFEM::CylCylFacePair::CLOAD>
MbDFEM::CylCylFacePair::pinAxisCLOADs(const std::vector<HoleNode>& pinNodes,
                                      const Base::Vector3d& pinCenter,
                                      const Base::Vector3d& pinAxis,
                                      double pinRadius,
                                      double pinAxialMin,
                                      double pinAxialMax,
                                      const TopoDS_Face& holeContactFace,
                                      const Base::Vector3d& pinForceFrameOrigin,
                                      const Base::Vector3d& pinForceFrameXAxis,
                                      const Base::Vector3d& pinForceFrameYAxis,
                                      const Base::Vector3d& pinForceFrameZAxis,
                                      double forceOnPinAxis,
                                      double tolerance) const
{
    if (tolerance < 0.0) {
        tolerance = std::max({std::abs(pinRadius), std::abs(pinAxialMax - pinAxialMin), 1.0}) * 1.0e-6;
    }

    std::vector<CLOAD> cloads;
    appendCLOADs(cloads,
                 pinAxisNodalForces(pinNodes,
                                     pinCenter,
                                     pinAxis,
                                     pinRadius,
                                     pinAxialMin,
                                     pinAxialMax,
                                     holeContactFace,
                                     pinForceFrameOrigin,
                                     pinForceFrameXAxis,
                                     pinForceFrameYAxis,
                                     pinForceFrameZAxis,
                                     forceOnPinAxis,
                                     tolerance),
                 tolerance);
    return cloads;
}

bool MbDFEM::CylCylFacePair::solve3x3(double matrix[3][3],
                                      const double rhs[3],
                                      double solution[3],
                                      double tolerance)
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
