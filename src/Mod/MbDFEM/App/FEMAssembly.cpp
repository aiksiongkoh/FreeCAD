// SPDX-License-Identifier: LGPL-2.1-or-later

#include "FEMAssembly.h"

#include <array>
#include <cstring>

#include <App/Document.h>
#include <App/DocumentObjectGroup.h>

#include "MbDAssembly.h"

PROPERTY_SOURCE(MbDFEM::FEMAssembly, App::Part)

namespace
{

struct FEMAssemblyCategory
{
    App::PropertyLinkList MbDFEM::FEMAssembly::*children;
    App::DocumentObjectGroup* (MbDFEM::FEMAssembly::*getFolder)() const;
};

constexpr std::array<FEMAssemblyCategory, 4> femAssemblyCategories = {{
    {&MbDFEM::FEMAssembly::parts, &MbDFEM::FEMAssembly::getPartsFolder},
    {&MbDFEM::FEMAssembly::joints, &MbDFEM::FEMAssembly::getJointsFolder},
    {&MbDFEM::FEMAssembly::motions, &MbDFEM::FEMAssembly::getMotionsFolder},
    {&MbDFEM::FEMAssembly::actions, &MbDFEM::FEMAssembly::getActionsFolder},
}};

App::DocumentObjectGroup* getFolder(const MbDFEM::FEMAssembly* assembly,
                                    const FEMAssemblyCategory& category)
{
    return assembly ? (assembly->*(category.getFolder))() : nullptr;
}

void addToAssemblyGroup(MbDFEM::FEMAssembly* assembly, App::DocumentObjectGroup* folder)
{
    if (assembly && folder && !assembly->hasObject(folder)) {
        assembly->addObject(folder);
    }
}

App::DocumentObjectGroup* matchingFolder(const char* subname,
                                         const char*& rest,
                                         const MbDFEM::FEMAssembly* assembly)
{
    rest = nullptr;
    const char* dot = subname ? std::strchr(subname, '.') : nullptr;
    if (!dot) {
        return nullptr;
    }

    const std::string segment(subname, dot);
    for (const auto& category : femAssemblyCategories) {
        auto* folder = getFolder(assembly, category);
        if (folder && segment == folder->getNameInDocument()) {
            rest = dot + 1;
            return folder;
        }
    }
    return nullptr;
}

App::DocumentObject* findDirectChildByInternalName(const char* element,
                                                   const MbDFEM::FEMAssembly* assembly)
{
    if (!element || !*element) {
        return nullptr;
    }

    std::string name(element);
    if (!name.empty() && name.back() == '.') {
        name.pop_back();
    }

    for (const auto& category : femAssemblyCategories) {
        const auto childList = (assembly->*(category.children)).getValues();
        for (auto* child : childList) {
            if (child && name == child->getNameInDocument()) {
                return child;
            }
        }
    }
    return nullptr;
}

App::DocumentObject* matchingDirectChild(const char* subname,
                                         const char*& rest,
                                         const MbDFEM::FEMAssembly* assembly)
{
    rest = nullptr;
    const char* dot = subname ? std::strchr(subname, '.') : nullptr;
    if (!dot) {
        return findDirectChildByInternalName(subname, assembly);
    }

    const std::string segment(subname, dot);
    auto* child = findDirectChildByInternalName(segment.c_str(), assembly);
    if (child) {
        rest = dot + 1;
    }
    return child;
}

}  // namespace

