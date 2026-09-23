// SPDX-License-Identifier: LGPL-2.1-or-later
// Material and legend handling adapted from FemGui::ViewProviderFemPostObject,
// Copyright (c) 2015 Stefan Troeger, LGPL-2.1-or-later.

#include <Inventor/nodes/SoDrawStyle.h>
#include <Inventor/nodes/SoMaterial.h>
#include <Inventor/nodes/SoMaterialBinding.h>
#include <Base/Tools.h>
#include <Mod/Fem/App/FemPostPipeline.h>

#include "ViewProviderFEMPostPipeline.h"
#include "ViewProviderFEMPostPipelinePy.h"

using namespace MbDFEMGui;

PROPERTY_SOURCE(MbDFEMGui::ViewProviderFEMPostPipeline, FemGui::ViewProviderFemPostPipeline)

ViewProviderFEMPostPipeline::ViewProviderFEMPostPipeline()
{
    ADD_PROPERTY_TYPE(ShowColorContour, (true), "Coloring", App::Prop_None,
                      "Show scalar colors while retaining the selected field");
    ADD_PROPERTY_TYPE(ShowLegend, (true), "Coloring", App::Prop_None,
                      "Show the legend when scalar colors are displayed");
    // FEM also refreshes materials through non-virtual calls when another
    // pipeline is hidden. Reapply local policy after those scene-graph updates.
    const auto refresh = [](void* data, SoSensor*) {
        static_cast<ViewProviderFEMPostPipeline*>(data)->applyDisplayOptions();
    };
    materialSensor.setFunction(refresh);
    materialSensor.setData(this);
    legendSensor.setFunction(refresh);
    legendSensor.setData(this);
    materialSensor.attach(m_material);
    legendSensor.attach(m_colorStyle);
}

bool ViewProviderFEMPostPipeline::allowOverride(const App::DocumentObject& object) const
{
    return object.isDerivedFrom<Fem::FemPostPipeline>();
}

void ViewProviderFEMPostPipeline::applyDisplayOptions()
{
    materialSensor.detach();
    legendSensor.detach();
    const bool contour = ShowColorContour.getValue() && Field.hasEnums() && Field.getValue() > 0;
    m_colorStyle->style = Visibility.getValue() && contour && ShowLegend.getValue()
        ? SoDrawStyle::FILLED : SoDrawStyle::INVISIBLE;
    if (!contour) {
        const auto color = NoneFieldColor.getValue();
        m_material->diffuseColor.setValue(SbColor(color.r, color.g, color.b));
        m_material->transparency.setValue(Base::fromPercent(Transparency.getValue()));
        m_materialBinding->value = SoMaterialBinding::OVERALL;
        m_materialBinding->touch();
    }
    materialSensor.attach(m_material);
    legendSensor.attach(m_colorStyle);
}

void ViewProviderFEMPostPipeline::onChanged(const App::Property* prop)
{
    FemGui::ViewProviderFemPostPipeline::onChanged(prop);
    if (prop == &ShowColorContour && getObject()) {
        updateMaterial();
    }
    applyDisplayOptions();
}

void ViewProviderFEMPostPipeline::updateData(const App::Property* prop)
{
    FemGui::ViewProviderFemPostPipeline::updateData(prop);
    applyDisplayOptions();
}

void ViewProviderFEMPostPipeline::setDisplayMode(const char* mode)
{
    FemGui::ViewProviderFemPostPipeline::setDisplayMode(mode);
    applyDisplayOptions();
}

void ViewProviderFEMPostPipeline::show()
{
    FemGui::ViewProviderFemPostPipeline::show();
    applyDisplayOptions();
}

void ViewProviderFEMPostPipeline::OnChange(Base::Subject<int>& caller, int reason)
{
    FemGui::ViewProviderFemPostPipeline::OnChange(caller, reason);
    applyDisplayOptions();
}

void ViewProviderFEMPostPipeline::onSelectionChanged(const Gui::SelectionChanges& selection)
{
    FemGui::ViewProviderFemPostPipeline::onSelectionChanged(selection);
    applyDisplayOptions();
}

void ViewProviderFEMPostPipeline::updateColorBars()
{
    FemGui::ViewProviderFemPostPipeline::updateColorBars();
    applyDisplayOptions();
}

PyObject* ViewProviderFEMPostPipeline::getPyObject()
{
    if (!pyViewObject) {
        pyViewObject = new ViewProviderFEMPostPipelinePy(this);
    }
    pyViewObject->IncRef();
    return pyViewObject;
}
