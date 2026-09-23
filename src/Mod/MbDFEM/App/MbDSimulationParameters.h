// SPDX-License-Identifier: LGPL-2.1-or-later

#pragma once

#include <App/DocumentObject.h>
#include <App/PropertyStandard.h>
#include <Mod/MbDFEM/MbDFEMGlobal.h>

namespace MbDFEM
{

class MbDFEMExport MbDSimulationParameters: public App::DocumentObject
{
    PROPERTY_HEADER_WITH_OVERRIDE(MbDFEM::MbDSimulationParameters);

public:
    MbDSimulationParameters();
    ~MbDSimulationParameters() override = default;

    App::PropertyFloat startTime;
    App::PropertyFloat endTime;
    App::PropertyFloat outputInterval;
    App::PropertyFloat minStepSize;
    App::PropertyFloat maxStepSize;
    App::PropertyInteger significantDigits;
    App::PropertyInteger maxIterations;

    const char* getViewProviderName() const override
    {
        return "MbDFEMGui::ViewProviderMbDSimulationParameters";
    }
};

}  // namespace MbDFEM
