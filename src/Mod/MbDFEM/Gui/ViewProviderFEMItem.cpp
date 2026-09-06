// SPDX-License-Identifier: LGPL-2.1-or-later

#include "ViewProviderFEMItem.h"

#include <QMenu>

#include <Inventor/nodes/SoGroup.h>
#include <Inventor/nodes/SoSeparator.h>

#include <Mod/MbDFEM/App/FEMAssembly.h>
#include <Mod/MbDFEM/App/FEMPart.h>

#include "ViewProviderUtils.h"

using namespace MbDFEMGui;

PROPERTY_SOURCE(MbDFEMGui::ViewProviderFEMItem, Gui::ViewProviderDocumentObject)

ViewProviderFEMItem::ViewProviderFEMItem()
    : childRoot(new SoGroup)
{
    sPixmap = "Document";

    childRoot->ref();
    pcRoot->addChild(childRoot);
}

ViewProviderFEMItem::~ViewProviderFEMItem()
{
    childRoot->unref();
    childRoot = nullptr;
}

SoGroup* ViewProviderFEMItem::getChildRoot() const
{
    return childRoot;
}

std::vector<App::DocumentObject*> ViewProviderFEMItem::claimChildren() const
{
    auto* assembly = getObject<MbDFEM::FEMAssembly>();
    if (assembly) {
        std::vector<App::DocumentObject*> children;
        auto folders = assembly->getCategoryFolders();
        children.insert(children.end(), folders.begin(), folders.end());
        return children;
    }

    auto* part = getObject<MbDFEM::FEMPart>();
    if (part) {
        std::vector<App::DocumentObject*> children;
        if (auto* mesh = part->mesh.getValue()) {
            children.push_back(mesh);
        }
        if (auto* solver = part->solver.getValue()) {
            children.push_back(solver);
        }
        return children;
    }

    return {};
}

std::vector<App::DocumentObject*> ViewProviderFEMItem::claimChildren3D() const
{
    auto* assembly = getObject<MbDFEM::FEMAssembly>();
    if (assembly) {
        return assembly->getCategoryChildren();
    }

    auto* part = getObject<MbDFEM::FEMPart>();
    if (part) {
        return {};
    }

    return {};
}

void ViewProviderFEMItem::setupContextMenu(QMenu* menu, QObject* receiver, const char* member)
{
    if (getObject<MbDFEM::FEMPart>()) {
        addMbDFEMContextMenuCommands(menu, {"MbDFEM_CreateFEMPartMesh"});
    }
    else {
        addMbDFEMContextMenuCommands(menu, {"MbDFEM_CreateFEMAssembly"});
    }

    if (auto* otherMenu = addOtherContextMenu(menu)) {
        Gui::ViewProviderDocumentObject::setupContextMenu(otherMenu, receiver, member);
    }
    finalizeMbDFEMContextMenu(menu);
}
