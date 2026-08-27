// SPDX-License-Identifier: LGPL-2.1-or-later

#pragma once

#include <Gui/ViewProviderGeometryObject.h>
#include <Mod/MbDFEM/MbDFEMGlobal.h>

class QMenu;
class SoGroup;

namespace MbDFEMGui
{

class MbDFEMGuiExport ViewProviderFEMAssembly: public Gui::ViewProviderGeometryObject
{
    PROPERTY_HEADER_WITH_OVERRIDE(MbDFEMGui::ViewProviderFEMAssembly);

public:
    ViewProviderFEMAssembly();
    ~ViewProviderFEMAssembly() override;

    void attach(App::DocumentObject* object) override;
    SoGroup* getChildRoot() const override;
    std::vector<App::DocumentObject*> claimChildren() const override;
    std::vector<App::DocumentObject*> claimChildren3D() const override;
    void setupContextMenu(QMenu* menu, QObject* receiver, const char* member) override;

private:
    SoGroup* childRoot;
};

}  // namespace MbDFEMGui
