// SPDX-License-Identifier: LGPL-2.1-or-later

#include <Base/Console.h>
#include <Base/Exception.h>
#include <Base/Interpreter.h>
#include <Base/PyObjectBase.h>
#include <Base/VectorPy.h>
#include <App/DocumentObjectPy.h>

#include "AsmtIO.h"
#include "AnulAnulFacePair.h"
#include "CylCylFacePair.h"
#include "FEMAction.h"
#include "FEMAssembly.h"
#include "FEMItem.h"
#include "FEMJoint.h"
#include "FEMPart.h"
#include "FacePair.h"
#include "MbDAction.h"
#include "MbDAnimationParameters.h"
#include "MbDAssembly.h"
#include "MbDFolders.h"
#include "MbDGravity.h"
#include "MbDItemIJ.h"
#include "MbDJoint.h"
#include "MbDMassMarker.h"
#include "MbDMarker.h"
#include "MbDMotion.h"
#include "MbDPart.h"
#include "MbDSimulationParameters.h"
#include "RectRectFacePair.h"

namespace MbDFEM
{

class Module: public Py::ExtensionModule<Module>
{
public:
    Module()
        : Py::ExtensionModule<Module>("MbDFEM")
    {
        add_varargs_method("exportAssemblyAsmt",
                           &Module::exportAssemblyAsmt,
                           "exportAssemblyAsmt(assembly, filename) -- Export an MbDAssembly as ASMT.");
        add_varargs_method("importSolvedAsmt",
                           &Module::importSolvedAsmt,
                           "importSolvedAsmt(assembly, filename) -- Import solved ASMT result series.");
        add_varargs_method(
            "cylCylHoleCLOADs",
            &Module::cylCylHoleCLOADs,
            "cylCylHoleCLOADs(facePair, nodes, center, axis, radius, axialMin, axialMax, force)"
            " -- Compute cylindrical-hole CalculiX CLOAD records.");
        initialize("The MbDFEM module.");
    }

private:
    Py::Object invoke_method_varargs(void* method_def, const Py::Tuple& args) override
    {
        try {
            return Py::ExtensionModule<Module>::invoke_method_varargs(method_def, args);
        }
        catch (const Base::Exception& e) {
            throw Py::Exception(e.getPyExceptionType(), e.what());
        }
        catch (const std::exception& e) {
            throw Py::RuntimeError(e.what());
        }
    }

    Py::Object exportAssemblyAsmt(const Py::Tuple& args)
    {
        PyObject* object {};
        char* filename {};
        if (!PyArg_ParseTuple(args.ptr(),
                              "O!et",
                              &App::DocumentObjectPy::Type,
                              &object,
                              "utf-8",
                              &filename)) {
            throw Py::Exception();
        }

        std::string encodedFilename(filename);
        PyMem_Free(filename);

        auto* documentObject = static_cast<App::DocumentObjectPy*>(object)->getDocumentObjectPtr();
        auto* assembly = freecad_cast<MbDFEM::MbDAssembly*>(documentObject);
        if (!assembly) {
            throw Py::TypeError("exportAssemblyAsmt expects an MbDFEM::MbDAssembly");
        }

        return Py::String(MbDFEM::exportAssemblyAsmt(assembly, encodedFilename));
    }

    Py::Object importSolvedAsmt(const Py::Tuple& args)
    {
        PyObject* object {};
        char* filename {};
        if (!PyArg_ParseTuple(args.ptr(),
                              "O!et",
                              &App::DocumentObjectPy::Type,
                              &object,
                              "utf-8",
                              &filename)) {
            throw Py::Exception();
        }

        std::string encodedFilename(filename);
        PyMem_Free(filename);

        auto* documentObject = static_cast<App::DocumentObjectPy*>(object)->getDocumentObjectPtr();
        auto* assembly = freecad_cast<MbDFEM::MbDAssembly*>(documentObject);
        if (!assembly) {
            throw Py::TypeError("importSolvedAsmt expects an MbDFEM::MbDAssembly");
        }

        Py::List result;
        for (auto* imported : MbDFEM::importSolvedAsmt(assembly, encodedFilename)) {
            result.append(Py::Object(imported->getPyObject(), true));
        }
        return result;
    }

