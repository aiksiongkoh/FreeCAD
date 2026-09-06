// SPDX-License-Identifier: LGPL-2.1-or-later

#include "FEMPartPy.h"
#include "FEMPartPy.cpp"

#include <App/DocumentObjectGroup.h>
#include <Base/VectorPy.h>

std::string MbDFEM::FEMPartPy::representation() const
{
    return "<MbDFEM::FEMPart>";
}

PyObject* MbDFEM::FEMPartPy::getCustomAttributes(const char* /*attr*/) const
{
    return nullptr;
}

int MbDFEM::FEMPartPy::setCustomAttributes(const char* /*attr*/, PyObject* /*value*/)
{
    return 0;
}

PyObject* MbDFEM::FEMPartPy::elementCentroidLocal(PyObject* args)
{
    int elementId;
    if (!PyArg_ParseTuple(args, "i", &elementId)) {
        return nullptr;
    }

    return new Base::VectorPy(getFEMPartPtr()->elementCentroidLocal(elementId));
}

PyObject* MbDFEM::FEMPartPy::elementCentroidGlobal(PyObject* args)
{
    int elementId;
    if (!PyArg_ParseTuple(args, "i", &elementId)) {
        return nullptr;
    }

    return new Base::VectorPy(getFEMPartPtr()->elementCentroidGlobal(elementId));
}

PyObject* MbDFEM::FEMPartPy::resultForState(PyObject* args)
{
    int stateIndex;
    if (!PyArg_ParseTuple(args, "i", &stateIndex)) {
        return nullptr;
    }

    auto* result = getFEMPartPtr()->resultForState(stateIndex);
    if (!result) {
        Py_RETURN_NONE;
    }
    return result->getPyObject();
}

PyObject* MbDFEM::FEMPartPy::validateResultSeries(PyObject* args)
{
    if (!PyArg_ParseTuple(args, "")) {
        return nullptr;
    }

    getFEMPartPtr()->validateResultSeries();
    Py_RETURN_NONE;
}

PyObject* MbDFEM::FEMPartPy::getResultsFolder(PyObject* args)
{
    if (!PyArg_ParseTuple(args, "")) {
        return nullptr;
    }

    auto* folder = getFEMPartPtr()->getResultsFolder();
    if (!folder) {
        Py_Return;
    }

    return Py::new_reference_to(Py::asObject(folder->getPyObject()));
}

PyObject* MbDFEM::FEMPartPy::ensureResultsFolder(PyObject* args)
{
    if (!PyArg_ParseTuple(args, "")) {
        return nullptr;
    }

    auto* folder = getFEMPartPtr()->ensureResultsFolder();
    if (!folder) {
        Py_Return;
    }

    return Py::new_reference_to(Py::asObject(folder->getPyObject()));
}

PyObject* MbDFEM::FEMPartPy::synchronizeResultsFolder(PyObject* args)
{
    if (!PyArg_ParseTuple(args, "")) {
        return nullptr;
    }

    getFEMPartPtr()->synchronizeResultsFolder();
    Py_Return;
}
