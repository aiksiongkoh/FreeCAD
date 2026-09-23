// SPDX-License-Identifier: LGPL-2.1-or-later

#pragma once

#include "FacePair.h"

namespace MbDFEM
{

class MbDFEMExport RectRectFacePair: public FacePair
{
    PROPERTY_HEADER_WITH_OVERRIDE(MbDFEM::RectRectFacePair);

public:
    RectRectFacePair() = default;
    RectRectFacePair(App::DocumentObject* objectI,
                     std::string subNameI,
                     App::DocumentObject* objectJ,
                     std::string subNameJ);
};

}  // namespace MbDFEM
