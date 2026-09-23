// SPDX-License-Identifier: LGPL-2.1-or-later

#include "MbDSimulationParameters.h"

PROPERTY_SOURCE(MbDFEM::MbDSimulationParameters, App::DocumentObject)

MbDFEM::MbDSimulationParameters::MbDSimulationParameters()
{
    ADD_PROPERTY_TYPE(startTime, (0.0), "MbDFEM", App::Prop_None, "Simulation start time");
    ADD_PROPERTY_TYPE(endTime, (1.0), "MbDFEM", App::Prop_None, "Simulation end time");
    ADD_PROPERTY_TYPE(outputInterval, (0.01), "MbDFEM", App::Prop_None, "Simulation output interval");
    ADD_PROPERTY_TYPE(minStepSize,
                      (1.0e-09),
                      "MbDFEM",
                      App::Prop_None,
                      "Minimum simulation integration step size");
    ADD_PROPERTY_TYPE(maxStepSize,
                      (1.0),
                      "MbDFEM",
                      App::Prop_None,
                      "Maximum simulation integration step size");
    ADD_PROPERTY_TYPE(significantDigits,
                      (4),
                      "MbDFEM",
                      App::Prop_None,
                      "Number of significant digits used for simulation accuracy");
    ADD_PROPERTY_TYPE(maxIterations, (100), "MbDFEM", App::Prop_None, "Maximum solver iterations");
}
