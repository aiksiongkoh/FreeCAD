// SPDX-License-Identifier: LGPL-2.1-or-later

#pragma once

#include <Gui/ViewProviderGeometryObject.h>
#include <Mod/MbDFEM/MbDFEMGlobal.h>

class QMenu;
class SoGroup;
class SoSwitch;

namespace MbDFEMGui
{

class MbDFEMGuiExport ViewProviderFEMPart: public Gui::ViewProviderGeometryObject
{
    PROPERTY_HEADER_WITH_OVERRIDE(MbDFEMGui::ViewProviderFEMPart);

public:
    ViewProviderFEMPart();
    ~ViewProviderFEMPart() override;

    void attach(App::DocumentObject* object) override;
    void updateData(const App::Property* prop) override;
    bool canAddToSceneGraph() const override;
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
