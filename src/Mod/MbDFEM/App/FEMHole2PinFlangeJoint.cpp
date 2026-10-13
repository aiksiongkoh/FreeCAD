// SPDX-License-Identifier: LGPL-2.1-or-later

#include "FEMHole2PinFlangeJoint.h"

#include "AnnuAnnuFacePair.h"
#include "CylCylFacePair.h"
#include "JointLoadUtils.h"
#include "MbDJoint.h"

#include <App/Document.h>
#include <Base/Matrix.h>
#include <BRepAdaptor_Surface.hxx>
#include <TopoDS.hxx>
#include <gp_Cylinder.hxx>
#include <gp_Pln.hxx>

#include <algorithm>
#include <cmath>
#include <stdexcept>
#include <unordered_set>

PROPERTY_SOURCE(MbDFEM::FEMHole2PinFlangeJoint, MbDFEM::FEMJoint)

App::DocumentObjectExecReturn* MbDFEM::FEMHole2PinFlangeJoint::execute()
{
    unsigned cylindricalCount = 0;
    unsigned annularCount = 0;
    for (auto* pair : facePairs.getValues()) {
        if (pair && pair->isDerivedFrom(CylCylFacePair::getClassTypeId())) {
            ++cylindricalCount;
        }
        else if (pair && pair->isDerivedFrom(AnnuAnnuFacePair::getClassTypeId())) {
            ++annularCount;
        }
        else {
            return new App::DocumentObjectExecReturn(
                "FEMHole2PinFlangeJoint facePairs must contain only CylCylFacePair and "
                "AnnuAnnuFacePair objects.",
                this
            );
        }
    }

    if (cylindricalCount != 2 || annularCount == 0) {
        return new App::DocumentObjectExecReturn(
            "FEMHole2PinFlangeJoint requires exactly two CylCylFacePair objects and at least "
            "one AnnuAnnuFacePair in facePairs.",
            this
        );
    }

    return FEMJoint::execute();
}

namespace
{
Base::Placement loadFrame(
    const Base::Vector3d& origin,
    const Base::Vector3d& zAxis,
    const Base::Vector3d& force
)
{
    auto xAxis = force - zAxis * force.Dot(zAxis);
    if (xAxis.Length() <= 1.0e-12) {
        const auto fallback = std::abs(zAxis.x) < 0.9 ? Base::Vector3d::UnitX : Base::Vector3d::UnitY;
        xAxis = fallback - zAxis * fallback.Dot(zAxis);
    }
    xAxis.Normalize();
    const auto yAxis = zAxis.Cross(xAxis);
    Base::Matrix4D matrix;
    for (int row = 0; row < 3; ++row) {
        matrix[row][0] = xAxis[row];
        matrix[row][1] = yAxis[row];
        matrix[row][2] = zAxis[row];
    }
    return Base::Placement(origin, Base::Rotation(matrix));
}

const App::PropertyLinkSub& pinFace(const MbDFEM::CylCylFacePair& pair)
{
    return pair.coordsOnFace == MbDFEM::FacePair::IJUkn::I ? pair.faceJ : pair.faceI;
}

TopoDS_Face referencedFace(const App::PropertyLinkSub& link)
{
    const auto* part = freecad_cast<MbDFEM::MbDPart*>(link.getValue());
    if (!part || link.getSubValues().empty()) {
        throw std::runtime_error("Flange joint requires MbDPart face references.");
    }
    return TopoDS::Face(part->Shape.getShape().getSubShape(link.getSubValues().front().c_str()));
}

void setOriginLoad(
    MbDFEM::FacePair& pair,
    const Base::Vector3d& origin,
    const Base::Vector3d& axis,
    const Base::Vector3d& force,
    const Base::Vector3d& torque
)
{
    pair.forceOnFaceIatOrigin = force;
    pair.torqueOnFaceIatOrigin = torque;
    pair.forceCoord = loadFrame(origin, axis, force);
    pair.torqueCoord = pair.forceCoord;
}
}  // namespace

