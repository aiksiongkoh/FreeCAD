// SPDX-License-Identifier: LGPL-2.1-or-later

#pragma once

#include <App/DocumentObject.h>
#include <App/PropertyLinks.h>
#include <App/PropertyStandard.h>
#include <Mod/MbDFEM/MbDFEMGlobal.h>

namespace MbDFEM
{

class MbDFEMExport FEMAnimationParameters: public App::DocumentObject
{
    PROPERTY_HEADER_WITH_OVERRIDE(MbDFEM::FEMAnimationParameters);

public:
    FEMAnimationParameters();
    ~FEMAnimationParameters() override = default;

    App::PropertyLinkList selectedParts;
    App::PropertyInteger currentFrame;
    App::PropertyInteger startFrame;
    App::PropertyInteger endFrame;
    App::PropertyFloat updateRate;
    App::PropertyString fieldName;
    App::PropertyBool sharedColorScale;
    App::PropertyBool loop;
    App::PropertyBool settingsInitialized;
    void handleChangedPropertyType(
        Base::XMLReader& reader,
        const char* typeName,
        App::Property* prop
    ) override;

    const char* getViewProviderName() const override
    {
        return "MbDFEMGui::ViewProviderFEMAnimationParameters";
    }
};

}  // namespace MbDFEM
