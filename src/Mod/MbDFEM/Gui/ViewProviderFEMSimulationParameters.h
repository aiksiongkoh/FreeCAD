// SPDX-License-Identifier: LGPL-2.1-or-later

#pragma once

#include <Gui/ViewProviderDocumentObject.h>
#include <Mod/MbDFEM/MbDFEMGlobal.h>

namespace MbDFEMGui
{

class MbDFEMGuiExport ViewProviderFEMSimulationParameters: public Gui::ViewProviderDocumentObject
{
    PROPERTY_HEADER_WITH_OVERRIDE(MbDFEMGui::ViewProviderFEMSimulationParameters);

public:
    ViewProviderFEMSimulationParameters();
    ~ViewProviderFEMSimulationParameters() override = default;

    bool doubleClicked() override;
};

}  // namespace MbDFEMGui
