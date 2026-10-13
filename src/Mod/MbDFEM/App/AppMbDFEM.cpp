// SPDX-License-Identifier: LGPL-2.1-or-later

#include <Base/Console.h>
#include <Base/Exception.h>
#include <Base/Interpreter.h>
#include <Base/PlacementPy.h>
#include <Base/PyObjectBase.h>
#include <Base/VectorPy.h>
#include <App/DocumentObjectPy.h>
#include <App/GeoFeature.h>

#include "AsmtIO.h"
#include "AnnuAnnuFacePair.h"
#include "CylCylFacePair.h"
#include "FEMAction.h"
#include "FEMAssembly.h"
#include "FEMAnimationParameters.h"
#include "FEMSimulationParameters.h"
#include "FEMHole2PinFlangeJoint.h"
#include "FEMHolePinJoint.h"
#include "FEMItem.h"
#include "FEMJoint.h"
#include "FEMPart.h"
#include "FacePair.h"
#include "MbDAction.h"
#include "MbDAnimationParameters.h"
#include "MbDAssembly.h"
#include "MbDFolders.h"
#include "MbDGravity.h"
#include "MbDGroundPart.h"
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
        add_varargs_method(
            "exportAssemblyAsmt",
            &Module::exportAssemblyAsmt,
            "exportAssemblyAsmt(assembly, filename) -- Export an MbDAssembly as ASMT."
        );
        add_varargs_method(
            "convertToGroundPart",
            &Module::convertToGroundPart,
            "convertToGroundPart(part) -- Convert an MbDPart and move it to FixedParts."
        );
        add_varargs_method(
            "importSolvedAsmt",
            &Module::importSolvedAsmt,
            "importSolvedAsmt(assembly, filename) -- Import solved ASMT result series."
        );
        add_varargs_method(
            "annuAnnuValidateGeometry",
            &Module::annuAnnuValidateGeometry,
            "annuAnnuValidateGeometry(pair, linearTolerance=-1, angularTolerance=-1)"
            " -- Validate current annulus contact geometry; raises on invalid pairs."
        );
        add_varargs_method(
            "annuAnnuValidateSampledGeometry",
            &Module::annuAnnuValidateSampledGeometry,
            "annuAnnuValidateSampledGeometry(pair, lower=-1, upper=-1, ratio=0)"
            " -- Validate sampled contact geometry and identify the selected annulus side."
        );
        add_varargs_method(
            "annuAnnuFaceLoad",
            &Module::annuAnnuFaceLoad,
            "annuAnnuFaceLoad(pair, part, nodes, force, torque, markerOrigin)"
            " -- Distribute a supplied mesh-coordinate wrench on annular contact nodes."
        );
        add_varargs_method(
            "annuAnnuJointAnnulusLoad",
            &Module::annuAnnuJointAnnulusLoad,
            "annuAnnuJointAnnulusLoad(pair, joint, part, nodes, participatingPairs, lower=-1, "
            "upper=-1, ratio=0)"
            " -- Distribute the joint wrench on the selected annulus part."
        );
        add_varargs_method(
            "annuAnnuJointOtherAnnulusLoad",
            &Module::annuAnnuJointOtherAnnulusLoad,
            "annuAnnuJointOtherAnnulusLoad(pair, joint, part, nodes, participatingPairs, lower=-1, "
            "upper=-1, ratio=0)"
            " -- Distribute the joint wrench on the opposing annulus contact part."
        );
        add_varargs_method(
            "cylCylHoleCLOADs",
            &Module::cylCylHoleCLOADs,
            "cylCylHoleCLOADs(facePair, nodes, center, axis, radius, axialMin, axialMax, force)"
            " -- Compute cylindrical-hole CalculiX CLOAD records."
        );
        add_varargs_method(
            "cylCylJointState",
            &Module::cylCylJointState,
            "cylCylJointState(pair, joint, lower=-1, upper=-1, ratio=0, participatingPairCount=1)"
            " -- Refresh and return the global marker-I reaction and common load frames."
        );
        add_varargs_method(
            "cylCylJointHoleLoad",
            &Module::cylCylJointHoleLoad,
            "cylCylJointHoleLoad(pair, joint, part, nodes, participatingPairs, lower=-1, upper=-1, "
            "ratio=0)"
            " -- Finalized hole loading from joint results and referenced geometry."
        );
        add_varargs_method(
            "cylCylJointPinLoad",
            &Module::cylCylJointPinLoad,
            "cylCylJointPinLoad(pair, joint, part, nodes, participatingPairs, lower=-1, upper=-1, "
            "ratio=0)"
            " -- Load pin nodes touching the sampled hole contact face."
        );
        add_varargs_method(
            "cylCylHoleLoadComponents",
            &Module::cylCylHoleLoadComponents,
            "cylCylHoleLoadComponents(facePair, nodes, center, axis, radius, axialMin, axialMax, "
            "force, torque)"
            " -- Compute and validate separate hole force/torque CLOAD contributions in mesh "
            "coordinates."
        );
        initialize("The MbDFEM module.");
    }

