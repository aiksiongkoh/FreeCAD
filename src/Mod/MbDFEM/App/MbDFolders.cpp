// SPDX-License-Identifier: LGPL-2.1-or-later

#include "MbDFolders.h"

#include <algorithm>

#include <App/Document.h>
#include <App/GroupExtension.h>

#include "MbDAction.h"
#include "MbDAssembly.h"
#include "MbDGroupUtils.h"
#include "MbDJoint.h"
#include "MbDMarker.h"
#include "MbDMotion.h"
#include "MbDPart.h"
#include "FEMAction.h"
#include "FEMAssembly.h"
#include "FEMJoint.h"
#include "FEMPart.h"

PROPERTY_SOURCE(MbDFEM::MbDAssembliesFolder, App::DocumentObjectGroup)
PROPERTY_SOURCE(MbDFEM::MbDPartsFolder, App::DocumentObjectGroup)
PROPERTY_SOURCE(MbDFEM::MbDFixedPartsFolder, App::DocumentObjectGroup)
PROPERTY_SOURCE(MbDFEM::MbDMarkersFolder, App::DocumentObjectGroup)
PROPERTY_SOURCE(MbDFEM::MbDJointsFolder, App::DocumentObjectGroup)
PROPERTY_SOURCE(MbDFEM::MbDMotionsFolder, App::DocumentObjectGroup)
PROPERTY_SOURCE(MbDFEM::MbDActionsFolder, App::DocumentObjectGroup)
PROPERTY_SOURCE(MbDFEM::FEMPartsFolder, App::DocumentObjectGroup)
PROPERTY_SOURCE(MbDFEM::FEMJointsFolder, App::DocumentObjectGroup)
PROPERTY_SOURCE(MbDFEM::FEMMotionsFolder, App::DocumentObjectGroup)
PROPERTY_SOURCE(MbDFEM::FEMActionsFolder, App::DocumentObjectGroup)

namespace
{

bool omitFolderFromSubName(std::ostringstream&,
                           App::DocumentObject* topParent,
                           App::DocumentObject* child)
{
    return topParent && child;
}

MbDFEM::MbDAssembly* owningAssembly(App::DocumentObjectGroup* folder)
{
    if (!folder) {
        return nullptr;
    }

    auto* document = folder->getDocument();
    if (!document) {
        return nullptr;
    }

    for (auto* assembly : document->getObjectsOfType<MbDFEM::MbDAssembly>()) {
        if (assembly->getPartsFolder() == folder || assembly->getFixedPartsFolder() == folder) {
            return assembly;
        }
    }
    return nullptr;
}

MbDFEM::FEMAssembly* owningFEMAssembly(App::DocumentObjectGroup* folder)
{
    if (!folder) {
        return nullptr;
    }

    auto* document = folder->getDocument();
    if (!document) {
        return nullptr;
    }

    for (auto* assembly : document->getObjectsOfType<MbDFEM::FEMAssembly>()) {
        if (assembly->getPartsFolder() == folder || assembly->getJointsFolder() == folder
            || assembly->getMotionsFolder() == folder || assembly->getActionsFolder() == folder) {
            return assembly;
        }
    }
    return nullptr;
}

void synchronizeOwningAssembly(App::DocumentObjectGroup* folder, const App::Property* prop)
{
    if (!folder || prop != &folder->Group || folder->Group.testStatus(App::Property::User3)) {
        return;
    }
    if (auto* assembly = owningAssembly(folder)) {
        assembly->synchronizePartCategories();
    }
}

void addToGeoGroup(App::DocumentObject* owner, App::DocumentObject* child)
{
    if (!owner || !child) {
        return;
    }

    if (auto* group = owner->getExtensionByType<App::GroupExtension>()) {
        MbDFEM::appendUnique(group->Group, child);
    }
}

void removeFromGeoGroup(App::DocumentObject* owner, App::DocumentObject* child)
{
    if (!owner || !child) {
        return;
    }

    if (auto* group = owner->getExtensionByType<App::GroupExtension>()) {
        MbDFEM::removeAll(group->Group, child);
    }
}

template<typename FolderT, typename ChildT>
bool allowFEMObject(FolderT* folder, App::PropertyLinkList MbDFEM::FEMAssembly::*list, App::DocumentObject* object)
{
    if (!object || !object->isDerivedFrom<ChildT>()) {
        return false;
    }
    if (auto* assembly = owningFEMAssembly(folder)) {
        MbDFEM::appendUnique(assembly->*list, object);
    }
    return true;
}

template<typename FolderT>
std::vector<App::DocumentObject*> addFEMObject(FolderT* folder, App::DocumentObject* object)
{
    auto added = folder->App::GroupExtension::addObject(object);
    if (auto* assembly = owningFEMAssembly(folder)) {
        addToGeoGroup(assembly, object);
    }
    return added;
}

template<typename FolderT>
std::vector<App::DocumentObject*> removeFEMObject(FolderT* folder,
                                                  App::PropertyLinkList MbDFEM::FEMAssembly::*list,
                                                  App::DocumentObject* object)
{
    auto removed = folder->App::GroupExtension::removeObject(object);
    if (auto* assembly = owningFEMAssembly(folder)) {
        MbDFEM::removeAll(assembly->*list, object);
        removeFromGeoGroup(assembly, object);
    }
    return removed;
}

template<typename FolderT>
void synchronizeFEMFolder(FolderT* folder,
                          App::PropertyLinkList MbDFEM::FEMAssembly::*list,
                          const App::Property* prop)
{
    if (!folder || prop != &folder->Group || folder->Group.testStatus(App::Property::User3)) {
        return;
    }
    if (auto* assembly = owningFEMAssembly(folder)) {
        std::vector<App::DocumentObject*> objects;
        for (auto* object : folder->Group.getValues()) {
            if (object && std::find(objects.begin(), objects.end(), object) == objects.end()) {
                objects.push_back(object);
                addToGeoGroup(assembly, object);
            }
        }
        (assembly->*list).setValues(objects);
    }
}

}  // namespace