MbDFEM::FEMAssembly::FEMAssembly()
{
    ADD_PROPERTY_TYPE(mbdItem,
                      (nullptr),
                      "MbDFEM",
                      App::Prop_None,
                      "Multibody assembly represented by this FEM assembly");
    mbdItem.setScope(App::LinkScope::Global);
    ADD_PROPERTY_TYPE(parts,
                      (nullptr),
                      "MbDFEM",
                      App::Prop_None,
                      "FEM parts belonging to this assembly");
    parts.setScope(App::LinkScope::Child);
    ADD_PROPERTY_TYPE(joints,
                      (nullptr),
                      "MbDFEM",
                      App::Prop_None,
                      "FEM joints belonging to this assembly");
    joints.setScope(App::LinkScope::Child);
    ADD_PROPERTY_TYPE(motions,
                      (nullptr),
                      "MbDFEM",
                      App::Prop_None,
                      "FEM motions belonging to this assembly");
    motions.setScope(App::LinkScope::Child);
    ADD_PROPERTY_TYPE(actions,
                      (nullptr),
                      "MbDFEM",
                      App::Prop_None,
                      "FEM actions belonging to this assembly");
    actions.setScope(App::LinkScope::Child);
    ADD_PROPERTY_TYPE(femParameters,
                      (nullptr),
                      "MbDFEM",
                      App::Prop_None,
                      "FEM parameters for this assembly");
    femParameters.setScope(App::LinkScope::Child);
    ADD_PROPERTY_TYPE(_partsFolder,
                      (nullptr),
                      "MbDFEM",
                      App::Prop_Hidden,
                      "Tree folder containing this assembly's FEM parts");
    _partsFolder.setScope(App::LinkScope::Hidden);
    ADD_PROPERTY_TYPE(_jointsFolder,
                      (nullptr),
                      "MbDFEM",
                      App::Prop_Hidden,
                      "Tree folder containing this assembly's FEM joints");
    _jointsFolder.setScope(App::LinkScope::Hidden);
    ADD_PROPERTY_TYPE(_motionsFolder,
                      (nullptr),
                      "MbDFEM",
                      App::Prop_Hidden,
                      "Tree folder containing this assembly's FEM motions");
    _motionsFolder.setScope(App::LinkScope::Hidden);
    ADD_PROPERTY_TYPE(_actionsFolder,
                      (nullptr),
                      "MbDFEM",
                      App::Prop_Hidden,
                      "Tree folder containing this assembly's FEM actions");
    _actionsFolder.setScope(App::LinkScope::Hidden);
}

App::DocumentObjectGroup* MbDFEM::FEMAssembly::getPartsFolder() const
{
    return dynamic_cast<App::DocumentObjectGroup*>(_partsFolder.getValue());
}

App::DocumentObjectGroup* MbDFEM::FEMAssembly::getJointsFolder() const
{
    return dynamic_cast<App::DocumentObjectGroup*>(_jointsFolder.getValue());
}

App::DocumentObjectGroup* MbDFEM::FEMAssembly::getMotionsFolder() const
{
    return dynamic_cast<App::DocumentObjectGroup*>(_motionsFolder.getValue());
}

App::DocumentObjectGroup* MbDFEM::FEMAssembly::getActionsFolder() const
{
    return dynamic_cast<App::DocumentObjectGroup*>(_actionsFolder.getValue());
}

std::vector<App::DocumentObjectGroup*> MbDFEM::FEMAssembly::getCategoryFolders() const
{
    std::vector<App::DocumentObjectGroup*> folders;
    for (auto* folder : {getPartsFolder(), getJointsFolder(), getMotionsFolder(), getActionsFolder()}) {
        if (folder) {
            folders.push_back(folder);
        }
    }
    return folders;
}

std::vector<App::DocumentObject*> MbDFEM::FEMAssembly::getCategoryChildren() const
{
    std::vector<App::DocumentObject*> children;
    for (const auto& category : femAssemblyCategories) {
        const auto values = (this->*(category.children)).getValues();
        children.insert(children.end(), values.begin(), values.end());
    }
    return children;
}

App::DocumentObjectGroup* MbDFEM::FEMAssembly::ensurePartsFolder()
{
    if (auto* folder = getPartsFolder()) {
        return folder;
    }
    if (!getDocument()) {
        return nullptr;
    }

    const std::string name = std::string(getNameInDocument()) + "_Parts";
    auto* folder = static_cast<App::DocumentObjectGroup*>(
        getDocument()->addObject("MbDFEM::FEMPartsFolder", name.c_str()));
    folder->Label.setValue("Parts");
    _partsFolder.setValue(folder);
    addToAssemblyGroup(this, folder);
    return folder;
}

