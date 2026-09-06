// SPDX-License-Identifier: LGPL-2.1-or-later

#include "ViewProviderFEMResultsFolder.h"

#include <App/Document.h>
#include <App/DocumentObject.h>
#include <App/DocumentObjectGroup.h>
#include <Gui/Command.h>
#include <Mod/MbDFEM/App/FEMPart.h>

using namespace MbDFEMGui;

PROPERTY_SOURCE(MbDFEMGui::ViewProviderFEMResultsFolder, Gui::ViewProviderDocumentObject)

ViewProviderFEMResultsFolder::ViewProviderFEMResultsFolder()
{
    sPixmap = "folder";
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
