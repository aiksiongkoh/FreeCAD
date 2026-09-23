// SPDX-License-Identifier: LGPL-2.1-or-later

#include "FacePair.h"

#include <utility>

PROPERTY_SOURCE(MbDFEM::FacePair, App::DocumentObject)

MbDFEM::FacePair::FacePair()
{
    ADD_PROPERTY_TYPE(faceI,
                      (nullptr),
                      "MbDFEM",
                      App::Prop_None,
                      "Face on side I");
    ADD_PROPERTY_TYPE(faceJ,
                      (nullptr),
                      "MbDFEM",
                      App::Prop_None,
                      "Face on side J");
    faceI.setScope(App::LinkScope::Global);
    faceJ.setScope(App::LinkScope::Global);
}

MbDFEM::FacePair::FacePair(App::DocumentObject* objectI,
                           std::string subNameI,
                           App::DocumentObject* objectJ,
                           std::string subNameJ)
    : FacePair()
{
    faceI.setValue(objectI, std::vector<std::string> {std::move(subNameI)});
    faceJ.setValue(objectJ, std::vector<std::string> {std::move(subNameJ)});
}
