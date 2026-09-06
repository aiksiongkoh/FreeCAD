/***************************************************************************
 *   Copyright (c) 2022 Uwe Stöhr <uwestoehr@lyx.org>                      *
 *                                                                         *
 *   This file is part of the FreeCAD CAx development system.              *
 *                                                                         *
 *   This library is free software; you can redistribute it and/or         *
 *   modify it under the terms of the GNU Library General Public           *
 *   License as published by the Free Software Foundation; either          *
 *   version 2 of the License, or (at your option) any later version.      *
 *                                                                         *
 *   This library  is distributed in the hope that it will be useful,      *
 *   but WITHOUT ANY WARRANTY; without even the implied warranty of        *
 *   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the         *
 *   GNU Library General Public License for more details.                  *
 *                                                                         *
 *   You should have received a copy of the GNU Library General Public     *
 *   License along with this library; see the file COPYING.LIB. If not,    *
 *   write to the Free Software Foundation, Inc., 59 Temple Place,         *
 *   Suite 330, Boston, MA  02111-1307, USA                                *
 *                                                                         *
 ***************************************************************************/


// clang-format off
#include <Gui/PythonWrapper.h>
#include "ViewProviderFemPostPipeline.h"
#include "TaskPostBoxes.h"
#ifdef FC_USE_VTK_PYTHON
#include "TaskPostExtraction.h"
#endif
// inclusion of the generated files (generated out of ViewProviderFemPostPipelinePy.xml)
#include "ViewProviderFemPostPipelinePy.h"
#include "ViewProviderFemPostPipelinePy.cpp"
// clang-format on


using namespace FemGui;

// returns a string which represents the object e.g. when printed in python
std::string ViewProviderFemPostPipelinePy::representation() const
{
    return {"<ViewProviderFemPostPipeline object>"};
}

PyObject* ViewProviderFemPostPipelinePy::updateColorBars(PyObject* args)
{
    if (!PyArg_ParseTuple(args, "")) {
        return nullptr;
    }

    this->getViewProviderFemPostPipelinePtr()->updateColorBars();

    Py_Return;
}

PyObject* ViewProviderFemPostPipelinePy::transformField(PyObject* args)
{
    char* FieldName;
    double FieldFactor;

    if (!PyArg_ParseTuple(args, "sd", &FieldName, &FieldFactor)) {
        return nullptr;
    }

    this->getViewProviderFemPostPipelinePtr()->transformField(FieldName, FieldFactor);

    Py_Return;
}

PyObject* ViewProviderFemPostPipelinePy::createDisplayTaskWidget(PyObject* args)
{
    if (!PyArg_ParseTuple(args, "")) {
        return nullptr;
    }

    auto panel = new TaskPostDisplay(getViewProviderFemPostPipelinePtr());

    Gui::PythonWrapper wrap;
    if (wrap.loadCoreModule()) {
        return Py::new_reference_to(wrap.fromQWidget(panel));
    }

    PyErr_SetString(PyExc_TypeError, "creating the panel failed");
    return nullptr;
}

PyObject* ViewProviderFemPostPipelinePy::createExtractionTaskWidget(PyObject* args)
{
#ifdef FC_USE_VTK_PYTHON
    if (!PyArg_ParseTuple(args, "")) {
        return nullptr;
    }

    auto panel = new TaskPostExtraction(getViewProviderFemPostPipelinePtr());

    Gui::PythonWrapper wrap;
    if (wrap.loadCoreModule()) {
        return Py::new_reference_to(wrap.fromQWidget(panel));
    }

    PyErr_SetString(PyExc_TypeError, "creating the panel failed");
    return nullptr;
#else
    (void)args;
    PyErr_SetString(PyExc_NotImplementedError, "VTK python wrapper not available");
    return nullptr;
#endif
}

PyObject* ViewProviderFemPostPipelinePy::createFramesTaskWidget(PyObject* args)
{
    if (!PyArg_ParseTuple(args, "")) {
        return nullptr;
    }

    auto panel = new TaskPostFrames(getViewProviderFemPostPipelinePtr());

    Gui::PythonWrapper wrap;
    if (wrap.loadCoreModule()) {
        return Py::new_reference_to(wrap.fromQWidget(panel));
    }

    PyErr_SetString(PyExc_TypeError, "creating the panel failed");
    return nullptr;
}

PyObject* ViewProviderFemPostPipelinePy::getCustomAttributes(const char* /*attr*/) const
{
    return nullptr;
}

int ViewProviderFemPostPipelinePy::setCustomAttributes(const char* /*attr*/, PyObject* /*obj*/)
{
    return 0;
}
