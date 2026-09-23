// SPDX-License-Identifier: LGPL-2.1-or-later

#include "MbDAnimationParameters.h"

PROPERTY_SOURCE(MbDFEM::MbDAnimationParameters, App::DocumentObject)

MbDFEM::MbDAnimationParameters::MbDAnimationParameters()
{
    ADD_PROPERTY_TYPE(updateRate,
                      (30),
                      "MbDFEM",
                      App::Prop_None,
                      "Simulation frames per real second during animation playback");
    ADD_PROPERTY_TYPE(currentFrame, (0), "MbDFEM", App::Prop_None, "Current result-series frame index");
    ADD_PROPERTY_TYPE(startFrame, (1), "MbDFEM", App::Prop_None, "First result-series frame index");
    ADD_PROPERTY_TYPE(endFrame, (-1), "MbDFEM", App::Prop_None, "Last result-series frame index");
    ADD_PROPERTY_TYPE(playbackSpeed,
                      (1.0),
                      "MbDFEM",
                      App::Prop_None,
                      "Computed simulation seconds per real second during animation playback");
    ADD_PROPERTY_TYPE(lengthScale,
                      (1.0),
                      "MbDFEM",
                      App::Prop_None,
                      "Scale factor applied to result translations during animation playback");
    ADD_PROPERTY_TYPE(showTrails, (false), "MbDFEM", App::Prop_None, "Show animation trails");
    ADD_PROPERTY_TYPE(trailLength, (60), "MbDFEM", App::Prop_None, "Number of trail frames to display");
    ADD_PROPERTY_TYPE(loop, (true), "MbDFEM", App::Prop_None, "Loop animation playback");
    ADD_PROPERTY_TYPE(interpolateFrames,
                      (true),
                      "MbDFEM",
                      App::Prop_None,
                      "Interpolate animation frames");
}
