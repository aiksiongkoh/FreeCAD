// SPDX-License-Identifier: LGPL-2.1-or-later

#pragma once

#include <App/OriginGroupExtension.h>
#include <App/PropertyLinks.h>
#include <Base/Vector3D.h>
#include <Mod/MbDFEM/MbDFEMGlobal.h>
#include <Mod/Part/App/PartFeature.h>

namespace MbDFEM
{

class MbDFEMExport FEMPart: public Part::Feature, public App::OriginGroupExtension
{
    PROPERTY_HEADER_WITH_EXTENSIONS(MbDFEM::FEMPart);

public:
    FEMPart();
    ~FEMPart() override = default;
    App::PropertyLink mbdItem;
    App::PropertyLink mesh;
    App::PropertyLink solver;
    App::PropertyLinkList results;
    App::PropertyLink visual;

    App::DocumentObjectExecReturn* execute() override;
    PyObject* getPyObject() override;
    App::DocumentObject* getSubObject(const char* subname,
                                      PyObject** pyObj = nullptr,
                                      Base::Matrix4D* mat = nullptr,
                                      bool transform = true,
                                      int depth = 0) const override;
    int setElementVisible(const char* element, bool visible) override;
    int isElementVisible(const char* element) const override;

    Base::Vector3d elementCentroidLocal(int elementId) const;
    Base::Vector3d elementCentroidGlobal(int elementId) const;
    App::DocumentObject* resultForState(int stateIndex) const;
    void validateResultSeries() const;
    App::DocumentObjectGroup* getResultsFolder() const;
    App::DocumentObjectGroup* ensureResultsFolder();
    void synchronizeResultsFolder();
    void onChanged(const App::Property* prop) override;
    void onDocumentRestored() override;
    void unsetupObject() override;

    const char* getViewProviderName() const override
    {
        return "MbDFEMGui::ViewProviderFEMPart";
    }

private:
    App::PropertyLink _resultsFolder;
};

}  // namespace MbDFEM