    Py::Object cylCylHoleCLOADs(const Py::Tuple& args)
    {
        PyObject* pairObject {};
        PyObject* nodesObject {};
        PyObject* centerObject {};
        PyObject* axisObject {};
        PyObject* forceObject {};
        double radius {};
        double axialMin {};
        double axialMax {};
        if (!PyArg_ParseTuple(args.ptr(),
                              "O!O!O!O!dddO!",
                              &App::DocumentObjectPy::Type,
                              &pairObject,
                              &PyList_Type,
                              &nodesObject,
                              &Base::VectorPy::Type,
                              &centerObject,
                              &Base::VectorPy::Type,
                              &axisObject,
                              &radius,
                              &axialMin,
                              &axialMax,
                              &Base::VectorPy::Type,
                              &forceObject)) {
            throw Py::Exception();
        }

        auto* documentObject =
            static_cast<App::DocumentObjectPy*>(pairObject)->getDocumentObjectPtr();
        auto* facePair = freecad_cast<MbDFEM::CylCylFacePair*>(documentObject);
        if (!facePair) {
            throw Py::TypeError("cylCylHoleCLOADs expects an MbDFEM::CylCylFacePair");
        }

        std::vector<MbDFEM::CylCylFacePair::HoleNode> nodes;
        const Py_ssize_t nodeCount = PyList_Size(nodesObject);
        nodes.reserve(static_cast<std::size_t>(nodeCount));
        for (Py_ssize_t index = 0; index < nodeCount; ++index) {
            PyObject* item = PyList_GetItem(nodesObject, index);
            int nodeId {};
            PyObject* positionObject {};
            if (!PyArg_ParseTuple(
                    item, "iO!", &nodeId, &Base::VectorPy::Type, &positionObject)) {
                throw Py::TypeError("nodes must contain (nodeId, FreeCAD.Vector) tuples");
            }
            nodes.push_back(
                {nodeId, static_cast<Base::VectorPy*>(positionObject)->value()});
        }

        const Base::Vector3d center = static_cast<Base::VectorPy*>(centerObject)->value();
        const Base::Vector3d axis = static_cast<Base::VectorPy*>(axisObject)->value();
        const Base::Vector3d force = static_cast<Base::VectorPy*>(forceObject)->value();
        const auto cloads = facePair->holeCLOADs(
            nodes, center, axis, radius, axialMin, axialMax, force);

        Py::List result;
        for (const auto& cload : cloads) {
            result.append(Py::asObject(Py_BuildValue("(iid)", cload.nodeId, cload.dof, cload.value)));
        }
        return result;
    }
};

PyObject* initModule()
{
    return Base::Interpreter().addModule(new Module);
}

}  // namespace MbDFEM

PyMOD_INIT_FUNC(MbDFEM)
{
    // load dependent module
    try {
        Base::Interpreter().runString("import Part");
    }
    catch (const Base::Exception& e) {
        PyErr_SetString(PyExc_ImportError, e.what());
        PyMOD_Return(nullptr);
    }

    PyObject* module = MbDFEM::initModule();
    MbDFEM::FEMItem::init();
    MbDFEM::FacePair::init();
    MbDFEM::CylCylFacePair::init();
    MbDFEM::AnulAnulFacePair::init();
    MbDFEM::RectRectFacePair::init();
    MbDFEM::FEMAction::init();
    MbDFEM::FEMAssembly::init();
    MbDFEM::FEMJoint::init();
    MbDFEM::FEMPart::init();
    MbDFEM::MbDAssembly::init();
    MbDFEM::MbDPart::init();
    MbDFEM::MbDMarker::init();
    MbDFEM::MbDMassMarker::init();
    MbDFEM::MbDItemIJ::init();
    MbDFEM::MbDJoint::init();
    MbDFEM::MbDMotion::init();
    MbDFEM::MbDAction::init();
    MbDFEM::MbDGravity::init();
    MbDFEM::MbDSimulationParameters::init();
    MbDFEM::MbDAnimationParameters::init();
    MbDFEM::MbDAssembliesFolder::init();
    MbDFEM::MbDPartsFolder::init();
    MbDFEM::MbDFixedPartsFolder::init();
    MbDFEM::MbDMarkersFolder::init();
    MbDFEM::MbDJointsFolder::init();
    MbDFEM::MbDMotionsFolder::init();
    MbDFEM::MbDActionsFolder::init();
    MbDFEM::FEMPartsFolder::init();
    MbDFEM::FEMResultsFolder::init();
    MbDFEM::FEMJointsFolder::init();
    MbDFEM::FEMMotionsFolder::init();
    MbDFEM::FEMActionsFolder::init();
    Base::Console().log("Loading MbDFEM module... done\n");
    PyMOD_Return(module);
}
