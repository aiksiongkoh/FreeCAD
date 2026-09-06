// SPDX-License-Identifier: LGPL-2.1-or-later

#include "MbDPartPy.h"
#include "MbDPartPy.cpp"

#include <App/DocumentObjectPy.h>
#include <Base/VectorPy.h>

#include "MbDMassMarker.h"
#include "MbDMarker.h"

std::string MbDFEM::MbDPartPy::representation() const
{
    return "<MbDFEM::MbDPart>";
}

PyObject* MbDFEM::MbDPartPy::getCustomAttributes(const char* /*attr*/) const
{
    return nullptr;
}

int MbDFEM::MbDPartPy::setCustomAttributes(const char* /*attr*/, PyObject* /*value*/)
{
    return 0;
}

PyObject* MbDFEM::MbDPartPy::addMarker(PyObject* args)
{
    PyObject* object;
    if (!PyArg_ParseTuple(args, "O!", &App::DocumentObjectPy::Type, &object)) {
        return nullptr;
    }

    auto* documentObject = static_cast<App::DocumentObjectPy*>(object)->getDocumentObjectPtr();
    if (!documentObject->isDerivedFrom<MbDFEM::MbDMarker>()) {
        PyErr_SetString(PyExc_TypeError, "addMarker expects an MbDFEM::MbDMarker");
        return nullptr;
    }

    getMbDPartPtr()->addMarker(static_cast<MbDFEM::MbDMarker*>(documentObject));
    Py_Return;
}

PyObject* MbDFEM::MbDPartPy::removeMarker(PyObject* args)
{
    PyObject* object;
    if (!PyArg_ParseTuple(args, "O!", &App::DocumentObjectPy::Type, &object)) {
        return nullptr;
    }

    auto* documentObject = static_cast<App::DocumentObjectPy*>(object)->getDocumentObjectPtr();
    if (!documentObject->isDerivedFrom<MbDFEM::MbDMarker>()) {
        PyErr_SetString(PyExc_TypeError, "removeMarker expects an MbDFEM::MbDMarker");
        return nullptr;
    }

    getMbDPartPtr()->removeMarker(static_cast<MbDFEM::MbDMarker*>(documentObject));
    Py_Return;
}

PyObject* MbDFEM::MbDPartPy::getMarkersFolder(PyObject* args)
{
    if (!PyArg_ParseTuple(args, "")) {
        return nullptr;
    }

    auto* folder = getMbDPartPtr()->getMarkersFolder();
    if (!folder) {
        Py_Return;
    }

    return Py::new_reference_to(Py::asObject(folder->getPyObject()));
}

PyObject* MbDFEM::MbDPartPy::getMassMarker(PyObject* args)
{
    if (!PyArg_ParseTuple(args, "")) {
        return nullptr;
    }

    auto* marker = getMbDPartPtr()->getMassMarker();
    if (!marker) {
        Py_Return;
    }

    return Py::new_reference_to(Py::asObject(marker->getPyObject()));
}

PyObject* MbDFEM::MbDPartPy::ensureMassMarker(PyObject* args)
{
    if (!PyArg_ParseTuple(args, "")) {
        return nullptr;
    }

    auto* marker = getMbDPartPtr()->ensureMassMarker();
    if (!marker) {
        Py_Return;
    }

    return Py::new_reference_to(Py::asObject(marker->getPyObject()));
}

PyObject* MbDFEM::MbDPartPy::populateMassMarkerFromShape(PyObject* args)
{
    if (!PyArg_ParseTuple(args, "")) {
        return nullptr;
    }

    auto* marker = getMbDPartPtr()->populateMassMarkerFromShape();
    if (!marker) {
        Py_Return;
    }

    return Py::new_reference_to(Py::asObject(marker->getPyObject()));
}

PyObject* MbDFEM::MbDPartPy::globalPositionOf(PyObject* args)
{
    PyObject* pointObject;
    if (!PyArg_ParseTuple(args, "O!", &Base::VectorPy::Type, &pointObject)) {
        return nullptr;
    }

    const Base::Vector3d point = static_cast<Base::VectorPy*>(pointObject)->value();
    return new Base::VectorPy(getMbDPartPtr()->globalPositionOf(point));
}

PyObject* MbDFEM::MbDPartPy::globalVelocityOf(PyObject* args)
{
    PyObject* pointObject;
    if (!PyArg_ParseTuple(args, "O!", &Base::VectorPy::Type, &pointObject)) {
        return nullptr;
    }

    const Base::Vector3d point = static_cast<Base::VectorPy*>(pointObject)->value();
    return new Base::VectorPy(getMbDPartPtr()->globalVelocityOf(point));
}

PyObject* MbDFEM::MbDPartPy::globalAccelerationOf(PyObject* args)
{
    PyObject* pointObject;
    if (!PyArg_ParseTuple(args, "O!", &Base::VectorPy::Type, &pointObject)) {
        return nullptr;
    }

    const Base::Vector3d point = static_cast<Base::VectorPy*>(pointObject)->value();
    return new Base::VectorPy(getMbDPartPtr()->globalAccelerationOf(point));
}
