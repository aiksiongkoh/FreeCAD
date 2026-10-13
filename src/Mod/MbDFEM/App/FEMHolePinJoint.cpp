// SPDX-License-Identifier: LGPL-2.1-or-later

#include "FEMHolePinJoint.h"

#include "CylCylFacePair.h"
#include "MbDJoint.h"

#include <App/Document.h>

#include <algorithm>
#include <stdexcept>

PROPERTY_SOURCE(MbDFEM::FEMHolePinJoint, MbDFEM::FEMJoint)

App::DocumentObjectExecReturn* MbDFEM::FEMHolePinJoint::execute()
{
    const auto& pairs = facePairs.getValues();
    if (pairs.size() != 1 || !pairs.front()
        || !pairs.front()->isDerivedFrom(CylCylFacePair::getClassTypeId())) {
        return new App::DocumentObjectExecReturn(
            "FEMHolePinJoint requires exactly one CylCylFacePair in facePairs.",
            this
        );
    }

    return FEMJoint::execute();
}

void MbDFEM::FEMHolePinJoint::distributeJointWrench(const MbDJoint& joint, int lower, int upper, double ratio)
{
    if (mbdItem.getValue() != &joint) {
        throw std::runtime_error("FEMHolePinJoint does not reference the supplied MbDJoint.");
    }
    const auto& pairs = facePairs.getValues();
    auto* pair = pairs.size() == 1 ? freecad_cast<CylCylFacePair*>(pairs.front()) : nullptr;
    if (!pair) {
        throw std::runtime_error("FEMHolePinJoint requires exactly one CylCylFacePair in facePairs.");
    }
    // With one contact, the full force is assigned to forceOnFaceIatOrigin.
    // updateJointState transfers the marker-I moment to the hole origin and
    // stores it in torqueOnFaceIatOrigin (N mm), ready for nodal discretization.
    pair->updateJointState(joint, lower, upper, ratio, 1);
}

bool MbDFEM::FEMHolePinJoint::updateParticipatingPairs(
    const MbDJoint& joint,
    const std::vector<FacePair*>& pairs,
    int lower,
    int upper,
    double ratio
)
{
    for (auto* object : joint.getDocument()->getObjects()) {
        auto* femJoint = freecad_cast<FEMHolePinJoint*>(object);
        if (!femJoint || femJoint->mbdItem.getValue() != &joint) {
            continue;
        }
        const auto& owned = femJoint->facePairs.getValues();
        const bool overlaps = std::any_of(pairs.begin(), pairs.end(), [&owned](FacePair* pair) {
            return pair && std::find(owned.begin(), owned.end(), pair) != owned.end();
        });
        if (!overlaps) {
            continue;
        }
        if (owned.size() != 1 || !std::all_of(pairs.begin(), pairs.end(), [&owned](FacePair* pair) {
                return pair == owned.front();
            })) {
            throw std::runtime_error("FEMHolePinJoint loading requires only its single FacePair.");
        }
        femJoint->distributeJointWrench(joint, lower, upper, ratio);
        return true;
    }
    return false;
}
