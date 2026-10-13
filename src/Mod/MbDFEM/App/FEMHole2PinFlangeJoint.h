// SPDX-License-Identifier: LGPL-2.1-or-later

#pragma once

#include "FEMJoint.h"

#include <vector>

namespace MbDFEM
{

class MbDJoint;
class FacePair;

class MbDFEMExport FEMHole2PinFlangeJoint: public FEMJoint
{
    PROPERTY_HEADER_WITH_OVERRIDE(MbDFEM::FEMHole2PinFlangeJoint);

public:
    FEMHole2PinFlangeJoint() = default;
    ~FEMHole2PinFlangeJoint() override = default;

    App::DocumentObjectExecReturn* execute() override;

    void distributeJointWrench(const MbDJoint& joint, int lower = -1, int upper = -1, double ratio = 0.0);

    // Use specialized distribution only for pairs belonging to this FEM joint.
    // Returns false for other FEM joint types, which retain their own load policy.
    static bool updateParticipatingPairs(
        const MbDJoint& joint,
        const std::vector<FacePair*>& pairs,
        int lower,
        int upper,
        double ratio
    );
};

}  // namespace MbDFEM
