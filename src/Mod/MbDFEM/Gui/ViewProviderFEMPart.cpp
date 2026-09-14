// SPDX-License-Identifier: LGPL-2.1-or-later

#include "ViewProviderFEMPart.h"

#include <QMenu>

#include <Inventor/nodes/SoGroup.h>
#include <Inventor/nodes/SoSeparator.h>
#include <Inventor/nodes/SoSwitch.h>

#include <App/DocumentObjectGroup.h>
#include <App/GeoFeatureGroupExtension.h>
#include <App/MaterialObject.h>
#include <App/OriginGroupExtension.h>
#include <App/PropertyGeo.h>
#include <Mod/MbDFEM/App/FEMPart.h>

#include "ViewProviderUtils.h"

using namespace MbDFEMGui;

PROPERTY_SOURCE(MbDFEMGui::ViewProviderFEMPart, Gui::ViewProviderGeometryObject)

namespace
{

bool isClaimedChildVisible(const App::DocumentObject* child)
{
    return child && child->Visibility.getValue();
}

bool isDisplayMeshChild(const MbDFEM::FEMPart* part, const App::DocumentObject* child)
{
    if (!part || !child) {
        return false;
    }

    const std::string prefix = std::string(part->getNameInDocument()) + "_";
    const std::string name = child->getNameInDocument();
    return name == prefix + "CLOADFaces" || name == prefix + "DLOADElements";
}

}  // namespace

ViewProviderFEMPart::ViewProviderFEMPart()
    : childSwitch(new SoSwitch)
    , childRoot(new SoGroup)
    , frontRoot(new SoSeparator)
{
    sPixmap = "Document";
    ADD_PROPERTY_TYPE(DLOADSampleSize,
                      (20),
                      "MbDFEM",
                      App::Prop_None,
                      "Maximum number of FEM elements sampled for Show DLOADs arrows");

    childSwitch->ref();
    childRoot->ref();
    frontRoot->ref();
    childSwitch->whichChild = effectiveChildVisibility() ? SO_SWITCH_ALL : SO_SWITCH_NONE;
    childSwitch->addChild(childRoot);
    pcRoot->addChild(childSwitch);
}

ViewProviderFEMPart::~ViewProviderFEMPart()
{
    childSwitch->unref();
    childSwitch = nullptr;
    childRoot->unref();
    childRoot = nullptr;
    frontRoot->unref();
    frontRoot = nullptr;
}

SoGroup* ViewProviderFEMPart::getChildRoot() const
{
    return childRoot;
}

SoSeparator* ViewProviderFEMPart::getFrontRoot() const
{
    return frontRoot;
}

void ViewProviderFEMPart::attach(App::DocumentObject* object)
{
    Gui::ViewProviderGeometryObject::attach(object);
    hideOriginInTree(object);
    if (auto* placement = object ? object->getPlacementProperty() : nullptr) {
        updateData(placement);
    }
    updateChildVisibility();
}

void ViewProviderFEMPart::updateData(const App::Property* prop)
{
    Gui::ViewProviderGeometryObject::updateData(prop);

    auto* part = getObject<MbDFEM::FEMPart>();
    if (part && prop == &part->Visibility) {
        updateChildVisibility();
    }
}

bool ViewProviderFEMPart::canAddToSceneGraph() const
{
    return Gui::ViewProviderGeometryObject::canAddToSceneGraph();
}

void ViewProviderFEMPart::hide()
{
    Gui::ViewProviderGeometryObject::hide();
    updateChildVisibility();
}

void ViewProviderFEMPart::show()
{
    Gui::ViewProviderGeometryObject::show();
    updateChildVisibility();
}

std::vector<App::DocumentObject*> ViewProviderFEMPart::claimChildren() const
{
    auto* part = getObject<MbDFEM::FEMPart>();
    if (!part) {
        return {};
    }

    hideOriginInTree(part);

    std::vector<App::DocumentObject*> children;
    for (auto* object : part->Group.getValues()) {
        if (object && object->isDerivedFrom<App::MaterialObject>()) {
            children.push_back(object);
        }
    }
    if (auto* mesh = part->mesh.getValue()) {
        children.push_back(mesh);
    }
    for (auto* object : part->Group.getValues()) {
        if (isDisplayMeshChild(part, object)) {
            children.push_back(object);
        }
    }
    if (auto* solver = part->solver.getValue()) {
        children.push_back(solver);
    }
    if (auto* resultsFolder = part->getResultsFolder()) {
        children.push_back(resultsFolder);
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

    std::vector<App::DocumentObject*> children;
    if (auto* mesh = part->mesh.getValue()) {
        if (isClaimedChildVisible(mesh)) {
            children.push_back(mesh);
        }
    }
    for (auto* object : part->Group.getValues()) {
        if (isDisplayMeshChild(part, object) && isClaimedChildVisible(object)) {
            children.push_back(object);
        }
    }
    if (auto* visual = part->visual.getValue()) {
        if (isClaimedChildVisible(visual)) {
            children.push_back(visual);
        }
    }
    return children;
}

void ViewProviderFEMPart::setupContextMenu(QMenu* menu, QObject* receiver, const char* member)
{
    Q_UNUSED(receiver)
    Q_UNUSED(member)

    addMbDFEMContextMenuCommands(
        menu,
        {"MbDFEM_CreateFEMPartMesh",
         "MbDFEM_ShowFEMPartTrueMesh",
         "MbDFEM_ShowFEMPartCLOADFaces",
         "MbDFEM_ShowFEMPartCLOADs",
         "MbDFEM_ShowFEMPartDLOADElements",
         "MbDFEM_ShowFEMPartDLOADs"});
    addOtherContextMenu(menu);
    finalizeMbDFEMContextMenu(menu);
}

void ViewProviderFEMPart::onChanged(const App::Property* prop)
{
    Gui::ViewProviderGeometryObject::onChanged(prop);

    if (prop == &Visibility) {
        if (auto* part = getObject()) {
            part->Visibility.setValue(Visibility.getValue());
        }
        updateChildVisibility();
    }
}

void ViewProviderFEMPart::updateChildVisibility()
{
    if (childSwitch) {
        childSwitch->whichChild = effectiveChildVisibility() ? SO_SWITCH_ALL : SO_SWITCH_NONE;
    }
}

bool ViewProviderFEMPart::effectiveChildVisibility() const
{
    auto* part = getObject<MbDFEM::FEMPart>();
    if (!part || !part->Visibility.getValue() || !Visibility.getValue()) {
        return false;
    }

    auto* parent = App::GeoFeatureGroupExtension::getGroupOfObject(part);
    return !parent || parent->isElementVisible(part->getNameInDocument()) != 0;
}
