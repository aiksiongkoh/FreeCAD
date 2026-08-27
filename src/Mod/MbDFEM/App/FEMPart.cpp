// SPDX-License-Identifier: LGPL-2.1-or-later

#include "FEMPart.h"

#include <array>
#include <cstring>
#include <string>

#include <App/GeoFeature.h>

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

    const std::array<App::DocumentObject*, 3> children = {{
        part->material.getValue(),
        part->mesh.getValue(),
        part->solver.getValue(),
    }};
    for (auto* child : children) {
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

}  // namespace

MbDFEM::FEMPart::FEMPart()
{
    ADD_PROPERTY_TYPE(mbdItem,
                      (nullptr),
                      "MbDFEM",
                      App::Prop_None,
                      "Multibody part represented by this FEM part");
    mbdItem.setScope(App::LinkScope::Global);
    ADD_PROPERTY_TYPE(material,
                      (nullptr),
                      "MbDFEM",
                      App::Prop_None,
                      "FEM material copied from this part's MbDMassMarker material");
    material.setScope(App::LinkScope::Child);
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

App::DocumentObject* MbDFEM::FEMPart::getSubObject(const char* subname,
                                                   PyObject** pyObj,
                                                   Base::Matrix4D* mat,
                                                   bool transform,
                                                   int depth) const
{
    const char* rest = nullptr;
    auto* child = matchingDirectChild(subname, rest, this);
    if (child) {
        if (!rest || *rest == '\0') {
            return child;
        }
        return child->getSubObject(rest, pyObj, mat, transform, depth + 1);
    }

    return Part::Feature::getSubObject(subname, pyObj, mat, transform, depth);
}
