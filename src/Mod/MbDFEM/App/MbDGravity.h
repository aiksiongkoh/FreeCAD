// SPDX-License-Identifier: LGPL-2.1-or-later

#pragma once

#include <App/DocumentObject.h>
#include <App/PropertyGeo.h>
#include <Mod/MbDFEM/MbDFEMGlobal.h>

namespace MbDFEM
{

class MbDFEMExport MbDGravity: public App::DocumentObject
{
    PROPERTY_HEADER_WITH_OVERRIDE(MbDFEM::MbDGravity);

public:
    MbDGravity();
    ~MbDGravity() override = default;

    App::PropertyVector gravity;  // mm/s^2

    const char* getViewProviderName() const override
    {
        return "MbDFEMGui::ViewProviderMbDGravity";
    }
};

}  // namespace MbDFEM