private:
    Py::Object convertToGroundPart(const Py::Tuple& args)
    {
        PyObject* object {};
        if (!PyArg_ParseTuple(args.ptr(), "O!", &App::DocumentObjectPy::Type, &object)) {
            throw Py::Exception();
        }
        auto* part = freecad_cast<MbDPart*>(documentObject(object));
        if (!part) {
            throw Py::TypeError("convertToGroundPart expects an MbDFEM::MbDPart");
        }
        return Py::Object(MbDGroundPart::convert(part)->getPyObject(), true);
    }

    Py::Object annuAnnuValidateGeometry(const Py::Tuple& args)
    {
        PyObject* object {};
        double linearTolerance = -1.0, angularTolerance = -1.0;
        if (!PyArg_ParseTuple(
                args.ptr(),
                "O!|dd",
                &App::DocumentObjectPy::Type,
                &object,
                &linearTolerance,
                &angularTolerance
            )) {
            throw Py::Exception();
        }
        auto* pair = freecad_cast<AnnuAnnuFacePair*>(
            static_cast<App::DocumentObjectPy*>(object)->getDocumentObjectPtr()
        );
        if (!pair) {
            throw Py::TypeError("annuAnnuValidateGeometry expects an MbDFEM::AnnuAnnuFacePair");
        }
        const auto geometry = pair->validateGeometry(linearTolerance, angularTolerance);
        return annularGeometry(geometry);
    }

    Py::Object annuAnnuValidateSampledGeometry(const Py::Tuple& args)
    {
        PyObject* object {};
        int lower = -1, upper = -1;
        double ratio = 0.0;
        if (!PyArg_ParseTuple(
                args.ptr(),
                "O!|iid",
                &App::DocumentObjectPy::Type,
                &object,
                &lower,
                &upper,
                &ratio
            )) {
            throw Py::Exception();
        }
        auto* pair = freecad_cast<AnnuAnnuFacePair*>(documentObject(object));
        if (!pair) {
            throw Py::TypeError("Expected AnnuAnnuFacePair");
        }
        return annularGeometry(pair->validateSampledGeometry(lower, upper, ratio));
    }

    static Py::Dict annularGeometry(const AnnuAnnuFacePair::ValidatedGeometry& geometry)
    {
        Py::Dict result;
        result.setItem("annulusSide", Py::String(geometry.annulusIsFaceI ? "I" : "J"));
        result.setItem("center", Py::asObject(new Base::VectorPy(geometry.annulus.center)));
        result.setItem("axis", Py::asObject(new Base::VectorPy(geometry.annulus.axis)));
        result.setItem("innerRadius", Py::Float(geometry.annulus.innerRadius));
        result.setItem("outerRadius", Py::Float(geometry.annulus.outerRadius));
        return result;
    }

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
        if (
            !PyArg_ParseTuple(args.ptr(), "O!et", &App::DocumentObjectPy::Type, &object, "utf-8", &filename)
        ) {
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
        if (
            !PyArg_ParseTuple(args.ptr(), "O!et", &App::DocumentObjectPy::Type, &object, "utf-8", &filename)
        ) {
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

    template<class Loads>
    static Py::Dict loadComponents(const Loads& loads)
    {
        Py::Dict result;
        const auto add = [&result](const char* name, const auto& records) {
            Py::List values;
            for (const auto& record : records) {
                values.append(
                    Py::asObject(Py_BuildValue("(iid)", record.nodeId, record.dof, record.value))
                );
            }
            result.setItem(name, values);
        };
        add("transverse_force", loads.transverseForce);
        add("axial_force", loads.axialForce);
        add("bending_torque", loads.bendingTorque);
        add("axial_torque", loads.axialTorque);
        return result;
    }

    static Py::Dict jointState(const FacePair& pair)
    {
        Py::Dict result;
        result.setItem(
            "forceOnFaceIatOrigin",
            Py::asObject(new Base::VectorPy(pair.forceOnFaceIatOrigin))
        );
        result.setItem(
            "torqueOnFaceIatOrigin",
            Py::asObject(new Base::VectorPy(pair.torqueOnFaceIatOrigin))
        );
        result.setItem("forceCoord", Py::asObject(new Base::PlacementPy(pair.forceCoord)));
        result.setItem("torqueCoord", Py::asObject(new Base::PlacementPy(pair.torqueCoord)));
        const char* coordsOnFace = "Unknown";
        switch (pair.coordsOnFace) {
            case FacePair::IJUkn::I:
                coordsOnFace = "I";
                break;
            case FacePair::IJUkn::J:
                coordsOnFace = "J";
                break;
            case FacePair::IJUkn::Unknown:
                break;
        }
        result.setItem("coordsOnFace", Py::String(coordsOnFace));
        return result;
    }

    static App::DocumentObject* documentObject(PyObject* value)
    {
        return static_cast<App::DocumentObjectPy*>(value)->getDocumentObjectPtr();
    }

    static std::vector<FacePair*> participatingPairs(PyObject* values)
    {
        std::vector<FacePair*> result;
        for (Py_ssize_t i = 0; i < PyList_Size(values); ++i) {
            auto* value = PyList_GetItem(values, i);
            if (!PyObject_TypeCheck(value, &App::DocumentObjectPy::Type)) {
                throw Py::TypeError("Participants must be FacePair objects");
            }
            auto* pair = freecad_cast<FacePair*>(documentObject(value));
            if (!pair) {
                throw Py::TypeError("Participants must be FacePair objects");
            }
            result.push_back(pair);
        }
        return result;
    }

    static std::vector<AnnuAnnuFacePair::Node> annularNodes(PyObject* values)
    {
        std::vector<AnnuAnnuFacePair::Node> result;
        for (Py_ssize_t i = 0; i < PyList_Size(values); ++i) {
            int id;
            PyObject* vector;
            if (
                !PyArg_ParseTuple(PyList_GetItem(values, i), "iO!", &id, &Base::VectorPy::Type, &vector)
            ) {
                throw Py::Exception();
            }
            result.push_back({id, static_cast<Base::VectorPy*>(vector)->value()});
        }
        return result;
    }

    static Py::Dict annularLoad(const AnnuAnnuFacePair::FaceLoad& load)
    {
        Py::Dict result;
        const auto vector = [&result](const char* name, const Base::Vector3d& value) {
            result.setItem(name, Py::asObject(new Base::VectorPy(value)));
        };
        vector("origin", load.origin);
        vector("x_axis", load.xAxis);
        vector("y_axis", load.yAxis);
        vector("z_axis", load.zAxis);
        vector("torque_x_axis", load.torqueXAxis);
        vector("torque_y_axis", load.torqueYAxis);
        vector("force", load.force);
        vector("torque", load.torque);
        result.setItem("annulusSide", Py::String(load.annulusIsFaceI ? "I" : "J"));
        Py::Dict forceQuadrants, torqueQuadrants, regions;
        for (size_t q = 0; q < 4; ++q) {
            const auto list = [](const std::vector<int>& values) {
                Py::List result;
                for (int id : values) {
                    result.append(Py::Long(id));
                }
                return result;
            };
            const auto forceName = "FQ" + std::to_string(q + 1);
            const auto torqueName = "TQ" + std::to_string(q + 1);
            forceQuadrants.setItem(forceName, list(load.forceQuadrants[q]));
            torqueQuadrants.setItem(torqueName, list(load.torqueQuadrants[q]));
            regions.setItem(forceName, list(load.forceQuadrants[q]));
            regions.setItem(torqueName, list(load.torqueQuadrants[q]));
        }
        result.setItem("force_quadrants", forceQuadrants);
        result.setItem("torque_quadrants", torqueQuadrants);
        // Existing node-set formatting and face display accept named regions.
        result.setItem("octants", regions);
        result.setItem("cload_components", loadComponents(load));
        Py::List records;
        for (const auto& record : load.cloads) {
            records.append(
                Py::asObject(Py_BuildValue("(iid)", record.nodeId, record.dof, record.value))
            );
        }
        result.setItem("cloads", records);
        return result;
    }

    Py::Object annuAnnuFaceLoad(const Py::Tuple& args)
    {
        PyObject *pairObject {}, *partObject {}, *nodes {}, *force {}, *torque {}, *origin {};
        if (!PyArg_ParseTuple(
                args.ptr(),
                "O!O!O!O!O!O!",
                &App::DocumentObjectPy::Type,
                &pairObject,
                &App::DocumentObjectPy::Type,
                &partObject,
                &PyList_Type,
                &nodes,
                &Base::VectorPy::Type,
                &force,
                &Base::VectorPy::Type,
                &torque,
                &Base::VectorPy::Type,
                &origin
            )) {
            throw Py::Exception();
        }
        auto* pair = freecad_cast<AnnuAnnuFacePair*>(documentObject(pairObject));
        auto* part = freecad_cast<App::GeoFeature*>(documentObject(partObject));
        if (!pair || !part) {
            throw Py::TypeError("Expected AnnuAnnuFacePair and geometric part");
        }
        const auto value = [](PyObject* vector) {
            return static_cast<Base::VectorPy*>(vector)->value();
        };
        return annularLoad(
            pair->faceLoad(*part, annularNodes(nodes), value(force), value(torque), value(origin))
        );
    }

    Py::Object annuAnnuJointAnnulusLoad(const Py::Tuple& args)
    {
        return annuAnnuJointLoad(args, true);
    }

    Py::Object annuAnnuJointOtherAnnulusLoad(const Py::Tuple& args)
    {
        return annuAnnuJointLoad(args, false);
    }

    Py::Object annuAnnuJointLoad(const Py::Tuple& args, bool annulusSide)
    {
        PyObject *pairObject {}, *jointObject {}, *partObject {}, *nodes {}, *participants {};
        int lower = -1, upper = -1;
        double ratio = 0.0;
        if (!PyArg_ParseTuple(
                args.ptr(),
                "O!O!O!O!O!|iid",
                &App::DocumentObjectPy::Type,
                &pairObject,
                &App::DocumentObjectPy::Type,
                &jointObject,
                &App::DocumentObjectPy::Type,
                &partObject,
                &PyList_Type,
                &nodes,
                &PyList_Type,
                &participants,
                &lower,
                &upper,
                &ratio
            )) {
            throw Py::Exception();
        }
        auto* pair = freecad_cast<AnnuAnnuFacePair*>(documentObject(pairObject));
        auto* joint = freecad_cast<MbDJoint*>(documentObject(jointObject));
        auto* part = freecad_cast<MbDPart*>(documentObject(partObject));
        if (!pair || !joint || !part) {
            throw Py::TypeError("Expected AnnuAnnuFacePair, MbDJoint and MbDPart");
        }
        const auto load = annulusSide ? &AnnuAnnuFacePair::jointAnnulusLoad
                                      : &AnnuAnnuFacePair::jointOtherAnnulusLoad;
        auto result = annularLoad((pair->*load)(
            *joint,
            *part,
            annularNodes(nodes),
            participatingPairs(participants),
            lower,
            upper,
            ratio
        ));
        result.setItem("joint_state", jointState(*pair));
        return result;
    }

    Py::Object cylCylJointState(const Py::Tuple& args)
    {
        PyObject *pairObject {}, *jointObject {};
        int lower = -1, upper = -1, participatingPairCount = 1;
        double ratio = 0.0;
        if (!PyArg_ParseTuple(
                args.ptr(),
                "O!O!|iidi",
                &App::DocumentObjectPy::Type,
                &pairObject,
                &App::DocumentObjectPy::Type,
                &jointObject,
                &lower,
                &upper,
                &ratio,
                &participatingPairCount
            )) {
            throw Py::Exception();
        }
        auto* pair = freecad_cast<CylCylFacePair*>(
            static_cast<App::DocumentObjectPy*>(pairObject)->getDocumentObjectPtr()
        );
        auto* joint = freecad_cast<MbDJoint*>(
            static_cast<App::DocumentObjectPy*>(jointObject)->getDocumentObjectPtr()
        );
        if (!pair || !joint) {
            throw Py::TypeError("Expected CylCylFacePair and MbDJoint");
        }
        pair->updateJointState(*joint, lower, upper, ratio, participatingPairCount);
        return jointState(*pair);
    }

    Py::Object cylCylJointHoleLoad(const Py::Tuple& args)
    {
        return cylCylJointLoad(args, true);
    }

    Py::Object cylCylJointPinLoad(const Py::Tuple& args)
    {
        return cylCylJointLoad(args, false);
    }

    Py::Object cylCylJointLoad(const Py::Tuple& args, bool holeSide)
    {
        PyObject *pairObject {}, *jointObject {}, *partObject {}, *nodeObjects {}, *pairObjects {};
        int lower = -1, upper = -1;
        double ratio = 0.0;
        if (!PyArg_ParseTuple(
                args.ptr(),
                "O!O!O!O!O!|iid",
                &App::DocumentObjectPy::Type,
                &pairObject,
                &App::DocumentObjectPy::Type,
                &jointObject,
                &App::DocumentObjectPy::Type,
                &partObject,
                &PyList_Type,
                &nodeObjects,
                &PyList_Type,
                &pairObjects,
                &lower,
                &upper,
                &ratio
            )) {
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
        const auto participants = participatingPairs(pairObjects);
        std::vector<CylCylFacePair::HoleNode> nodes;
        for (Py_ssize_t i = 0; i < PyList_Size(nodeObjects); ++i) {
            int id;
            PyObject* vector;
            if (
                !PyArg_ParseTuple(PyList_GetItem(nodeObjects, i), "iO!", &id, &Base::VectorPy::Type, &vector)
            ) {
                throw Py::Exception();
            }
            nodes.push_back({id, static_cast<Base::VectorPy*>(vector)->value()});
        }
        const auto load = holeSide
            ? pair->jointHoleLoad(*joint, *part, nodes, participants, lower, upper, ratio)
            : pair->jointPinLoad(*joint, *part, nodes, participants, lower, upper, ratio);
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
        result.setItem("joint_state", jointState(*pair));
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
        if (!PyArg_ParseTuple(
                args.ptr(),
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
                &torqueObject
            )) {
            throw Py::Exception();
        }

        auto* documentObject = static_cast<App::DocumentObjectPy*>(pairObject)->getDocumentObjectPtr();
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
            if (!PyArg_ParseTuple(item, "iO!", &nodeId, &Base::VectorPy::Type, &positionObject)) {
                throw Py::TypeError("nodes must contain (nodeId, FreeCAD.Vector) tuples");
            }
            nodes.push_back({nodeId, static_cast<Base::VectorPy*>(positionObject)->value()});
        }

        const Base::Vector3d center = static_cast<Base::VectorPy*>(centerObject)->value();
        const Base::Vector3d axis = static_cast<Base::VectorPy*>(axisObject)->value();
        const Base::Vector3d force = static_cast<Base::VectorPy*>(forceObject)->value();
        if (components) {
            const Base::Vector3d torque = static_cast<Base::VectorPy*>(torqueObject)->value();
            const auto loads
                = facePair->holeCLOADs(nodes, center, axis, radius, axialMin, axialMax, force, torque);
            return loadComponents(loads);
        }
        const auto cloads
            = facePair->holeCLOADs(nodes, center, axis, radius, axialMin, axialMax, force);

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
    MbDFEM::AnnuAnnuFacePair::init();
    MbDFEM::RectRectFacePair::init();
    MbDFEM::FEMAction::init();
    MbDFEM::FEMAssembly::init();
    MbDFEM::FEMAnimationParameters::init();
    MbDFEM::FEMSimulationParameters::init();
    MbDFEM::FEMJoint::init();
    MbDFEM::FEMHole2PinFlangeJoint::init();
    MbDFEM::FEMHolePinJoint::init();
    MbDFEM::FEMPart::init();
    MbDFEM::MbDAssembly::init();
    MbDFEM::MbDPart::init();
    MbDFEM::MbDGroundPart::init();
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
