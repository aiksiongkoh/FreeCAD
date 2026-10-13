// SPDX-License-Identifier: LGPL-2.1-or-later

#include "FEMAnimationParameters.h"
#include <cstring>

PROPERTY_SOURCE(MbDFEM::FEMAnimationParameters, App::DocumentObject)

MbDFEM::FEMAnimationParameters::FEMAnimationParameters()
{
    ADD_PROPERTY_TYPE(
        selectedParts,
        (nullptr),
        "MbDFEM",
        App::Prop_None,
        "FEM bodies selected for synchronized result playback"
    );
    selectedParts.setScope(App::LinkScope::Global);
    ADD_PROPERTY_TYPE(currentFrame, (0), "MbDFEM", App::Prop_None, "Current FEM result state");
    ADD_PROPERTY_TYPE(startFrame, (1), "MbDFEM", App::Prop_None, "First FEM playback state");
    ADD_PROPERTY_TYPE(
        endFrame,
        (-1),
        "MbDFEM",
        App::Prop_None,
        "Last FEM playback state; -1 uses the last available state"
    );
    ADD_PROPERTY_TYPE(
        updateRate,
        (30),
        "MbDFEM",
        App::Prop_None,
        "Signed states per real second: negative reverses playback; zero pauses"
    );
    ADD_PROPERTY_TYPE(
        fieldName,
        ("von Mises Stress"),
        "MbDFEM",
        App::Prop_None,
        "FEM scalar field displayed during playback"
    );
    ADD_PROPERTY_TYPE(
        sharedColorScale,
        (true),
        "MbDFEM",
        App::Prop_None,
        "Use the same fixed color range for all selected bodies"
    );
    ADD_PROPERTY_TYPE(loop, (true), "MbDFEM", App::Prop_None, "Loop FEM result playback");
    ADD_PROPERTY_TYPE(
        settingsInitialized,
        (false),
        "MbDFEM",
        App::Prop_Hidden,
        "Distinguish initial defaults from an intentionally empty body selection"
    );
}

void MbDFEM::FEMAnimationParameters::handleChangedPropertyType(
    Base::XMLReader& reader,
    const char* typeName,
    App::Property* prop
)
{
    if (prop == &updateRate && std::strcmp(typeName, "App::PropertyInteger") == 0) {
        App::PropertyInteger oldRate;
        oldRate.Restore(reader);
        updateRate.setValue(oldRate.getValue());
    }
    else {
        App::DocumentObject::handleChangedPropertyType(reader, typeName, prop);
    }
}
