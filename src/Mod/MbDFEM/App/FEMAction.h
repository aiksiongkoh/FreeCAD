// SPDX-License-Identifier: LGPL-2.1-or-later

#pragma once

#include "FEMItem.h"

namespace MbDFEM
{

class MbDFEMExport FEMAction: public FEMItem
{
    PROPERTY_HEADER_WITH_OVERRIDE(MbDFEM::FEMAction);

public:
    FEMAction() = default;
    ~FEMAction() override = default;
};

}  // namespace MbDFEM
