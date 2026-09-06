// SPDX-License-Identifier: LGPL-2.1-or-later

#include "FEMPart.h"

#include <algorithm>
#include <array>
#include <cstring>
#include <optional>
#include <sstream>
#include <string>
#include <vector>

#include <App/Document.h>
#include <App/GeoFeature.h>
#include <App/GeoFeatureGroupExtension.h>
#include <Base/Exception.h>
#include <Base/Tools.h>
#include <App/PropertyStandard.h>
#include <Mod/Fem/App/FemMeshObject.h>

#include "FEMAssembly.h"
#include "FEMMeshUtils.h"
#include "FEMPartPy.h"
#include "MbDAssembly.h"
#include "MbDFolders.h"
#include "MbDPart.h"

PROPERTY_SOURCE_WITH_EXTENSIONS(MbDFEM::FEMPart, Part::Feature)

namespace
{

App::DocumentObject* findDirectChildByInternalName(const char* element,
                                                   const MbDFEM::FEMPart* part)
{
    if (!element || !*element || !part) {
        return nullptr;
    }

    std::string name(element);
    if (!name.empty() && name.back() == '.') {
        name.pop_back();
    }

    const std::array<App::DocumentObject*, 3> linkedChildren = {{
        part->mesh.getValue(),
        part->solver.getValue(),
        part->visual.getValue(),
    }};
    for (auto* child : linkedChildren) {
        if (child && name == child->getNameInDocument()) {
            return child;
        }
    }
    for (auto* child : part->results.getValues()) {
        if (child && name == child->getNameInDocument()) {
            return child;
        }
    }
    return nullptr;
}

App::DocumentObject* matchingDirectChild(const char* subname,
                                         const char*& rest,
                                         const MbDFEM::FEMPart* part)
{
    rest = nullptr;
    const char* dot = subname ? std::strchr(subname, '.') : nullptr;
    if (!dot) {
        return findDirectChildByInternalName(subname, part);
    }

    const std::string segment(subname, dot);
    auto* child = findDirectChildByInternalName(segment.c_str(), part);
    if (child) {
        rest = dot + 1;
    }
    return child;
}

App::DocumentObjectGroup* matchingFolder(const char* subname,
                                         const char*& rest,
                                         App::DocumentObjectGroup* folder)
{
    rest = nullptr;
    const char* dot = subname ? std::strchr(subname, '.') : nullptr;
    if (!dot || !folder) {
        return nullptr;
    }

    const std::string segment(subname, dot);
    if (segment == folder->getNameInDocument()) {
        rest = dot + 1;
        return folder;
    }
    return nullptr;
}

bool parentAssemblyVisible(const App::DocumentObject* object)
{
    auto* group = object ? App::GeoFeatureGroupExtension::getGroupOfObject(object) : nullptr;
    auto* assembly = freecad_cast<MbDFEM::FEMAssembly*>(group);
    return !assembly || assembly->Visibility.getValue();
}

const MbDFEM::MbDAssembly* owningAssembly(const MbDFEM::MbDPart* part)
{
    if (!part || !part->getDocument()) {
        return nullptr;
    }

    for (auto* object :
         part->getDocument()->getObjectsOfType(MbDFEM::MbDAssembly::getClassTypeId())) {
        auto* assembly = freecad_cast<MbDFEM::MbDAssembly*>(object);
        if (!assembly) {
            continue;
        }

        const auto parts = assembly->parts.getValues();
        const auto fixedParts = assembly->fixedparts.getValues();
        if (std::find(parts.begin(), parts.end(), part) != parts.end()
            || std::find(fixedParts.begin(), fixedParts.end(), part) != fixedParts.end()) {
            return assembly;
        }
    }

    return nullptr;
}

std::optional<int> resultStateIndex(const App::DocumentObject* result)
{
    if (!result) {
        return std::nullopt;
    }

    auto* property = freecad_cast<App::PropertyInteger*>(
        result->getPropertyByName("MbDFEMStateIndex"));
    if (!property) {
        return std::nullopt;
    }

    return static_cast<int>(property->getValue());
}

void requireMatchingCount(const char* seriesName,
                          std::size_t seriesCount,
                          std::size_t resultCount,
                          std::vector<std::string>& mismatches)
{
    if (seriesCount == 0 || seriesCount == resultCount) {
        return;
    }

    std::ostringstream message;
    message << seriesName << " has " << seriesCount << " values; FEMPart.results has "
            << resultCount;
    mismatches.push_back(message.str());
}

void validatePartStateSeries(const MbDFEM::MbDPart* part,
                             std::size_t resultCount,
                             std::vector<std::string>& mismatches)
{
    if (!part) {
        return;
    }

    requireMatchingCount("MbDPart.xs", part->xs.getValues().size(), resultCount, mismatches);
    requireMatchingCount("MbDPart.ys", part->ys.getValues().size(), resultCount, mismatches);
    requireMatchingCount("MbDPart.zs", part->zs.getValues().size(), resultCount, mismatches);
    requireMatchingCount("MbDPart.bryxs", part->bryxs.getValues().size(), resultCount, mismatches);
    requireMatchingCount("MbDPart.bryys", part->bryys.getValues().size(), resultCount, mismatches);
    requireMatchingCount("MbDPart.bryzs", part->bryzs.getValues().size(), resultCount, mismatches);
    requireMatchingCount("MbDPart.vxs", part->vxs.getValues().size(), resultCount, mismatches);
    requireMatchingCount("MbDPart.vys", part->vys.getValues().size(), resultCount, mismatches);
    requireMatchingCount("MbDPart.vzs", part->vzs.getValues().size(), resultCount, mismatches);
    requireMatchingCount("MbDPart.omexs", part->omexs.getValues().size(), resultCount, mismatches);
    requireMatchingCount("MbDPart.omeys", part->omeys.getValues().size(), resultCount, mismatches);
    requireMatchingCount("MbDPart.omezs", part->omezs.getValues().size(), resultCount, mismatches);
    requireMatchingCount("MbDPart.axs", part->axs.getValues().size(), resultCount, mismatches);
    requireMatchingCount("MbDPart.ays", part->ays.getValues().size(), resultCount, mismatches);
    requireMatchingCount("MbDPart.azs", part->azs.getValues().size(), resultCount, mismatches);
    requireMatchingCount("MbDPart.alpxs", part->alpxs.getValues().size(), resultCount, mismatches);
    requireMatchingCount("MbDPart.alpys", part->alpys.getValues().size(), resultCount, mismatches);
    requireMatchingCount("MbDPart.alpzs", part->alpzs.getValues().size(), resultCount, mismatches);
}

}  // namespace

