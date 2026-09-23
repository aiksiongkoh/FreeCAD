// SPDX-License-Identifier: LGPL-2.1-or-later

#include "RectRectFacePair.h"

#include <utility>

PROPERTY_SOURCE(MbDFEM::RectRectFacePair, MbDFEM::FacePair)

MbDFEM::RectRectFacePair::RectRectFacePair(App::DocumentObject* objectI,
                                           std::string subNameI,
                                           App::DocumentObject* objectJ,
                                           std::string subNameJ)
    : FacePair(objectI, std::move(subNameI), objectJ, std::move(subNameJ))
{}