bool MbDFEM::MbDAssembliesFolder::allowObject(App::DocumentObject* object)
{
    return object && object->isDerivedFrom<MbDFEM::MbDAssembly>();
}

bool MbDFEM::MbDAssembliesFolder::redirectSubName(std::ostringstream& ss,
                                                  App::DocumentObject* topParent,
                                                  App::DocumentObject* child) const
{
    return omitFolderFromSubName(ss, topParent, child);
}

bool MbDFEM::MbDPartsFolder::allowObject(App::DocumentObject* object)
{
    if (!object || !object->isDerivedFrom<MbDFEM::MbDPart>()) {
        return false;
    }
    if (auto* assembly = owningAssembly(this)) {
        removeAll(assembly->fixedparts, object);
        appendUnique(assembly->parts, object);
    }
    return true;
}

std::vector<App::DocumentObject*> MbDFEM::MbDPartsFolder::addObject(App::DocumentObject* object)
{
    auto added = App::GroupExtension::addObject(object);
    if (auto* assembly = owningAssembly(this)) {
        assembly->synchronizePartCategories();
    }
    return added;
}

std::vector<App::DocumentObject*> MbDFEM::MbDPartsFolder::removeObject(App::DocumentObject* object)
{
    auto removed = App::GroupExtension::removeObject(object);
    if (auto* assembly = owningAssembly(this)) {
        assembly->synchronizePartCategories();
    }
    return removed;
}

bool MbDFEM::MbDPartsFolder::redirectSubName(std::ostringstream& ss,
                                             App::DocumentObject* topParent,
                                             App::DocumentObject* child) const
{
    return omitFolderFromSubName(ss, topParent, child);
}

void MbDFEM::MbDPartsFolder::onChanged(const App::Property* prop)
{
    App::DocumentObjectGroup::onChanged(prop);
    synchronizeOwningAssembly(this, prop);
}

bool MbDFEM::MbDFixedPartsFolder::allowObject(App::DocumentObject* object)
{
    if (!object || !object->isDerivedFrom<MbDFEM::MbDPart>()) {
        return false;
    }
    if (auto* assembly = owningAssembly(this)) {
        removeAll(assembly->parts, object);
        appendUnique(assembly->fixedparts, object);
    }
    return true;
}

std::vector<App::DocumentObject*> MbDFEM::MbDFixedPartsFolder::addObject(
    App::DocumentObject* object)
{
    auto added = App::GroupExtension::addObject(object);
    if (auto* assembly = owningAssembly(this)) {
        assembly->synchronizePartCategories();
    }
    return added;
}

std::vector<App::DocumentObject*> MbDFEM::MbDFixedPartsFolder::removeObject(
    App::DocumentObject* object)
{
    auto removed = App::GroupExtension::removeObject(object);
    if (auto* assembly = owningAssembly(this)) {
        assembly->synchronizePartCategories();
    }
    return removed;
}

bool MbDFEM::MbDFixedPartsFolder::redirectSubName(std::ostringstream& ss,
                                                  App::DocumentObject* topParent,
                                                  App::DocumentObject* child) const
{
    return omitFolderFromSubName(ss, topParent, child);
}

void MbDFEM::MbDFixedPartsFolder::onChanged(const App::Property* prop)
{
    App::DocumentObjectGroup::onChanged(prop);
    synchronizeOwningAssembly(this, prop);
}

bool MbDFEM::MbDMarkersFolder::allowObject(App::DocumentObject* object)
{
    return object && object->isDerivedFrom<MbDFEM::MbDMarker>();
}

bool MbDFEM::MbDMarkersFolder::redirectSubName(std::ostringstream& ss,
                                               App::DocumentObject* topParent,
                                               App::DocumentObject* child) const
{
    return omitFolderFromSubName(ss, topParent, child);
}

bool MbDFEM::MbDJointsFolder::allowObject(App::DocumentObject* object)
{
    return object && object->isDerivedFrom<MbDFEM::MbDJoint>();
}

bool MbDFEM::MbDJointsFolder::redirectSubName(std::ostringstream& ss,
                                              App::DocumentObject* topParent,
                                              App::DocumentObject* child) const
{
    return omitFolderFromSubName(ss, topParent, child);
}

