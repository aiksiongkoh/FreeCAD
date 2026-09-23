// SPDX-License-Identifier: LGPL-2.1-or-later

#pragma once

#include <App/DocumentObject.h>
#include <App/PropertyLinks.h>
#include <Mod/MbDFEM/MbDFEMGlobal.h>

#include <string>

namespace MbDFEM
{

class MbDFEMExport FacePair: public App::DocumentObject
{
    PROPERTY_HEADER_WITH_OVERRIDE(MbDFEM::FacePair);

public:
    FacePair();
    ~FacePair() override = default;

    FacePair(App::DocumentObject* objectI,
             std::string subNameI,
             App::DocumentObject* objectJ,
             std::string subNameJ);

    App::PropertyLinkSub faceI;
    App::PropertyLinkSub faceJ;
};

}  // namespace MbDFEM
