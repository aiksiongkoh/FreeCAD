// SPDX-License-Identifier: LGPL-2.1-or-later

#include "ViewProviderUtils.h"

#include <cstring>
#include <string>

#include <QAction>
#include <QMenu>

#include <Inventor/SoFullPath.h>
#include <Inventor/misc/SoChildList.h>
#include <Inventor/nodes/SoGroup.h>
#include <Inventor/nodes/SoNode.h>
#include <Inventor/nodes/SoSeparator.h>

#include <App/Document.h>
#include <App/OriginGroupExtension.h>
#include <Gui/Application.h>
#include <Gui/Action.h>
#include <Gui/Command.h>
#include <Gui/Document.h>
#include <Gui/ViewProviderDocumentObject.h>

namespace
{

bool addCommandToMenu(QMenu* menu, const char* commandName)
{
    auto* command = commandName
        ? Gui::Application::Instance->commandManager().getCommandByName(commandName)
        : nullptr;
    if (!command) {
        return false;
    }

    command->addTo(menu);
    command->testActive();
    return true;
}

bool addCommandShortcutToMenu(QMenu* menu, const char* commandName)
{
    auto* command = commandName
        ? Gui::Application::Instance->commandManager().getCommandByName(commandName)
        : nullptr;
    if (!menu || !command) {
        return false;
    }

    command->initAction();
    QAction* sourceAction = command->getAction() ? command->getAction()->action() : nullptr;
    if (!sourceAction) {
        return false;
    }

    auto* shortcutAction = new QAction(sourceAction->icon(), sourceAction->text(), menu);
    shortcutAction->setToolTip(sourceAction->toolTip());
    shortcutAction->setStatusTip(sourceAction->statusTip());
    shortcutAction->setWhatsThis(sourceAction->whatsThis());
    shortcutAction->setShortcut(sourceAction->shortcut());
    shortcutAction->setEnabled(command->isActive());
    QObject::connect(shortcutAction, &QAction::triggered, menu, [command]() {
        command->invoke(0, Gui::Command::TriggerAction);
    });
    menu->addAction(shortcutAction);
    return true;
}

}  // namespace

void MbDFEMGui::setOriginInTreeVisible(App::DocumentObject* object, bool visible)
{
    if (!object) {
        return;
    }

    auto* originGroup = object->getExtensionByType<App::OriginGroupExtension>();
    auto* origin = originGroup ? originGroup->Origin.getValue() : nullptr;
    auto* document = object->getDocument();
    auto* guiDocument = document ? Gui::Application::Instance->getDocument(document) : nullptr;
    auto* viewProvider = guiDocument && origin ? guiDocument->getViewProvider(origin) : nullptr;
    if (auto* documentViewProvider = freecad_cast<Gui::ViewProviderDocumentObject*>(viewProvider)) {
        if (documentViewProvider->ShowInTree.getValue() != visible) {
            documentViewProvider->ShowInTree.setValue(visible);
        }
    }
}

void MbDFEMGui::hideOriginInTree(App::DocumentObject* object)
{
    setOriginInTreeVisible(object, false);
}

App::DocumentObject* MbDFEMGui::getOriginObject(App::DocumentObject* object)
{
    auto* originGroup = object ? object->getExtensionByType<App::OriginGroupExtension>() : nullptr;
    return originGroup ? originGroup->Origin.getValue() : nullptr;
}

bool MbDFEMGui::addMbDFEMContextMenuCommands(QMenu* menu,
                                             std::initializer_list<const char*> commandNames)
{
    if (!menu) {
        return false;
    }

    bool addedCommand = false;
    for (const char* commandName : commandNames) {
        addedCommand = addCommandToMenu(menu, commandName) || addedCommand;
    }

    return addedCommand;
}

QMenu* MbDFEMGui::addOtherContextMenu(QMenu* menu)
{
    if (!menu) {
        return nullptr;
    }

    addCommandShortcutToMenu(menu, "Std_TransformManip");
    addCommandShortcutToMenu(menu, "Std_Delete");

    auto* otherMenu = menu->addMenu(QObject::tr("Other"));
    otherMenu->menuAction()->setProperty("MbDFEMOtherContextMenu", true);

    return otherMenu;
}

void MbDFEMGui::finalizeMbDFEMContextMenu(QMenu* menu)
{
    Q_UNUSED(menu)
}

bool MbDFEMGui::delegateSubobjectDetailPath(const Gui::ViewProviderDocumentObject* parent,
                                            const char* subname,
                                            SoFullPath* path,
                                            bool append,
                                            SoDetail*& det)
{
    if (!parent || !subname || !*subname || !path) {
        return false;
    }

    const int originalLength = path->getLength();
    const char* dot = std::strchr(subname, '.');
    if (!dot) {
        return false;
    }

    auto* object = parent->getObject();
    auto* child = object ? object->getSubObject(std::string(subname, dot - subname + 1).c_str()) : nullptr;
    auto* childViewProvider = child ? Gui::Application::Instance->getViewProvider(child) : nullptr;
    if (!childViewProvider) {
        return false;
    }

    if (auto* childRoot = parent->getChildRoot()) {
        if (append) {
            path->append(parent->getRoot());
        }
        path->append(childRoot);
    }
    else if (append) {
        path->append(parent->getRoot());
    }

    if (path->getLength()) {
        auto* tail = path->getTail();
        const SoChildList* children = tail ? tail->getChildren() : nullptr;
        if (children && children->find(childViewProvider->getRoot()) >= 0
            && childViewProvider->getDetailPath(dot + 1, path, true, det)) {
            return true;
        }
    }

    path->truncate(originalLength);
    return false;
}
