// SPDX-License-Identifier: LGPL-2.1-or-later

#include "ViewProviderFEMPart.h"

#include <QMenu>

#include <Inventor/nodes/SoGroup.h>
#include <Inventor/nodes/SoSeparator.h>

#include <App/PropertyGeo.h>
#include <Mod/MbDFEM/App/FEMPart.h>

#include "ViewProviderUtils.h"

using namespace MbDFEMGui;

PROPERTY_SOURCE(MbDFEMGui::ViewProviderFEMPart, Gui::ViewProviderGeometryObject)

ViewProviderFEMPart::ViewProviderFEMPart()
    : childRoot(new SoGroup)
{
    sPixmap = "Document";

    childRoot->ref();
    pcRoot->addChild(childRoot);
}

ViewProviderFEMPart::~ViewProviderFEMPart()
{
    childRoot->unref();
    childRoot = nullptr;
}

SoGroup* ViewProviderFEMPart::getChildRoot() const
{
    return childRoot;
}

void ViewProviderFEMPart::attach(App::DocumentObject* object)
{
    Gui::ViewProviderGeometryObject::attach(object);
    hideOriginInTree(object);
    if (auto* placement = object ? object->getPlacementProperty() : nullptr) {
        updateData(placement);
    }
}

std::vector<App::DocumentObject*> ViewProviderFEMPart::claimChildren() const
{
    auto* part = getObject<MbDFEM::FEMPart>();
    if (!part) {
        return {};
    }

    hideOriginInTree(part);

    std::vector<App::DocumentObject*> children;
    if (auto* material = part->material.getValue()) {
        children.push_back(material);
    }
    if (auto* mesh = part->mesh.getValue()) {
        children.push_back(mesh);
    }
    if (auto* solver = part->solver.getValue()) {
        children.push_back(solver);
    }
    return children;
}

std::vector<App::DocumentObject*> ViewProviderFEMPart::claimChildren3D() const
{
    auto* part = getObject<MbDFEM::FEMPart>();
    if (!part) {
        return {};
    }

    hideOriginInTree(part);
    return {};
}

void ViewProviderFEMPart::setupContextMenu(QMenu* menu, QObject* receiver, const char* member)
{
    Q_UNUSED(receiver)
    Q_UNUSED(member)

    addMbDFEMContextMenuCommands(menu, {"MbDFEM_CreateFEMPartMesh"});
    addOtherContextMenu(menu);
    finalizeMbDFEMContextMenu(menu);
}
