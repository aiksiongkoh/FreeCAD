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
        add_varargs_method(
            "cylCylJointHoleLoad",
            &Module::cylCylJointHoleLoad,
            "cylCylJointHoleLoad(pair, joint, part, nodes, participatingPairs, lower=-1, upper=-1, ratio=0)"
            " -- Finalized hole loading from joint results and referenced geometry.");
        add_varargs_method(
            "cylCylHoleLoadComponents",
            &Module::cylCylHoleLoadComponents,
            "cylCylHoleLoadComponents(facePair, nodes, center, axis, radius, axialMin, axialMax, force, torque)"
            " -- Compute and validate separate hole force/torque CLOAD contributions in mesh coordinates.");
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

    static Py::Dict loadComponents(const CylCylFacePair::HoleLoadComponents& loads)
    {
        Py::Dict result;
        const auto add = [&result](const char* name, const auto& records) {
            Py::List values;
            for (const auto& record : records) {
                values.append(Py::asObject(Py_BuildValue("(iid)", record.nodeId, record.dof, record.value)));
            }
            result.setItem(name, values);
        };
        add("transverse_force", loads.transverseForce);
        add("axial_force", loads.axialForce);
        add("bending_torque", loads.bendingTorque);
        add("axial_torque", loads.axialTorque);
        return result;
    }

    Py::Object cylCylJointHoleLoad(const Py::Tuple& args)
    {
        PyObject *pairObject {}, *jointObject {}, *partObject {}, *nodeObjects {}, *pairObjects {};
        int lower = -1, upper = -1;
        double ratio = 0.0;
        if (!PyArg_ParseTuple(args.ptr(), "O!O!O!O!O!|iid",
                              &App::DocumentObjectPy::Type, &pairObject,
                              &App::DocumentObjectPy::Type, &jointObject,
                              &App::DocumentObjectPy::Type, &partObject,
                              &PyList_Type, &nodeObjects, &PyList_Type, &pairObjects,
                              &lower, &upper, &ratio)) {
            throw Py::Exception();
        }
        const auto object = [](PyObject* value) {
            return static_cast<App::DocumentObjectPy*>(value)->getDocumentObjectPtr();
        };
        auto* pair = freecad_cast<CylCylFacePair*>(object(pairObject));
        auto* joint = freecad_cast<MbDJoint*>(object(jointObject));
        auto* part = freecad_cast<MbDPart*>(object(partObject));
        if (!pair || !joint || !part) {
            throw Py::TypeError("Expected CylCylFacePair, MbDJoint and MbDPart");
        }
        std::vector<CylCylFacePair*> participants;
        for (Py_ssize_t i = 0; i < PyList_Size(pairObjects); ++i) {
            PyObject* value = PyList_GetItem(pairObjects, i);
            if (!PyObject_TypeCheck(value, &App::DocumentObjectPy::Type)) {
                throw Py::TypeError("Participants must be CylCylFacePair objects");
            }
            auto* participant = freecad_cast<CylCylFacePair*>(object(value));
            if (!participant) {
                throw Py::TypeError("Participants must be CylCylFacePair objects");
            }
            participants.push_back(participant);
        }
        std::vector<CylCylFacePair::HoleNode> nodes;
        for (Py_ssize_t i = 0; i < PyList_Size(nodeObjects); ++i) {
            int id;
            PyObject* vector;
            if (!PyArg_ParseTuple(PyList_GetItem(nodeObjects, i), "iO!", &id, &Base::VectorPy::Type, &vector)) {
                throw Py::Exception();
            }
            nodes.push_back({id, static_cast<Base::VectorPy*>(vector)->value()});
        }
        const auto load = pair->jointHoleLoad(*joint, *part, nodes, participants, lower, upper, ratio);
        Py::Dict result;
        const auto addVector = [&result](const char* name, const Base::Vector3d& vector) {
            result.setItem(name, Py::asObject(new Base::VectorPy(vector)));
        };
        addVector("origin", load.origin);
        addVector("x_axis", load.xAxis);
        addVector("y_axis", load.yAxis);
        addVector("z_axis", load.zAxis);
        addVector("force", load.force);
        addVector("torque", load.torque);
        Py::Dict octants;
        const char* names[] = {"U1", "U2", "U3", "U4", "L1", "L2", "L3", "L4"};
        for (size_t i = 0; i < load.octants.size(); ++i) {
            Py::List ids;
            for (int id : load.octants[i]) {
                ids.append(Py::Long(id));
            }
            octants.setItem(names[i], ids);
        }
        result.setItem("octants", octants);
        result.setItem("cload_components", loadComponents(load.components));
        return result;
    }

    Py::Object cylCylHoleCLOADs(const Py::Tuple& args)
    {
        return holeLoads(args, false);
    }

    Py::Object cylCylHoleLoadComponents(const Py::Tuple& args)
    {
        return holeLoads(args, true);
    }

    Py::Object holeLoads(const Py::Tuple& args, bool components)
    {
        PyObject* pairObject {};
        PyObject* nodesObject {};
        PyObject* centerObject {};
        PyObject* axisObject {};
        PyObject* forceObject {};
        PyObject* torqueObject {};
        double radius {};
        double axialMin {};
        double axialMax {};
        if (!PyArg_ParseTuple(args.ptr(),
                              components ? "O!O!O!O!dddO!O!" : "O!O!O!O!dddO!",
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
                              &forceObject,
                              &Base::VectorPy::Type,
                              &torqueObject)) {
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
        if (components) {
            const Base::Vector3d torque = static_cast<Base::VectorPy*>(torqueObject)->value();
            const auto loads = facePair->holeCLOADs(
                nodes, center, axis, radius, axialMin, axialMax, force, torque);
            return loadComponents(loads);
        }
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
