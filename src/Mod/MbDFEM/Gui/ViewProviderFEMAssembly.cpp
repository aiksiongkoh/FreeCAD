// SPDX-License-Identifier: LGPL-2.1-or-later

#include "ViewProviderFEMAssembly.h"

#include <QMenu>

#include <Inventor/nodes/SoGroup.h>
#include <Inventor/nodes/SoSeparator.h>

#include <App/PropertyGeo.h>
#include <Mod/MbDFEM/App/FEMAssembly.h>

#include "ViewProviderUtils.h"

using namespace MbDFEMGui;

PROPERTY_SOURCE(MbDFEMGui::ViewProviderFEMAssembly, Gui::ViewProviderGeometryObject)

ViewProviderFEMAssembly::ViewProviderFEMAssembly()
    : childRoot(new SoGroup)
{
    sPixmap = "Document";

    childRoot->ref();
    pcRoot->addChild(childRoot);
}

ViewProviderFEMAssembly::~ViewProviderFEMAssembly()
{
    childRoot->unref();
    childRoot = nullptr;
}

SoGroup* ViewProviderFEMAssembly::getChildRoot() const
{
    return childRoot;
}

void ViewProviderFEMAssembly::attach(App::DocumentObject* object)
{
    Gui::ViewProviderGeometryObject::attach(object);
    hideOriginInTree(object);
    if (auto* placement = object ? object->getPlacementProperty() : nullptr) {
        updateData(placement);
    }
}

std::vector<App::DocumentObject*> ViewProviderFEMAssembly::claimChildren() const
{
    auto* assembly = getObject<MbDFEM::FEMAssembly>();
    if (!assembly) {
        return {};
    }

    hideOriginInTree(assembly);

    std::vector<App::DocumentObject*> children;
    auto folders = assembly->getCategoryFolders();
    children.insert(children.end(), folders.begin(), folders.end());
    return children;
}

std::vector<App::DocumentObject*> ViewProviderFEMAssembly::claimChildren3D() const
{
    auto* assembly = getObject<MbDFEM::FEMAssembly>();
    if (!assembly) {
        return {};
    }

    hideOriginInTree(assembly);
    return assembly->getCategoryChildren();
}

void ViewProviderFEMAssembly::setupContextMenu(QMenu* menu, QObject* receiver, const char* member)
{
    addMbDFEMContextMenuCommands(menu, {"MbDFEM_CreateFEMAssembly"});

    if (auto* otherMenu = addOtherContextMenu(menu)) {
        Gui::ViewProviderGeometryObject::setupContextMenu(otherMenu, receiver, member);
    }
    finalizeMbDFEMContextMenu(menu);
}
