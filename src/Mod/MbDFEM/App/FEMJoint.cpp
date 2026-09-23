// SPDX-License-Identifier: LGPL-2.1-or-later

#include "FEMJoint.h"

PROPERTY_SOURCE(MbDFEM::FEMJoint, MbDFEM::FEMItem)

MbDFEM::FEMJoint::FEMJoint()
{
    ADD_PROPERTY_TYPE(facePairs,
                      (nullptr),
                      "MbDFEM",
                      App::Prop_None,
                      "Touching FacePair objects");
    facePairs.setScope(App::LinkScope::Global);
}
