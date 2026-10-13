// SPDX-License-Identifier: LGPL-2.1-or-later

#pragma once

#include <App/DocumentObject.h>
#include <App/PropertyLinks.h>
#include <App/PropertyStandard.h>
#include <Mod/MbDFEM/MbDFEMGlobal.h>

namespace MbDFEM
{

class MbDFEMExport FEMSimulationParameters: public App::DocumentObject
{
    PROPERTY_HEADER_WITH_OVERRIDE(MbDFEM::FEMSimulationParameters);

public:
    FEMSimulationParameters();
    ~FEMSimulationParameters() override = default;

    App::PropertyLinkList selectedParts;
    App::PropertyInteger currentState;
    App::PropertyInteger startState;
    App::PropertyInteger endState;
    App::PropertyBool missingOnly;
    App::PropertyBool continueOnError;
    App::PropertyBool settingsInitialized;

    const char* getViewProviderName() const override
    {
        return "MbDFEMGui::ViewProviderFEMSimulationParameters";
    }
};

}  // namespace MbDFEM
