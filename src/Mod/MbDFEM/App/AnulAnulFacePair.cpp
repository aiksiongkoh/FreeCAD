// SPDX-License-Identifier: LGPL-2.1-or-later

#include "AnulAnulFacePair.h"

#include <utility>

PROPERTY_SOURCE(MbDFEM::AnulAnulFacePair, MbDFEM::FacePair)

MbDFEM::AnulAnulFacePair::AnulAnulFacePair(App::DocumentObject* objectI,
                                           std::string subNameI,
                                           App::DocumentObject* objectJ,
                                           std::string subNameJ)
    : FacePair(objectI, std::move(subNameI), objectJ, std::move(subNameJ))
{}