MbDFEM::FEMPart::FEMPart()
{
    ADD_PROPERTY_TYPE(mbdItem,
                      (nullptr),
                      "MbDFEM",
                      App::Prop_None,
                      "Multibody part represented by this FEM part");
    mbdItem.setScope(App::LinkScope::Global);
    ADD_PROPERTY_TYPE(mesh,
                      (nullptr),
                      "MbDFEM",
                      App::Prop_None,
                      "FEM mesh generated from this part's MbDPart shape");
    mesh.setScope(App::LinkScope::Global);
    ADD_PROPERTY_TYPE(solver,
                      (nullptr),
                      "MbDFEM",
                      App::Prop_None,
                      "Calculix solver used for this FEM part");
    solver.setScope(App::LinkScope::Child);
    ADD_PROPERTY_TYPE(results,
                      (nullptr),
                      "MbDFEM",
                      App::Prop_None,
                      "FEM result objects for this FEM part's solved states");
    results.setScope(App::LinkScope::Child);
    ADD_PROPERTY_TYPE(visual,
                      (nullptr),
                      "MbDFEM",
                      App::Prop_None,
                      "FEM post-processing pipeline for this FEM part");
    visual.setScope(App::LinkScope::Child);
    ADD_PROPERTY_TYPE(_resultsFolder,
                      (nullptr),
                      "MbDFEM",
                      App::Prop_Hidden,
                      "Tree folder containing this FEM part's result series");
    _resultsFolder.setScope(App::LinkScope::Hidden);

    App::OriginGroupExtension::initExtension(this);
}

