// SPDX-License-Identifier: LGPL-2.1-or-later

#include "ViewProviderFEMAssembly.h"

#include <QMenu>

#include <Inventor/nodes/SoGroup.h>
#include <Inventor/nodes/SoSeparator.h>
#include <Inventor/nodes/SoSwitch.h>

#include <App/PropertyGeo.h>
#include <Mod/MbDFEM/App/FEMAssembly.h>

#include "ViewProviderUtils.h"

using namespace MbDFEMGui;

PROPERTY_SOURCE(MbDFEMGui::ViewProviderFEMAssembly, Gui::ViewProviderPart)

ViewProviderFEMAssembly::ViewProviderFEMAssembly()
    : childSwitch(new SoSwitch)
    , childRoot(new SoGroup)
{
    sPixmap = "Document";

    childSwitch->ref();
    childRoot->ref();
    childSwitch->whichChild = effectiveChildVisibility() ? SO_SWITCH_ALL : SO_SWITCH_NONE;
    childSwitch->addChild(childRoot);
    pcRoot->addChild(childSwitch);
}

ViewProviderFEMAssembly::~ViewProviderFEMAssembly()
{
    childSwitch->unref();
    childSwitch = nullptr;
    childRoot->unref();
    childRoot = nullptr;
}

SoGroup* ViewProviderFEMAssembly::getChildRoot() const
{
    return childRoot;
}

void ViewProviderFEMAssembly::attach(App::DocumentObject* object)
{
    Gui::ViewProviderPart::attach(object);
    hideOriginInTree(object);
    if (auto* placement = object ? object->getPlacementProperty() : nullptr) {
        updateData(placement);
    }
    updateChildVisibility();
}

void ViewProviderFEMAssembly::updateData(const App::Property* prop)
{
    Gui::ViewProviderPart::updateData(prop);

    auto* assembly = getObject<MbDFEM::FEMAssembly>();
    if (assembly && prop == &assembly->Visibility) {
        updateChildVisibility();
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

    std::vector<App::DocumentObject*> children;
    for (auto* child : assembly->getCategoryChildren()) {
        if (child && child->Visibility.getValue()) {
            children.push_back(child);
        }
    }
    return children;
}

void ViewProviderFEMAssembly::setupContextMenu(QMenu* menu, QObject* receiver, const char* member)
{
    addMbDFEMContextMenuCommands(menu, {"MbDFEM_CreateFEMAssembly"});

    if (auto* otherMenu = addOtherContextMenu(menu)) {
        Gui::ViewProviderPart::setupContextMenu(otherMenu, receiver, member);
    }
    finalizeMbDFEMContextMenu(menu);
}

void ViewProviderFEMAssembly::onChanged(const App::Property* prop)
{
    Gui::ViewProviderPart::onChanged(prop);

    if (prop == &Visibility) {
        updateChildVisibility();
    }
}

void ViewProviderFEMAssembly::updateChildVisibility()
{
    if (childSwitch) {
        childSwitch->whichChild = effectiveChildVisibility() ? SO_SWITCH_ALL : SO_SWITCH_NONE;
    }
}

bool ViewProviderFEMAssembly::effectiveChildVisibility() const
{
    auto* assembly = getObject<MbDFEM::FEMAssembly>();
    return (!assembly || assembly->Visibility.getValue()) && Visibility.getValue();
}