bool MbDFEM::MbDMotionsFolder::allowObject(App::DocumentObject* object)
{
    return object && object->isDerivedFrom<MbDFEM::MbDMotion>();
}

bool MbDFEM::MbDMotionsFolder::redirectSubName(std::ostringstream& ss,
                                               App::DocumentObject* topParent,
                                               App::DocumentObject* child) const
{
    return omitFolderFromSubName(ss, topParent, child);
}

bool MbDFEM::MbDActionsFolder::allowObject(App::DocumentObject* object)
{
    return object && object->isDerivedFrom<MbDFEM::MbDAction>();
}

bool MbDFEM::MbDActionsFolder::redirectSubName(std::ostringstream& ss,
                                               App::DocumentObject* topParent,
                                               App::DocumentObject* child) const
{
    return omitFolderFromSubName(ss, topParent, child);
}

bool MbDFEM::FEMPartsFolder::allowObject(App::DocumentObject* object)
{
    return allowFEMObject<FEMPartsFolder, MbDFEM::FEMPart>(this, &FEMAssembly::parts, object);
}

std::vector<App::DocumentObject*> MbDFEM::FEMPartsFolder::addObject(App::DocumentObject* object)
{
    return addFEMObject(this, object);
}

std::vector<App::DocumentObject*> MbDFEM::FEMPartsFolder::removeObject(App::DocumentObject* object)
{
    return removeFEMObject(this, &FEMAssembly::parts, object);
}

bool MbDFEM::FEMPartsFolder::redirectSubName(std::ostringstream& ss,
                                             App::DocumentObject* topParent,
                                             App::DocumentObject* child) const
{
    return omitFolderFromSubName(ss, topParent, child);
}

void MbDFEM::FEMPartsFolder::onChanged(const App::Property* prop)
{
    App::DocumentObjectGroup::onChanged(prop);
    synchronizeFEMFolder(this, &FEMAssembly::parts, prop);
}

bool MbDFEM::FEMJointsFolder::allowObject(App::DocumentObject* object)
{
    return allowFEMObject<FEMJointsFolder, MbDFEM::FEMJoint>(this, &FEMAssembly::joints, object);
}

std::vector<App::DocumentObject*> MbDFEM::FEMJointsFolder::addObject(App::DocumentObject* object)
{
    return addFEMObject(this, object);
}

std::vector<App::DocumentObject*> MbDFEM::FEMJointsFolder::removeObject(App::DocumentObject* object)
{
    return removeFEMObject(this, &FEMAssembly::joints, object);
}

bool MbDFEM::FEMJointsFolder::redirectSubName(std::ostringstream& ss,
                                              App::DocumentObject* topParent,
                                              App::DocumentObject* child) const
{
    return omitFolderFromSubName(ss, topParent, child);
}

void MbDFEM::FEMJointsFolder::onChanged(const App::Property* prop)
{
    App::DocumentObjectGroup::onChanged(prop);
    synchronizeFEMFolder(this, &FEMAssembly::joints, prop);
}

bool MbDFEM::FEMMotionsFolder::allowObject(App::DocumentObject* object)
{
    return allowFEMObject<FEMMotionsFolder, MbDFEM::FEMItem>(this, &FEMAssembly::motions, object);
}

std::vector<App::DocumentObject*> MbDFEM::FEMMotionsFolder::addObject(App::DocumentObject* object)
{
    return addFEMObject(this, object);
}

std::vector<App::DocumentObject*> MbDFEM::FEMMotionsFolder::removeObject(App::DocumentObject* object)
{
    return removeFEMObject(this, &FEMAssembly::motions, object);
}

bool MbDFEM::FEMMotionsFolder::redirectSubName(std::ostringstream& ss,
                                               App::DocumentObject* topParent,
                                               App::DocumentObject* child) const
{
    return omitFolderFromSubName(ss, topParent, child);
}

void MbDFEM::FEMMotionsFolder::onChanged(const App::Property* prop)
{
    App::DocumentObjectGroup::onChanged(prop);
    synchronizeFEMFolder(this, &FEMAssembly::motions, prop);
}

bool MbDFEM::FEMActionsFolder::allowObject(App::DocumentObject* object)
{
    return allowFEMObject<FEMActionsFolder, MbDFEM::FEMAction>(this, &FEMAssembly::actions, object);
}

std::vector<App::DocumentObject*> MbDFEM::FEMActionsFolder::addObject(App::DocumentObject* object)
{
    return addFEMObject(this, object);
}

std::vector<App::DocumentObject*> MbDFEM::FEMActionsFolder::removeObject(App::DocumentObject* object)
{
    return removeFEMObject(this, &FEMAssembly::actions, object);
}

bool MbDFEM::FEMActionsFolder::redirectSubName(std::ostringstream& ss,
                                               App::DocumentObject* topParent,
                                               App::DocumentObject* child) const
{
    return omitFolderFromSubName(ss, topParent, child);
}

void MbDFEM::FEMActionsFolder::onChanged(const App::Property* prop)
{
    App::DocumentObjectGroup::onChanged(prop);
    synchronizeFEMFolder(this, &FEMAssembly::actions, prop);
}
