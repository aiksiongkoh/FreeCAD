// SPDX-License-Identifier: LGPL-2.1-or-later

#pragma once

#include <App/PropertyStandard.h>
#include <Gui/ViewProviderGeometryObject.h>
#include <Mod/MbDFEM/MbDFEMGlobal.h>

class QMenu;
class SoGroup;
class SoSeparator;
class SoSwitch;

namespace MbDFEMGui
{

class MbDFEMGuiExport ViewProviderFEMPart: public Gui::ViewProviderGeometryObject
{
    PROPERTY_HEADER_WITH_OVERRIDE(MbDFEMGui::ViewProviderFEMPart);

public:
    ViewProviderFEMPart();
    ~ViewProviderFEMPart() override;

    App::PropertyInteger DLOADSampleSize;

    void attach(App::DocumentObject* object) override;
    void updateData(const App::Property* prop) override;
    bool canAddToSceneGraph() const override;
    void hide() override;
    void show() override;
    SoGroup* getChildRoot() const override;
    SoSeparator* getFrontRoot() const override;
    std::vector<App::DocumentObject*> claimChildren() const override;
    std::vector<App::DocumentObject*> claimChildren3D() const override;
    void setupContextMenu(QMenu* menu, QObject* receiver, const char* member) override;
    void onChanged(const App::Property* prop) override;

private:
    void updateChildVisibility();
    bool effectiveChildVisibility() const;

    SoSwitch* childSwitch;
    SoGroup* childRoot;
    SoSeparator* frontRoot;
};

}  // namespace MbDFEMGui
