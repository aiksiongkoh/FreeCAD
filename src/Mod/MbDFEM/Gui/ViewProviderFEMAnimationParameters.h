// SPDX-License-Identifier: LGPL-2.1-or-later

#pragma once

#include <Gui/ViewProviderDocumentObject.h>
#include <Mod/MbDFEM/MbDFEMGlobal.h>

namespace MbDFEMGui
{

class MbDFEMGuiExport ViewProviderFEMAnimationParameters: public Gui::ViewProviderDocumentObject
{
    PROPERTY_HEADER_WITH_OVERRIDE(MbDFEMGui::ViewProviderFEMAnimationParameters);

public:
    ViewProviderFEMAnimationParameters();
    ~ViewProviderFEMAnimationParameters() override = default;

    bool doubleClicked() override;
};

}  // namespace MbDFEMGui
