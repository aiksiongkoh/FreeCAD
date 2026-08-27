// SPDX-License-Identifier: LGPL-2.1-or-later

#pragma once

#include <App/DocumentObject.h>
#include <Mod/MbDFEM/MbDFEMGlobal.h>

namespace MbDFEM
{

class MbDFEMExport FEMItem: public App::DocumentObject
{
    PROPERTY_HEADER_WITH_OVERRIDE(MbDFEM::FEMItem);

public:
    FEMItem();
    ~FEMItem() override = default;
    App::PropertyLink mbdItem;

    const char* getViewProviderName() const override
    {
        return "MbDFEMGui::ViewProviderFEMItem";
    }
};

}  // namespace MbDFEM
