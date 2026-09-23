// SPDX-License-Identifier: LGPL-2.1-or-later

#pragma once

#include <App/DocumentObject.h>
#include <App/PropertyStandard.h>
#include <Mod/MbDFEM/MbDFEMGlobal.h>

namespace MbDFEM
{

class MbDFEMExport MbDAnimationParameters: public App::DocumentObject
{
    PROPERTY_HEADER_WITH_OVERRIDE(MbDFEM::MbDAnimationParameters);

public:
    MbDAnimationParameters();
    ~MbDAnimationParameters() override = default;

    App::PropertyInteger updateRate;
    App::PropertyInteger currentFrame;
    App::PropertyInteger startFrame;
    App::PropertyInteger endFrame;
    App::PropertyFloat playbackSpeed;
    App::PropertyFloat lengthScale;
    App::PropertyBool showTrails;
    App::PropertyInteger trailLength;
    App::PropertyBool loop;
    App::PropertyBool interpolateFrames;

    const char* getViewProviderName() const override
    {
        return "MbDFEMGui::ViewProviderMbDAnimationParameters";
    }
};

}  // namespace MbDFEM
