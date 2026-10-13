// SPDX-License-Identifier: LGPL-2.1-or-later

#pragma once

#include "FEMJoint.h"

#include <vector>

namespace MbDFEM
{

class MbDJoint;
class FacePair;

class MbDFEMExport FEMHolePinJoint: public FEMJoint
{
    PROPERTY_HEADER_WITH_OVERRIDE(MbDFEM::FEMHolePinJoint);

public:
    FEMHolePinJoint() = default;
    ~FEMHolePinJoint() override = default;

    App::DocumentObjectExecReturn* execute() override;

    // Assign the full sampled wrench to the single cylindrical contact origin.
    void distributeJointWrench(const MbDJoint& joint, int lower = -1, int upper = -1, double ratio = 0.0);
    static bool updateParticipatingPairs(
        const MbDJoint& joint,
        const std::vector<FacePair*>& pairs,
        int lower,
        int upper,
        double ratio
    );
};

}  // namespace MbDFEM
