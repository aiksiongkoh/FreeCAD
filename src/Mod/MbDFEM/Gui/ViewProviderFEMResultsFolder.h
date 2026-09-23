// SPDX-License-Identifier: LGPL-2.1-or-later

#pragma once

#include <Gui/ViewProviderDocumentObject.h>
#include <Mod/MbDFEM/MbDFEMGlobal.h>

namespace MbDFEMGui
{

class MbDFEMGuiExport ViewProviderFEMResultsFolder: public Gui::ViewProviderDocumentObject
{
    PROPERTY_HEADER_WITH_OVERRIDE(MbDFEMGui::ViewProviderFEMResultsFolder);

public:
    ViewProviderFEMResultsFolder();
    ~ViewProviderFEMResultsFolder() override = default;

    std::vector<App::DocumentObject*> claimChildren() const override;
    bool doubleClicked() override;
    bool isShow() const override;
    void onChanged(const App::Property* prop) override;
    void updateData(const App::Property* prop) override;

    App::PropertyBool ShowColorContour;
    App::PropertyBool ShowLegend;

private:
    void synchronizeDisplay();
};

}  // namespace MbDFEMGui