bool MbDFEM::FEMHole2PinFlangeJoint::updateParticipatingPairs(
    const MbDJoint& joint,
    const std::vector<FacePair*>& pairs,
    int lower,
    int upper,
    double ratio
)
{
    const std::unordered_set<App::DocumentObject*> participants(pairs.begin(), pairs.end());
    for (auto* object : joint.getDocument()->getObjects()) {
        auto* femJoint = freecad_cast<FEMHole2PinFlangeJoint*>(object);
        if (!femJoint || femJoint->mbdItem.getValue() != &joint) {
            continue;
        }
        const auto& owned = femJoint->facePairs.getValues();
        const std::unordered_set<App::DocumentObject*> ownedPairs(owned.begin(), owned.end());
        if (participants == ownedPairs) {
            femJoint->distributeJointWrench(joint, lower, upper, ratio);
            return true;
        }
        if (std::any_of(pairs.begin(), pairs.end(), [&ownedPairs](const auto* pair) {
                return ownedPairs.count(const_cast<FacePair*>(pair));
            })) {
            throw std::runtime_error("Flange joint loading requires all of its FacePairs.");
        }
    }
    return false;
}

void MbDFEM::FEMHole2PinFlangeJoint::distributeJointWrench(
    const MbDJoint& joint,
    int lower,
    int upper,
    double ratio
)
{
    using namespace JointLoadUtils;
    if (mbdItem.getValue() != &joint) {
        throw std::runtime_error("Flange joint does not reference the supplied MbDJoint.");
    }
    if (!std::isfinite(ratio) || ratio < 0.0 || ratio > 1.0) {
        throw std::runtime_error("Joint sample interpolation ratio must be between zero and one.");
    }
    if (upper < 0) {
        upper = lower;
    }
    std::vector<CylCylFacePair*> cylinders;
    std::vector<AnnuAnnuFacePair*> annuli;
    std::unordered_set<FacePair*> unique;
    for (auto* object : facePairs.getValues()) {
        auto* pair = freecad_cast<FacePair*>(object);
        if (!pair || !unique.insert(pair).second) {
            throw std::runtime_error("Flange joint requires distinct FacePairs.");
        }
        if (auto* cylinder = freecad_cast<CylCylFacePair*>(pair)) {
            cylinders.push_back(cylinder);
        }
        else if (auto* annulus = freecad_cast<AnnuAnnuFacePair*>(pair)) {
            annuli.push_back(annulus);
        }
        else {
            throw std::runtime_error("Flange joint supports only cylindrical and annular FacePairs.");
        }
    }
    if (cylinders.size() != 2 || annuli.empty()) {
        throw std::runtime_error(
            "Flange joint requires two cylindrical pairs and at least one annular pair."
        );
    }
    // Resolve the hole/pin roles and sampled bearing origins without discretizing loads.
    for (auto* pair : cylinders) {
        pair->updateJointState(joint, lower, upper, ratio);
    }
    const auto& pin1 = pinFace(*cylinders[0]);
    const auto& pin2 = pinFace(*cylinders[1]);
    if (pin1.getValue() != pin2.getValue() || pin1.getSubValues() != pin2.getSubValues()) {
        throw std::runtime_error("Flange joint cylindrical pairs must share the same pin face.");
    }
    const auto* pin = freecad_cast<MbDPart*>(pin1.getValue());
    const auto cylinder = BRepAdaptor_Surface(referencedFace(pin1)).Cylinder();
    const auto direction = cylinder.Axis().Direction();
    auto axis = sampledPlacement(*pin, lower, upper, ratio)
                    .getRotation()
                    .multVec(Base::Vector3d(direction.X(), direction.Y(), direction.Z()));
    axis.Normalize();
    const auto origin1 = cylinders[0]->forceCoord.getPosition();
    const auto origin2 = cylinders[1]->forceCoord.getPosition();
    const auto separation = origin2 - origin1;
    const double span = separation.Dot(axis);
    const double tolerance = std::max(separation.Length(), 1.0) * 1.0e-7;
    if (std::abs(span) <= tolerance || (separation - axis * span).Length() > tolerance) {
        throw std::runtime_error("Flange joint requires separated coaxial bearing origins.");
    }
    for (const auto* pair : cylinders) {
        if (pair->forceCoord.getRotation().multVec(Base::Vector3d::UnitZ).Cross(axis).Length()
            > 1.0e-7) {
            throw std::runtime_error("Flange joint bearing axes must align with the common pin.");
        }
    }
    const auto* markerI = freecad_cast<MbDMarker*>(joint.markerI.getValue());
    const auto* partI = markerPart(markerI);
    const auto marker = sampledPlacement(*partI, lower, upper, ratio) * markerI->Placement.getValue();
    const auto sample = [=](const auto& values) {
        return sampleValue(values, lower) * (1.0 - ratio) + sampleValue(values, upper) * ratio;
    };
    const Base::Vector3d force(sample(joint.fxs), sample(joint.fys), sample(joint.fzs));
    const Base::Vector3d torque(sample(joint.txs), sample(joint.tys), sample(joint.tzs));
    const auto forceZ = axis * force.Dot(axis);
    const auto forceSide = force - forceZ;
    // Resolve the moment at the first bearing on the pin axis, preserving an
    // offset marker's wrench. FEM moment arms are mm, while histories use N m.
    const auto torqueAtOrigin = torque * siTorqueToFEMTorque
        + (marker.getPosition() - origin1).Cross(force);
    const auto torqueZ = axis * torqueAtOrigin.Dot(axis);
    const auto torqueSide = torqueAtOrigin - torqueZ;
    const auto forceSide2 = torqueSide.Cross(axis) / span;
    const auto forceSide1 = forceSide - forceSide2;

    const auto* partJ = markerPart(freecad_cast<MbDMarker*>(joint.markerJ.getValue()));
    const auto forceOnPin = forceZ * (pin == partI ? 1.0 : -1.0);
    std::vector<AnnuAnnuFacePair::ValidatedGeometry> geometries;
    size_t active = 0;
    double bestCompression = -1.0;
    for (size_t i = 0; i < annuli.size(); ++i) {
        auto& pair = *annuli[i];
        if (!((pair.faceI.getValue() == partI && pair.faceJ.getValue() == partJ)
              || (pair.faceI.getValue() == partJ && pair.faceJ.getValue() == partI))) {
            throw std::runtime_error("Flange joint annular pair must reference both joint parts.");
        }
        const auto geometry = pair.validateSampledGeometry(lower, upper, ratio);
        const auto offset = geometry.annulus.center - origin1;
        if ((offset - axis * offset.Dot(axis)).Length() > tolerance
            || geometry.annulus.axis.Cross(axis).Length() > 1.0e-7) {
            throw std::runtime_error("Flange joint annular contacts must be coaxial with the pin.");
        }
        geometries.push_back(geometry);
        const auto& link = pair.faceI.getValue() == pin ? pair.faceI : pair.faceJ;
        const auto face = referencedFace(link);
        const auto normalDirection = BRepAdaptor_Surface(face).Plane().Axis().Direction();
        Base::Vector3d normal(normalDirection.X(), normalDirection.Y(), normalDirection.Z());
        if (face.Orientation() == TopAbs_REVERSED) {
            normal = -normal;
        }
        normal = sampledPlacement(*pin, lower, upper, ratio).getRotation().multVec(normal);
        const double compression = -normal.Dot(forceOnPin);
        if (compression > bestCompression) {
            active = i;
            bestCompression = compression;
        }
    }
    if (forceZ.Length() > 1.0e-12 && bestCompression <= 0.0) {
        throw std::runtime_error("Flange joint has no outside annular face resisting the axial force.");
    }
    setOriginLoad(*cylinders[0], origin1, axis, forceSide1, Base::Vector3d());
    setOriginLoad(*cylinders[1], origin2, axis, forceSide2, Base::Vector3d());
    for (size_t i = 0; i < annuli.size(); ++i) {
        auto& pair = *annuli[i];
        const auto& geometry = geometries[i];
        setOriginLoad(
            pair,
            geometry.annulus.center,
            axis,
            i == active ? forceZ : Base::Vector3d(),
            i == active ? torqueZ : Base::Vector3d()
        );
        pair.coordsOnFace = geometry.annulusIsFaceI ? FacePair::IJUkn::I : FacePair::IJUkn::J;
    }
}
