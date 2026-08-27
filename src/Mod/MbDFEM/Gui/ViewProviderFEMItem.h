// SPDX-License-Identifier: LGPL-2.1-or-later

#pragma once

#include <Gui/ViewProviderDocumentObject.h>
#include <Mod/MbDFEM/MbDFEMGlobal.h>

class QMenu;
class SoGroup;

namespace MbDFEMGui
{

class MbDFEMGuiExport ViewProviderFEMItem: public Gui::ViewProviderDocumentObject
{
    PROPERTY_HEADER_WITH_OVERRIDE(MbDFEMGui::ViewProviderFEMItem);

public:
    ViewProviderFEMItem();
    ~ViewProviderFEMItem() override;

    SoGroup* getChildRoot() const override;
    std::vector<App::DocumentObject*> claimChildren() const override;
    std::vector<App::DocumentObject*> claimChildren3D() const override;
    void setupContextMenu(QMenu* menu, QObject* receiver, const char* member) override;

private:
    SoGroup* childRoot;
};

}  // namespace MbDFEMGui
