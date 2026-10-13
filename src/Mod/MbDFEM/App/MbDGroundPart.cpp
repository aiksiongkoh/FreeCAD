// SPDX-License-Identifier: LGPL-2.1-or-later

#include "MbDGroundPart.h"

#include <algorithm>
#include <memory>
#include <string>
#include <vector>

#include <App/Document.h>
#include <Base/Exception.h>

#include "MbDAssembly.h"

PROPERTY_SOURCE(MbDFEM::MbDGroundPart, MbDFEM::MbDPart)

MbDFEM::MbDGroundPart::MbDGroundPart()
{
    ADD_PROPERTY_TYPE(
        groundFaces,
        (nullptr),
        "MbDFEM",
        App::Prop_None,
        "Ground faces associated with this part"
    );
    // Self face references describe geometry; they must not create a dependency
    // from this object back to itself. The property remains visible in the editor.
    groundFaces.setScope(App::LinkScope::Hidden);
}

MbDFEM::MbDGroundPart* MbDFEM::MbDGroundPart::convert(MbDPart* part)
{
    auto* document = part ? part->getDocument() : nullptr;
    if (!document) {
        throw Base::ValueError("Ground Faces requires a part in a document");
    }
    MbDAssembly* assembly = nullptr;
    for (auto* object : document->getObjects()) {
        auto* candidate = freecad_cast<MbDAssembly*>(object);
        if (!candidate) {
            continue;
        }
        const auto contains = [part](const App::PropertyLinkList& list) {
            const auto& values = list.getValues();
            return std::find(values.begin(), values.end(), part) != values.end();
        };
        if (contains(candidate->parts) || contains(candidate->fixedparts)) {
            if (assembly) {
                throw Base::ValueError("Ground Faces requires a part belonging to one MbDAssembly");
            }
            assembly = candidate;
        }
    }
    if (!assembly) {
        throw Base::ValueError("The selected MbDPart must belong to an MbDAssembly");
    }
    if (auto* ground = freecad_cast<MbDGroundPart*>(part)) {
        assembly->groundPart(ground);
        return ground;
    }

    // Snapshot before changing child ownership. Removing an MbDPart normally
    // removes its markers, mass marker, markers folder, and origin as well.
    std::vector<std::pair<App::Property*, std::unique_ptr<App::Property>>> saved;
    std::vector<App::Property*> properties;
    part->getPropertyList(properties);
    for (auto* property : properties) {
        saved.emplace_back(property, property->Copy());
    }
    const std::string name = std::string(part->getNameInDocument()) + "_Ground";
    const std::string label = part->Label.getValue();
    auto* ground = document->addObject<MbDGroundPart>(name.c_str());
    auto* unusedOrigin = ground->Origin.getValue();
    part->markers.setValues({});
    part->massMarker.setValue(nullptr);
    static_cast<App::PropertyLink*>(part->getPropertyByName("_markersFolder"))->setValue(nullptr);
    part->Origin.setValue(nullptr);
    part->Group.setValues({});

    // Shape is copied last so its change handler sees the transferred mass marker.
    for (const auto& [source, value] : saved) {
        if (source == &part->Shape) {
            continue;
        }
        const char* propertyName = part->getPropertyName(source);
        auto* target = ground->getPropertyByName(propertyName);
        if (!target && source->testStatus(App::Property::PropDynamic)) {
            target = ground->addDynamicProperty(
                source->getTypeId().getName(),
                propertyName,
                part->getPropertyGroup(source),
                part->getPropertyDocumentation(source),
                part->getPropertyType(source)
            );
        }
        if (target && target->getTypeId() == source->getTypeId()) {
            target->Paste(*value);
        }
    }
    for (const auto& [source, value] : saved) {
        if (source == &part->Shape) {
            ground->Shape.Paste(*value);
        }
    }
    if (unusedOrigin && unusedOrigin != ground->Origin.getValue()) {
        document->removeObject(unusedOrigin);
    }

    // FreeCAD's replacement API also updates subelement links and expressions.
    const auto objects = document->getObjects();
    for (auto* object : objects) {
        if (object == part) {
            continue;
        }
        properties.clear();
        object->getPropertyList(properties);
        for (auto* property : properties) {
            auto* link = dynamic_cast<App::PropertyLinkBase*>(property);
            if (!link) {
                continue;
            }
            std::unique_ptr<App::Property> replacement(link->CopyOnLinkReplace(object, part, ground));
            if (replacement) {
                property->Paste(*replacement);
            }
        }
    }
    assembly->groundPart(ground);
    document->removeObject(part);
    ground->Label.setValue(label);
    return ground;
}
