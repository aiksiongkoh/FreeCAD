// SPDX-License-Identifier: LGPL-2.1-or-later

#pragma once

#include "FEMItem.h"

#include <App/PropertyLinks.h>

namespace MbDFEM
{

class MbDFEMExport FEMJoint: public FEMItem
{
    PROPERTY_HEADER_WITH_OVERRIDE(MbDFEM::FEMJoint);

public:
    FEMJoint();
    ~FEMJoint() override = default;

    App::PropertyLinkList facePairs;
};

}  // namespace MbDFEM
