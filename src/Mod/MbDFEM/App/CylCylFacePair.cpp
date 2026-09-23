// SPDX-License-Identifier: LGPL-2.1-or-later

#include "CylCylFacePair.h"

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

}  // namespace

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
    if (tolerance < 0.0) {
        tolerance = std::max({std::abs(holeRadius), std::abs(axialMax - axialMin), 1.0}) * 1.0e-6;
    }

    std::vector<CLOAD> cloads;
    appendCLOADs(cloads,
                 holeNodalForces(nodes, holeCenter, holeAxis, holeRadius, axialMin, axialMax, centerForce, tolerance),
                 tolerance);

    Base::Vector3d zAxis = holeAxis;
    if (zAxis.Length() <= Base::Vector3d::epsilon()) {
        return cloads;
    }
    zAxis.Normalize();
    const double forceAxis = centerForce.Dot(zAxis);
    const Base::Vector3d forceXAxis = centerForce - zAxis * forceAxis;
    appendCLOADs(cloads,
                 holeAxisNodalForces(nodes,
                                      holeCenter,
                                      zAxis,
                                      forceXAxis,
                                      holeRadius,
                                      axialMin,
                                      axialMax,
                                      forceAxis,
                                      tolerance),
                 tolerance);
    return cloads;
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
