// SPDX-License-Identifier: LGPL-2.1-or-later

#pragma once

#include <Inventor/sensors/SoNodeSensor.h>
#include <Mod/Fem/Gui/ViewProviderFemPostPipeline.h>
#include <Mod/MbDFEM/MbDFEMGlobal.h>

namespace MbDFEMGui
{

// Keep MbDFEM display policy separate from the general FEM post processor.
class MbDFEMGuiExport ViewProviderFEMPostPipeline: public FemGui::ViewProviderFemPostPipeline
{
    PROPERTY_HEADER_WITH_OVERRIDE(MbDFEMGui::ViewProviderFEMPostPipeline);

public:
    ViewProviderFEMPostPipeline();
    App::PropertyBool ShowColorContour;
    App::PropertyBool ShowLegend;

    bool allowOverride(const App::DocumentObject&) const override;
    void onChanged(const App::Property* prop) override;
    void updateData(const App::Property* prop) override;
    void setDisplayMode(const char* mode) override;
    void show() override;
    void OnChange(Base::Subject<int>& caller, int reason) override;
    void onSelectionChanged(const Gui::SelectionChanges& selection) override;
    void updateColorBars();
    PyObject* getPyObject() override;

private:
    void applyDisplayOptions();
    SoNodeSensor materialSensor;
    SoNodeSensor legendSensor;
};

}  // namespace MbDFEMGui