App::DocumentObjectExecReturn* MbDFEM::FEMPart::execute()
{
    if (auto* sourcePart = freecad_cast<MbDFEM::MbDPart*>(mbdItem.getValue())) {
        const auto sourcePlacement = sourcePart->Placement.getValue();
        if (!Placement.getValue().isSame(sourcePlacement, 1.0e-7)) {
            Placement.setValue(sourcePlacement);
        }
    }
    if (auto* meshObject = freecad_cast<App::GeoFeature*>(mesh.getValue())) {
        const Base::Placement identity;
        if (!meshObject->Placement.getValue().isSame(identity, 1.0e-7)) {
            meshObject->Placement.setValue(identity);
        }
    }

    return Part::Feature::execute();
}

Base::Vector3d MbDFEM::FEMPart::elementCentroidLocal(int elementId) const
{
    auto* meshObject = freecad_cast<Fem::FemMeshObject*>(mesh.getValue());
    if (!meshObject) {
        throw Base::ValueError("elementCentroidLocal requires FEMPart.mesh to link a FemMeshObject");
    }

    return MbDFEM::elementCentroidLocal(meshObject->FemMesh.getValue(), elementId);
}

Base::Vector3d MbDFEM::FEMPart::elementCentroidGlobal(int elementId) const
{
    const Base::Vector3d localCentroid = elementCentroidLocal(elementId);
    if (auto* sourcePart = freecad_cast<MbDFEM::MbDPart*>(mbdItem.getValue())) {
        return sourcePart->globalPositionOf(localCentroid);
    }

    Base::Vector3d globalCentroid;
    globalPlacement().multVec(localCentroid, globalCentroid);
    return globalCentroid;
}

int MbDFEM::FEMPart::setElementVisible(const char* element, bool visible)
{
    auto* child = findDirectChildByInternalName(element, this);
    if (!child) {
        return Part::Feature::setElementVisible(element, visible);
    }

    child->Visibility.setValue(visible);
    return visible ? 1 : 0;
}

int MbDFEM::FEMPart::isElementVisible(const char* element) const
{
    if (!Visibility.getValue() || !parentAssemblyVisible(this)) {
        return 0;
    }

    auto* child = findDirectChildByInternalName(element, this);
    if (!child) {
        return Part::Feature::isElementVisible(element);
    }

    return child->Visibility.getValue() ? 1 : 0;
}

App::DocumentObject* MbDFEM::FEMPart::resultForState(int stateIndex) const
{
    const auto resultValues = results.getValues();
    for (auto* result : resultValues) {
        const auto taggedIndex = resultStateIndex(result);
        if (taggedIndex && *taggedIndex == stateIndex) {
            return result;
        }
    }

    if (stateIndex < 0 || stateIndex >= static_cast<int>(resultValues.size())) {
        throw Base::IndexError("FEMPart result state index not in range");
    }

    validateResultSeries();
    return resultValues[static_cast<std::size_t>(stateIndex)];
}

void MbDFEM::FEMPart::validateResultSeries() const
{
    const auto resultValues = results.getValues();
    const auto resultCount = resultValues.size();
    const bool sparseIndexedResults =
        std::any_of(resultValues.begin(), resultValues.end(), [](const App::DocumentObject* result) {
            return resultStateIndex(result).has_value();
        });
    std::vector<std::string> mismatches;

    auto* part = freecad_cast<MbDFEM::MbDPart*>(mbdItem.getValue());
    const auto* assembly = owningAssembly(part);
    if (sparseIndexedResults) {
        auto maxStateCount = std::size_t {0};
        if (assembly) {
            maxStateCount = std::max(maxStateCount, assembly->times.getValues().size());
        }
        if (part) {
            maxStateCount = std::max(maxStateCount, part->xs.getValues().size());
            maxStateCount = std::max(maxStateCount, part->ys.getValues().size());
            maxStateCount = std::max(maxStateCount, part->zs.getValues().size());
        }
        for (auto* result : resultValues) {
            const auto taggedIndex = resultStateIndex(result);
            if (!taggedIndex) {
                continue;
            }
            if (*taggedIndex < 0
                || (maxStateCount > 0 && static_cast<std::size_t>(*taggedIndex) >= maxStateCount)) {
                std::ostringstream message;
                message << result->getNameInDocument() << " has MbDFEMStateIndex "
                        << *taggedIndex << " outside the MbD state range";
                mismatches.push_back(message.str());
            }
        }
    }
    else {
        validatePartStateSeries(part, resultCount, mismatches);
    }

    if (assembly && !sparseIndexedResults) {
        requireMatchingCount("MbDAssembly.times",
                             assembly->times.getValues().size(),
                             resultCount,
                             mismatches);
    }

    if (!mismatches.empty()) {
        std::ostringstream message;
        message << "FEMPart.results must correspond one-to-one with MbD states: ";
        for (std::size_t index = 0; index < mismatches.size(); ++index) {
            if (index > 0) {
                message << "; ";
            }
            message << mismatches[index];
        }
        throw Base::ValueError(message.str());
    }
}

