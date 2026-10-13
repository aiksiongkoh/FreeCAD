// SPDX-License-Identifier: LGPL-2.1-or-later

#include "ViewProviderFEMSimulationParameters.h"

#include <App/Document.h>
#include <App/DocumentObject.h>
#include <Gui/Command.h>

using namespace MbDFEMGui;

PROPERTY_SOURCE(MbDFEMGui::ViewProviderFEMSimulationParameters, Gui::ViewProviderDocumentObject)

ViewProviderFEMSimulationParameters::ViewProviderFEMSimulationParameters()
{
    sPixmap = "Document";
}

bool ViewProviderFEMSimulationParameters::doubleClicked()
{
    auto* object = getObject();
    auto* document = object ? object->getDocument() : nullptr;
    if (!object || !document) {
        return false;
    }

    const std::string command
        = "import FreeCAD as App\nimport FreeCADMbDFEMSimulation\n"
          "FreeCADMbDFEMSimulation.show_parameters_task_panel(App.getDocument('"
        + std::string(document->getName()) + "').getObject('"
        + std::string(object->getNameInDocument()) + "'))";
    Gui::Command::runCommand(Gui::Command::App, command.c_str());
    return true;
}
