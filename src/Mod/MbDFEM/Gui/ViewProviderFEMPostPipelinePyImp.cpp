// SPDX-License-Identifier: LGPL-2.1-or-later

#include "ViewProviderFEMPostPipeline.h"
#include "ViewProviderFEMPostPipelinePy.h"
#include "ViewProviderFEMPostPipelinePy.cpp"

using namespace MbDFEMGui;

std::string ViewProviderFEMPostPipelinePy::representation() const
{
    return "<MbDFEMGui::ViewProviderFEMPostPipeline>";
}

PyObject* ViewProviderFEMPostPipelinePy::updateColorBars(PyObject* args)
{
    if (!PyArg_ParseTuple(args, "")) {
        return nullptr;
    }
    getViewProviderFEMPostPipelinePtr()->updateColorBars();
    Py_Return;
}

PyObject* ViewProviderFEMPostPipelinePy::getCustomAttributes(const char*) const
{
    return nullptr;
}

int ViewProviderFEMPostPipelinePy::setCustomAttributes(const char*, PyObject*)
{
    return 0;
}
