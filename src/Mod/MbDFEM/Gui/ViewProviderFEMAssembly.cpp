// SPDX-License-Identifier: LGPL-2.1-or-later

#include "ViewProviderFEMAssembly.h"

#include <string>

#include <QMenu>

#include <Inventor/nodes/SoGroup.h>
#include <Inventor/nodes/SoSeparator.h>
#include <Inventor/nodes/SoSwitch.h>

#include <App/Document.h>
#include <App/PropertyGeo.h>
#include <Base/Interpreter.h>
#include <Mod/MbDFEM/App/FEMAssembly.h>

#include "ViewProviderUtils.h"

using namespace MbDFEMGui;

namespace
{

std::string quotedPythonString(const char* value)
{
    std::string result = "'";
    for (const char* cursor = value ? value : ""; *cursor; ++cursor) {
        if (*cursor == '\\' || *cursor == '\'') {
            result += '\\';
        }
        result += *cursor;
    }
    result += "'";
    return result;
}

}  // namespace

PROPERTY_SOURCE(MbDFEMGui::ViewProviderFEMAssembly, Gui::ViewProviderPart)

ViewProviderFEMAssembly::ViewProviderFEMAssembly()
    : childSwitch(new SoSwitch)
    , childRoot(new SoGroup)
{
    sPixmap = "Document";
    ADD_PROPERTY_TYPE(DLOADAutoScale,
                      (true),
                      "MbDFEM",
                      App::Prop_None,
                      "Scale DLOAD arrows from assembly-wide result magnitudes");
    ADD_PROPERTY_TYPE(DLOADScale,
                      (1.0),
                      "MbDFEM",
                      App::Prop_None,
                      "DLOAD arrow scale multiplier, or absolute scale when auto-scale is off");
    ADD_PROPERTY_TYPE(CLOADAutoScale,
                      (true),
                      "MbDFEM",
                      App::Prop_None,
                      "Scale CLOAD arrows from assembly-wide result magnitudes");
    ADD_PROPERTY_TYPE(CLOADScale,
                      (1.0),
                      "MbDFEM",
                      App::Prop_None,
                      "CLOAD arrow scale multiplier, or absolute scale when auto-scale is off");

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

    if (prop != &DLOADAutoScale && prop != &DLOADScale && prop != &CLOADAutoScale
        && prop != &CLOADScale) {
        return;
    }

    auto* assembly = getObject();
    auto* document = assembly ? assembly->getDocument() : nullptr;
    if (!assembly || !document) {
        return;
    }

    try {
        const bool isCLOAD = prop == &CLOADAutoScale || prop == &CLOADScale;
        const bool forceScalePrepare = prop == &DLOADAutoScale || prop == &CLOADAutoScale;
        const std::string module = isCLOAD ? "FreeCADMbDFEMCLOADs" : "FreeCADMbDFEMDLOADs";
        const std::string script =
            "import " + module + "\n" + module + ".refresh_assembly_diagrams("
            + quotedPythonString(document->getName()) + ", "
            + quotedPythonString(assembly->getNameInDocument()) + ", "
            + std::string(forceScalePrepare ? "True" : "False") + ")";
        Base::Interpreter().runString(script.c_str());
    }
    catch (const Base::Exception&) {
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
