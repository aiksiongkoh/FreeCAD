// SPDX-License-Identifier: LGPL-2.1-or-later

#include "FEMSimulationParameters.h"

PROPERTY_SOURCE(MbDFEM::FEMSimulationParameters, App::DocumentObject)

MbDFEM::FEMSimulationParameters::FEMSimulationParameters()
{
    ADD_PROPERTY_TYPE(
        selectedParts,
        (nullptr),
        "MbDFEM",
        App::Prop_None,
        "FEM parts selected for assembly CalculiX jobs"
    );
    selectedParts.setScope(App::LinkScope::Global);
    ADD_PROPERTY_TYPE(currentState, (0), "MbDFEM", App::Prop_None, "Current MbD state");
    ADD_PROPERTY_TYPE(startState, (1), "MbDFEM", App::Prop_None, "First state to process");
    ADD_PROPERTY_TYPE(
        endState,
        (-1),
        "MbDFEM",
        App::Prop_None,
        "Last state to process; -1 uses the last available state"
    );
    ADD_PROPERTY_TYPE(
        missingOnly,
        (true),
        "MbDFEM",
        App::Prop_None,
        "Skip imported results whose state time and source files are current"
    );
    ADD_PROPERTY_TYPE(
        continueOnError,
        (true),
        "MbDFEM",
        App::Prop_None,
        "Continue with remaining jobs when a part or state fails"
    );
    ADD_PROPERTY_TYPE(
        settingsInitialized,
        (false),
        "MbDFEM",
        App::Prop_Hidden,
        "Distinguish initial defaults from an intentionally empty selection"
    );
}
