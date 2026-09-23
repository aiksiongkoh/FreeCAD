// SPDX-License-Identifier: LGPL-2.1-or-later

#include "ViewProviderFEMResultsFolder.h"

#include <App/Document.h>
#include <App/DocumentObject.h>
#include <App/DocumentObjectGroup.h>
#include <Gui/Command.h>
#include <Gui/Document.h>
#include <Mod/MbDFEM/App/FEMPart.h>

using namespace MbDFEMGui;

PROPERTY_SOURCE(MbDFEMGui::ViewProviderFEMResultsFolder, Gui::ViewProviderDocumentObject)

ViewProviderFEMResultsFolder::ViewProviderFEMResultsFolder()
{
    sPixmap = "folder";
    ADD_PROPERTY_TYPE(ShowColorContour, (true), "Display", App::Prop_None,
                      "Show result colors on the surface");
    ADD_PROPERTY_TYPE(ShowLegend, (true), "Display", App::Prop_None,
                      "Show the legend when color contours are enabled");
}

bool ViewProviderFEMResultsFolder::isShow() const
{
    return Visibility.getValue();
}

void ViewProviderFEMResultsFolder::onChanged(const App::Property* prop)
{
    Gui::ViewProviderDocumentObject::onChanged(prop);
    if (prop == &Visibility || prop == &ShowColorContour || prop == &ShowLegend) {
        synchronizeDisplay();
    }
}

void ViewProviderFEMResultsFolder::updateData(const App::Property* prop)
{
    Gui::ViewProviderDocumentObject::updateData(prop);
    if (getObject() && prop == &getObject()->Visibility) {
        synchronizeDisplay();
    }
}

void ViewProviderFEMResultsFolder::synchronizeDisplay()
{
    auto* folder = getObject();
    if (!folder || !folder->getDocument() || !getDocument() || isRestoring()) {
        return;
    }
    for (auto* object : folder->getDocument()->getObjects()) {
        auto* part = dynamic_cast<MbDFEM::FEMPart*>(object);
        if (!part || part->getResultsFolder() != folder) {
            continue;
        }
        if (auto* visual = part->visual.getValue()) {
            if (auto* view = getDocument()->getViewProvider(visual)) {
                for (const auto* name : {"ShowColorContour", "ShowLegend"}) {
                    auto* target = dynamic_cast<App::PropertyBool*>(view->getPropertyByName(name));
                    auto* source = static_cast<App::PropertyBool*>(getPropertyByName(name));
                    if (target) {
                        target->setValue(source->getValue());
                    }
                }
            }
            visual->Visibility.setValue(Visibility.getValue());
        }
        return;
    }
}

std::vector<App::DocumentObject*> ViewProviderFEMResultsFolder::claimChildren() const
{
    std::vector<App::DocumentObject*> children;
    auto* folder = dynamic_cast<App::DocumentObjectGroup*>(getObject());
    if (!folder) {
        return children;
    }

    children = folder->Group.getValues();
    return children;
}

bool ViewProviderFEMResultsFolder::doubleClicked()
{
    auto* object = getObject();
    auto* document = object ? object->getDocument() : nullptr;
    if (!object || !document) {
        return false;
    }

    const std::string documentName = document->getName();
    const std::string objectName = object->getNameInDocument();
    const std::string command = "import FreeCAD as App\n"
                                "import FreeCADMbDFEMResultsPanel\n"
                                "obj = App.getDocument('"
        + documentName + "').getObject('" + objectName
        + "')\n"
          "FreeCADMbDFEMResultsPanel.show_results_task_panel(obj)";

    Gui::Command::runCommand(Gui::Command::App, command.c_str());
    return true;
}