App::DocumentObject* MbDFEM::FEMPart::getSubObject(const char* subname,
                                                   PyObject** pyObj,
                                                   Base::Matrix4D* mat,
                                                   bool transform,
                                                   int depth) const
{
    const char* rest = nullptr;
    auto* folder = matchingFolder(subname, rest, getResultsFolder());
    if (folder) {
        if (!rest || *rest == '\0') {
            return folder;
        }
        return Part::Feature::getSubObject(rest, pyObj, mat, transform, depth);
    }

    auto* child = matchingDirectChild(subname, rest, this);
    if (child) {
        if (!rest || *rest == '\0') {
            return child;
        }
        return child->getSubObject(rest, pyObj, mat, transform, depth + 1);
    }

    return Part::Feature::getSubObject(subname, pyObj, mat, transform, depth);
}

App::DocumentObjectGroup* MbDFEM::FEMPart::getResultsFolder() const
{
    return dynamic_cast<App::DocumentObjectGroup*>(_resultsFolder.getValue());
}

App::DocumentObjectGroup* MbDFEM::FEMPart::ensureResultsFolder()
{
    if (auto* folder = getResultsFolder()) {
        return folder;
    }
    if (!getDocument()) {
        return nullptr;
    }

    const std::string name = std::string(getNameInDocument()) + "_Results";
    auto* folder = static_cast<App::DocumentObjectGroup*>(
        getDocument()->addObject("MbDFEM::FEMResultsFolder", name.c_str()));
    folder->Label.setValue("Results");
    _resultsFolder.setValue(folder);
    addObject(folder);
    return folder;
}

void MbDFEM::FEMPart::synchronizeResultsFolder()
{
    auto* folder = ensureResultsFolder();
    if (!folder) {
        return;
    }

    folder->Group.setScope(App::LinkScope::Child);
    Base::ObjectStatusLocker<App::Property::Status, App::Property> guard(App::Property::User3,
                                                                         &folder->Group);
    folder->Group.setValues(results.getValues());
    if (!hasObject(folder)) {
        addObject(folder);
    }
}

void MbDFEM::FEMPart::onChanged(const App::Property* prop)
{
    Part::Feature::onChanged(prop);

    if (prop == &results && !results.testStatus(App::Property::User3)) {
        synchronizeResultsFolder();
    }
}

void MbDFEM::FEMPart::onDocumentRestored()
{
    Part::Feature::onDocumentRestored();
    synchronizeResultsFolder();
}

void MbDFEM::FEMPart::unsetupObject()
{
    auto* document = getDocument();
    if (document) {
        if (auto* folder = getResultsFolder()) {
            if (folder->isAttachedToDocument() && !folder->isRemoving()) {
                document->removeObject(folder->getNameInDocument());
            }
        }
    }

    Part::Feature::unsetupObject();
}

PyObject* MbDFEM::FEMPart::getPyObject()
{
    if (PythonObject.is(Py::_None())) {
        PythonObject = Py::Object(new FEMPartPy(this), true);
    }
    return Py::new_reference_to(PythonObject);
}
