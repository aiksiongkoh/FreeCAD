// SPDX-License-Identifier: LGPL-2.1-or-later

#pragma once

#include <Gui/ViewProviderPart.h>
#include <Mod/MbDFEM/MbDFEMGlobal.h>

class QMenu;
class SoGroup;
class SoSwitch;

namespace MbDFEMGui
{

class MbDFEMGuiExport ViewProviderFEMAssembly: public Gui::ViewProviderPart
{
    PROPERTY_HEADER_WITH_OVERRIDE(MbDFEMGui::ViewProviderFEMAssembly);

public:
    ViewProviderFEMAssembly();
    ~ViewProviderFEMAssembly() override;

    void attach(App::DocumentObject* object) override;
    void updateData(const App::Property* prop) override;
    SoGroup* getChildRoot() const override;
    std::vector<App::DocumentObject*> claimChildren() const override;
    std::vector<App::DocumentObject*> claimChildren3D() const override;
    void setupContextMenu(QMenu* menu, QObject* receiver, const char* member) override;
    void onChanged(const App::Property* prop) override;

private:
    void updateChildVisibility();
    bool effectiveChildVisibility() const;

    SoSwitch* childSwitch;
    SoGroup* childRoot;
};

}  // namespace MbDFEMGui