App::DocumentObjectGroup* MbDFEM::FEMAssembly::ensureJointsFolder()
{
    if (auto* folder = getJointsFolder()) {
        return folder;
    }
    if (!getDocument()) {
        return nullptr;
    }

    const std::string name = std::string(getNameInDocument()) + "_Joints";
    auto* folder = static_cast<App::DocumentObjectGroup*>(
        getDocument()->addObject("MbDFEM::FEMJointsFolder", name.c_str()));
    folder->Label.setValue("Joints");
    _jointsFolder.setValue(folder);
    addToAssemblyGroup(this, folder);
    return folder;
}

App::DocumentObjectGroup* MbDFEM::FEMAssembly::ensureMotionsFolder()
{
    if (auto* folder = getMotionsFolder()) {
        return folder;
    }
    if (!getDocument()) {
        return nullptr;
    }

    const std::string name = std::string(getNameInDocument()) + "_Motions";
    auto* folder = static_cast<App::DocumentObjectGroup*>(
        getDocument()->addObject("MbDFEM::FEMMotionsFolder", name.c_str()));
    folder->Label.setValue("Motions");
    _motionsFolder.setValue(folder);
    addToAssemblyGroup(this, folder);
    return folder;
}

App::DocumentObjectGroup* MbDFEM::FEMAssembly::ensureActionsFolder()
{
    if (auto* folder = getActionsFolder()) {
        return folder;
    }
    if (!getDocument()) {
        return nullptr;
    }

    const std::string name = std::string(getNameInDocument()) + "_Actions";
    auto* folder = static_cast<App::DocumentObjectGroup*>(
        getDocument()->addObject("MbDFEM::FEMActionsFolder", name.c_str()));
    folder->Label.setValue("Actions");
    _actionsFolder.setValue(folder);
    addToAssemblyGroup(this, folder);
    return folder;
}

void MbDFEM::FEMAssembly::ensureCategoryFolders()
{
    ensurePartsFolder();
    ensureJointsFolder();
    ensureMotionsFolder();
    ensureActionsFolder();
}

App::DocumentObjectExecReturn* MbDFEM::FEMAssembly::execute()
{
    if (auto* sourceAssembly = freecad_cast<MbDFEM::MbDAssembly*>(mbdItem.getValue())) {
        const auto sourcePlacement = sourceAssembly->Placement.getValue();
        if (!Placement.getValue().isSame(sourcePlacement, 1.0e-7)) {
            Placement.setValue(sourcePlacement);
        }
    }

    return App::Part::execute();
}

int MbDFEM::FEMAssembly::setElementVisible(const char* element, bool visible)
{
    auto* child = findDirectChildByInternalName(element, this);
    if (!child) {
        return App::Part::setElementVisible(element, visible);
    }

    child->Visibility.setValue(visible);
    return visible ? 1 : 0;
}

int MbDFEM::FEMAssembly::isElementVisible(const char* element) const
{
    if (!Visibility.getValue()) {
        return 0;
    }

    auto* child = findDirectChildByInternalName(element, this);
    if (!child) {
        return App::Part::isElementVisible(element);
    }

    return child->Visibility.getValue() ? 1 : 0;
}

App::DocumentObject* MbDFEM::FEMAssembly::getSubObject(const char* subname,
                                                       PyObject** pyObj,
                                                       Base::Matrix4D* mat,
                                                       bool transform,
                                                       int depth) const
{
    const char* rest = nullptr;
    auto* folder = matchingFolder(subname, rest, this);
    if (folder) {
        if (!rest || *rest == '\0') {
            return folder;
        }
        return App::Part::getSubObject(rest, pyObj, mat, transform, depth);
    }

    auto* child = matchingDirectChild(subname, rest, this);
    if (child) {
        if (!rest || *rest == '\0') {
            return child;
        }
        return child->getSubObject(rest, pyObj, mat, transform, depth + 1);
    }

    return App::Part::getSubObject(subname, pyObj, mat, transform, depth);
}
