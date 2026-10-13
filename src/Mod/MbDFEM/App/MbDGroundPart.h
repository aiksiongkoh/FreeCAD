// SPDX-License-Identifier: LGPL-2.1-or-later

#pragma once

#include "MbDPart.h"

namespace MbDFEM
{

class MbDFEMExport MbDGroundPart: public MbDPart
{
    PROPERTY_HEADER_WITH_OVERRIDE(MbDFEM::MbDGroundPart);

public:
    MbDGroundPart();
    ~MbDGroundPart() override = default;

    App::PropertyLinkSubList groundFaces;

    // The caller owns the document transaction.
    static MbDGroundPart* convert(MbDPart* part);
};

}  // namespace MbDFEM
