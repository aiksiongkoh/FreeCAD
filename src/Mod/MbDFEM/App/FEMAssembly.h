// SPDX-License-Identifier: LGPL-2.1-or-later

#pragma once

#include <App/DocumentObjectGroup.h>
#include <App/Part.h>
#include <App/PropertyLinks.h>
#include <vector>

#include <Mod/MbDFEM/MbDFEMGlobal.h>

namespace MbDFEM
{

class MbDFEMExport FEMAssembly: public App::Part
{
    PROPERTY_HEADER_WITH_OVERRIDE(MbDFEM::FEMAssembly);

public:
    FEMAssembly();
    ~FEMAssembly() override = default;
    App::PropertyLink mbdItem;
    App::PropertyLinkList parts;
    App::PropertyLinkList joints;
    App::PropertyLinkList motions;
    App::PropertyLinkList actions;
    App::PropertyLink femParameters;

    App::DocumentObjectGroup* getPartsFolder() const;
    App::DocumentObjectGroup* getJointsFolder() const;
    App::DocumentObjectGroup* getMotionsFolder() const;
    App::DocumentObjectGroup* getActionsFolder() const;
    std::vector<App::DocumentObjectGroup*> getCategoryFolders() const;
    std::vector<App::DocumentObject*> getCategoryChildren() const;

    App::DocumentObjectGroup* ensurePartsFolder();
    App::DocumentObjectGroup* ensureJointsFolder();
    App::DocumentObjectGroup* ensureMotionsFolder();
    App::DocumentObjectGroup* ensureActionsFolder();
    void ensureCategoryFolders();

    App::DocumentObjectExecReturn* execute() override;
    int setElementVisible(const char* element, bool visible) override;
    int isElementVisible(const char* element) const override;
    App::DocumentObject* getSubObject(const char* subname,
                                      PyObject** pyObj = nullptr,
                                      Base::Matrix4D* mat = nullptr,
                                      bool transform = true,
                                      int depth = 0) const override;

    const char* getViewProviderName() const override
    {
        return "MbDFEMGui::ViewProviderFEMAssembly";
    }

private:
    App::PropertyLink _partsFolder;
    App::PropertyLink _jointsFolder;
    App::PropertyLink _motionsFolder;
    App::PropertyLink _actionsFolder;
};

}  // namespace MbDFEM
