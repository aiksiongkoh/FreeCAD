// SPDX-License-Identifier: LGPL-2.1-or-later

#pragma once

#include <App/OriginGroupExtension.h>
#include <App/PropertyLinks.h>
#include <Mod/MbDFEM/MbDFEMGlobal.h>
#include <Mod/Part/App/PartFeature.h>

namespace MbDFEM
{

class MbDFEMExport FEMPart: public Part::Feature, public App::OriginGroupExtension
{
    PROPERTY_HEADER_WITH_EXTENSIONS(MbDFEM::FEMPart);

public:
    FEMPart();
    ~FEMPart() override = default;
    App::PropertyLink mbdItem;
    App::PropertyLink material;
    App::PropertyLink mesh;
    App::PropertyLink solver;

    App::DocumentObjectExecReturn* execute() override;
    App::DocumentObject* getSubObject(const char* subname,
                                      PyObject** pyObj = nullptr,
                                      Base::Matrix4D* mat = nullptr,
                                      bool transform = true,
                                      int depth = 0) const override;

    const char* getViewProviderName() const override
    {
        return "MbDFEMGui::ViewProviderFEMPart";
    }
};

}  // namespace MbDFEM
