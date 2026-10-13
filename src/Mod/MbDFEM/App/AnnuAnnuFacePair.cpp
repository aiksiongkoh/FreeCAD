// SPDX-License-Identifier: LGPL-2.1-or-later

#include "AnnuAnnuFacePair.h"
#include "FEMHole2PinFlangeJoint.h"
#include "JointLoadUtils.h"
#include "MbDJoint.h"
#include <Base/Matrix.h>
#include <Eigen/SVD>

#include <App/GeoFeature.h>
#include <Mod/Part/App/PartFeature.h>
#include <BRepAdaptor_Curve.hxx>
#include <BRepAdaptor_Surface.hxx>
#include <BRepAlgoAPI_Cut.hxx>
#include <BRepBuilderAPI_Transform.hxx>
#include <BRepCheck_Analyzer.hxx>
#include <BRepGProp.hxx>
#include <BRep_Tool.hxx>
#include <GProp_GProps.hxx>
#include <Precision.hxx>
#include <Standard_Failure.hxx>
#include <TopExp_Explorer.hxx>
#include <TopoDS.hxx>
#include <TopoDS_Face.hxx>
#include <TopoDS_Wire.hxx>
#include <gp_Circ.hxx>
#include <gp_Pln.hxx>

#include <algorithm>
#include <cmath>
#include <stdexcept>
#include <utility>
#include <vector>
#include <unordered_set>
#include <gp_Trsf.hxx>

PROPERTY_SOURCE(MbDFEM::AnnuAnnuFacePair, MbDFEM::FacePair)

const char* MbDFEM::AnnuAnnuFacePair::LoadCostEnums[] = {"C", "C2", nullptr};

MbDFEM::AnnuAnnuFacePair::AnnuAnnuFacePair()
{
    loadCost.setEnums(LoadCostEnums);
    ADD_PROPERTY_TYPE(
        loadCost,
        (long(1)),
        "MbDFEM",
        App::Prop_None,
        "C: minimum quadrant coefficient; C2: minimum nodal magnitude"
    );
}

namespace
{
double checkedTolerance(double value, double fallback)
{
    if (!std::isfinite(value) || value == 0.0) {
        throw std::runtime_error("AnnuAnnuFacePair tolerances must be finite and positive.");
    }
    return value < 0.0 ? fallback : value;
}

TopoDS_Face referencedFace(const App::PropertyLinkSub& link, const char* side)
{
    auto* object = link.getValue();
    const auto& names = link.getSubValues();
    if (!object || names.size() != 1 || names.front().empty()) {
        throw std::runtime_error(
            std::string("AnnuAnnuFacePair face") + side + " requires exactly one face reference."
        );
    }
    // getShape applies the referenced object's placement and resolves links and
    // nested subobjects. Supply the parent's placement separately, exactly once.
    Base::Matrix4D parentTransform;
    if (const auto* feature = freecad_cast<const App::GeoFeature*>(object)) {
        parentTransform
            = (feature->globalPlacement() * feature->Placement.getValue().inverse()).toMatrix();
    }
    const auto shape = Part::Feature::getShape(
        object,
        Part::ShapeOption::NeedSubElement | Part::ShapeOption::ResolveLink
            | Part::ShapeOption::Transform,
        names.front().c_str(),
        &parentTransform
    );
    if (shape.IsNull() || shape.ShapeType() != TopAbs_FACE || !BRepCheck_Analyzer(shape).IsValid()) {
        throw std::runtime_error(
            std::string("AnnuAnnuFacePair face") + side + " does not resolve to a valid face."
        );
    }
    return TopoDS::Face(shape);
}

TopoDS_Face sampledFace(const App::PropertyLinkSub& link, const char* side, const Base::Placement& placement)
{
    try {
        const auto* part = freecad_cast<const MbDFEM::MbDPart*>(link.getValue());
        if (!part) {
            throw std::runtime_error("Annular joint loading requires MbDPart face references.");
        }
        const auto delta = (placement * part->globalPlacement().inverse()).toMatrix();
        gp_Trsf transform;
        transform.SetValues(
            delta[0][0],
            delta[0][1],
            delta[0][2],
            delta[0][3],
            delta[1][0],
            delta[1][1],
            delta[1][2],
            delta[1][3],
            delta[2][0],
            delta[2][1],
            delta[2][2],
            delta[2][3]
        );
        return TopoDS::Face(
            BRepBuilderAPI_Transform(referencedFace(link, side), transform, true).Shape()
        );
    }
    catch (const Standard_Failure& error) {
        throw std::runtime_error(
            std::string("Annular sampled geometry operation failed: ") + error.GetMessageString()
        );
    }
}

double faceArea(const TopoDS_Face& face)
{
    GProp_GProps properties;
    BRepGProp::SurfaceProperties(face, properties);
    return std::abs(properties.Mass());
}

bool parallel(const gp_Dir& first, const gp_Dir& second, double angularTolerance)
{
    const double angle = first.Angle(second);
    return std::min(angle, std::acos(-1.0) - angle) <= angularTolerance;
}
}  // namespace

MbDFEM::AnnuAnnuFacePair::AnnuAnnuFacePair(
    App::DocumentObject* objectI,
    std::string subNameI,
    App::DocumentObject* objectJ,
    std::string subNameJ
)
    : AnnuAnnuFacePair()
{
    faceI.setValue(objectI, std::vector<std::string> {std::move(subNameI)});
    faceJ.setValue(objectJ, std::vector<std::string> {std::move(subNameJ)});
}

bool MbDFEM::AnnuAnnuFacePair::annulusGeometry(
    const TopoDS_Face& face,
    AnnulusGeometry& geometry,
    double linearTolerance,
    double angularTolerance
)
{
    BRepAdaptor_Surface surface(face);
    if (surface.GetType() != GeomAbs_Plane) {
        return false;
    }
    std::vector<gp_Circ> circles;
    for (TopExp_Explorer wires(face, TopAbs_WIRE); wires.More(); wires.Next()) {
        const auto wire = TopoDS::Wire(wires.Current());
        if (!BRep_Tool::IsClosed(wire)) {
            return false;
        }
        bool first = true;
        gp_Circ circle;
        for (TopExp_Explorer edges(wire, TopAbs_EDGE); edges.More(); edges.Next()) {
            BRepAdaptor_Curve curve(TopoDS::Edge(edges.Current()));
            if (curve.GetType() != GeomAbs_Circle) {
                return false;
            }
            const auto edgeCircle = curve.Circle();
            if (first) {
                circle = edgeCircle;
                first = false;
            }
            else if (
                circle.Location().Distance(edgeCircle.Location()) > linearTolerance
                || std::abs(circle.Radius() - edgeCircle.Radius()) > linearTolerance
                || !parallel(circle.Axis().Direction(), edgeCircle.Axis().Direction(), angularTolerance)
            ) {
                return false;
            }
        }
        if (first || circle.Radius() <= linearTolerance) {
            return false;
        }
        // Accept circles split into several edges, but reject partial rings.
        GProp_GProps length;
        BRepGProp::LinearProperties(wire, length);
        if (std::abs(length.Mass() - 2.0 * std::acos(-1.0) * circle.Radius())
            > std::max(linearTolerance, angularTolerance * circle.Radius())) {
            return false;
        }
        circles.push_back(circle);
    }
    if (circles.size() != 2 || circles[0].Location().Distance(circles[1].Location()) > linearTolerance
        || !parallel(circles[0].Axis().Direction(), circles[1].Axis().Direction(), angularTolerance)) {
        return false;
    }
    const double inner = std::min(circles[0].Radius(), circles[1].Radius());
    const double outer = std::max(circles[0].Radius(), circles[1].Radius());
    if (outer - inner <= linearTolerance) {
        return false;
    }
    const auto& outerCircle = circles[circles[0].Radius() >= circles[1].Radius() ? 0 : 1];
    const auto center = outerCircle.Location();
    const auto axis = outerCircle.Axis().Direction();
    geometry = {
        Base::Vector3d(center.X(), center.Y(), center.Z()),
        Base::Vector3d(axis.X(), axis.Y(), axis.Z()),
        inner,
        outer
    };
    return true;
}

bool MbDFEM::AnnuAnnuFacePair::areCoplanar(
    const TopoDS_Face& first,
    const TopoDS_Face& second,
    double linearTolerance,
    double angularTolerance
)
{
    BRepAdaptor_Surface surfaceI(first), surfaceJ(second);
    if (surfaceI.GetType() != GeomAbs_Plane || surfaceJ.GetType() != GeomAbs_Plane) {
        return false;
    }
    const auto planeI = surfaceI.Plane();
    const auto planeJ = surfaceJ.Plane();
    return parallel(planeI.Axis().Direction(), planeJ.Axis().Direction(), angularTolerance)
        && planeI.Distance(planeJ.Location()) <= linearTolerance
        && planeJ.Distance(planeI.Location()) <= linearTolerance;
}

bool MbDFEM::AnnuAnnuFacePair::isAnnulusContained(
    const TopoDS_Face& annulus,
    const TopoDS_Face& other,
    double linearTolerance
)
{
    BRepAlgoAPI_Cut difference;
    difference.SetArguments({annulus});
    difference.SetTools({other});
    difference.SetFuzzyValue(linearTolerance);
    difference.SetNonDestructive(true);
    difference.Build();
    if (!difference.IsDone() || difference.HasErrors() || difference.Shape().IsNull()) {
        throw std::runtime_error("AnnuAnnuFacePair containment operation failed.");
    }
    GProp_GProps remainder;
    BRepGProp::SurfaceProperties(difference.Shape(), remainder);
    // Boundary contact is allowed. Only a residual area below the square of
    // the distance tolerance is treated as numerical debris.
    return std::abs(remainder.Mass()) <= linearTolerance * linearTolerance;
}

MbDFEM::AnnuAnnuFacePair::ValidatedGeometry MbDFEM::AnnuAnnuFacePair::validateGeometry(
    double linearTolerance,
    double angularTolerance
) const
{
    linearTolerance = checkedTolerance(linearTolerance, Precision::Confusion());
    angularTolerance = checkedTolerance(angularTolerance, Precision::Angular());
    try {
        return validateFaces(
            referencedFace(faceI, "I"),
            referencedFace(faceJ, "J"),
            linearTolerance,
            angularTolerance
        );
    }
    catch (const Standard_Failure& error) {
        throw std::runtime_error(
            std::string("AnnuAnnuFacePair geometry operation failed: ") + error.GetMessageString()
        );
    }
}

MbDFEM::AnnuAnnuFacePair::ValidatedGeometry MbDFEM::AnnuAnnuFacePair::validateFaces(
    const TopoDS_Face& first,
    const TopoDS_Face& second,
    double linearTolerance,
    double angularTolerance
)
{
    linearTolerance = checkedTolerance(linearTolerance, Precision::Confusion());
    angularTolerance = checkedTolerance(angularTolerance, Precision::Angular());
    try {
        AnnulusGeometry geometryI, geometryJ;
        const bool annulusI = annulusGeometry(first, geometryI, linearTolerance, angularTolerance);
        const bool annulusJ = annulusGeometry(second, geometryJ, linearTolerance, angularTolerance);
        if (!annulusI && !annulusJ) {
            throw std::runtime_error(
                "AnnuAnnuFacePair requires at least one complete concentric annulus face."
            );
        }
        if (!areCoplanar(first, second, linearTolerance, angularTolerance)) {
            throw std::runtime_error("AnnuAnnuFacePair faces must be coplanar.");
        }
        // Equal areas select I deterministically. Containment, not area alone,
        // determines whether the selected contact region is admissible.
        const bool selectI = annulusI && (!annulusJ || faceArea(first) <= faceArea(second));
        if (!isAnnulusContained(selectI ? first : second, selectI ? second : first, linearTolerance)) {
            throw std::runtime_error(
                "AnnuAnnuFacePair selected annulus is not completely bounded by the other face."
            );
        }
        return {selectI, selectI ? geometryI : geometryJ};
    }
    catch (const Standard_Failure& error) {
        throw std::runtime_error(
            std::string("AnnuAnnuFacePair geometry operation failed: ") + error.GetMessageString()
        );
    }
}

App::DocumentObjectExecReturn* MbDFEM::AnnuAnnuFacePair::execute()
{
    try {
        validateGeometry();
        return App::DocumentObject::StdReturn;
    }
    catch (const std::exception& error) {
        return new App::DocumentObjectExecReturn(error.what(), this);
    }
}

namespace
{
using AnnularPair = MbDFEM::AnnuAnnuFacePair;

bool finiteVector(const Base::Vector3d& value)
{
    return std::isfinite(value.x) && std::isfinite(value.y) && std::isfinite(value.z);
}

Base::Vector3d meshFallback(const Base::Vector3d& zAxis, const Base::Placement& placement)
{
    Base::Vector3d x, y;
    placement.getRotation().multVec(Base::Vector3d::UnitX, x);
    placement.getRotation().multVec(Base::Vector3d::UnitY, y);
    x -= zAxis * x.Dot(zAxis);
    y -= zAxis * y.Dot(zAxis);
    auto result = x.Sqr() >= y.Sqr() ? x : y;
    result.Normalize();
    return result;
}

struct LoadAxes
{
    Base::Vector3d fx, fy, tx, ty, z;
};

LoadAxes loadAxes(
    const Base::Vector3d& axis,
    const Base::Placement& annulusPlacement,
    const Base::Vector3d& force,
    const Base::Vector3d& torque
)
{
    LoadAxes result;
    result.z = axis;
    result.z.Normalize();
    const auto fallback = meshFallback(result.z, annulusPlacement);
    const auto torqueSide = torque - result.z * torque.Dot(result.z);
    result.ty = torqueSide.Length() > 1.0e-12 ? torqueSide : fallback;
    result.ty.Normalize();
    result.tx = result.ty.Cross(result.z);
    const auto forceSide = force - result.z * force.Dot(result.z);
    result.fx = forceSide.Length() > 1.0e-12 ? forceSide : torque.Cross(result.z);
    if (result.fx.Length() <= 1.0e-12) {
        result.fx = fallback;
    }
    result.fx.Normalize();
    result.fy = result.z.Cross(result.fx);
    return result;
}

Base::Placement loadFrame(
    const Base::Vector3d& origin,
    const Base::Vector3d& x,
    const Base::Vector3d& y,
    const Base::Vector3d& z
)
{
    Base::Matrix4D matrix;
    for (int row = 0; row < 3; ++row) {
        matrix[row][0] = x[row];
        matrix[row][1] = y[row];
        matrix[row][2] = z[row];
    }
    return Base::Placement(origin, Base::Rotation(matrix));
}

int quadrant(double x, double y)
{
    return x >= 0.0 ? (y >= 0.0 ? 0 : 3) : (y >= 0.0 ? 1 : 2);
}

std::vector<AnnularPair::CLOAD> records(
    const std::vector<AnnularPair::Node>& nodes,
    const std::vector<Base::Vector3d>& forces
)
{
    std::vector<AnnularPair::CLOAD> result;
    for (size_t i = 0; i < nodes.size(); ++i) {
        for (int dof = 0; dof < 3; ++dof) {
            if (forces[i][dof] != 0.0) {
                result.push_back({nodes[i].id, dof + 1, forces[i][dof]});
            }
        }
    }
    return result;
}

void checkAnnularWrench(
    const std::vector<AnnularPair::Node>& nodes,
    const Base::Vector3d& origin,
    const std::vector<Base::Vector3d>& forces,
    const Base::Vector3d& targetForce,
    const Base::Vector3d& targetTorque,
    double length,
    double geometricTolerance,
    const char* component
)
{
    Base::Vector3d force, torque;
    double absoluteForce = 0.0;
    for (size_t i = 0; i < nodes.size(); ++i) {
        force += forces[i];
        torque += (nodes[i].position - origin).Cross(forces[i]);
        absoluteForce += forces[i].Length();
    }
    const double forceTolerance = 1.0e-6 * std::max(1.0, targetForce.Length());
    const double torqueTolerance = 1.0e-6
            * std::max({1.0, targetTorque.Length(), targetForce.Length() * length})
        + geometricTolerance * absoluteForce;
    if (!finiteVector(force) || !finiteVector(torque) || (force - targetForce).Length() > forceTolerance
        || (torque - targetTorque).Length() > torqueTolerance) {
        throw std::runtime_error(
            std::string("Annular ") + component
            + " cannot satisfy force/moment equilibrium; refine the contact face mesh."
        );
    }
}

// One force basis per node, with a constant signed coefficient in each quadrant.
// C2 scales columns by sqrt(sum of squared basis magnitudes), including the
// nodeX bending profile. SVD handles redundant equations and checks feasibility.
std::vector<Base::Vector3d> distributeComponent(
    const std::vector<AnnularPair::Node>& nodes,
    const Base::Vector3d& origin,
    const std::vector<int>& regions,
    const std::vector<Base::Vector3d>& bases,
    const Base::Vector3d& zAxis,
    const Base::Vector3d& force,
    const Base::Vector3d& torque,
    double length,
    double tolerance,
    bool nodalCost,
    const char* name
)
{
    std::array<int, 4> counts {};
    std::array<double, 4> weights {};
    for (size_t i = 0; i < regions.size(); ++i) {
        ++counts[regions[i]];
        weights[regions[i]] += bases[i].Sqr();
    }
    for (auto& weight : weights) {
        weight = nodalCost && weight > 0.0 ? std::sqrt(weight) : 1.0;
    }
    std::array<int, 4> columns;
    columns.fill(-1);
    int active = 0;
    for (int q = 0; q < 4; ++q) {
        if (counts[q]) {
            columns[q] = active++;
        }
    }
    std::vector<Base::Vector3d> result(nodes.size());
    if (active == 0) {
        checkAnnularWrench(nodes, origin, result, force, torque, length, tolerance, name);
        return result;
    }
    Eigen::MatrixXd matrix = Eigen::MatrixXd::Zero(6, active);
    for (size_t i = 0; i < nodes.size(); ++i) {
        auto relative = nodes[i].position - origin;
        // Geometric tolerance permits tiny offsets from the contact plane.
        // Check the final wrench at the actual nodes after the planar solve.
        relative -= zAxis * relative.Dot(zAxis);
        const auto moment = relative.Cross(bases[i]);
        const double weight = weights[regions[i]];
        for (int row = 0; row < 3; ++row) {
            matrix(row, columns[regions[i]]) += bases[i][row] / weight;
            matrix(row + 3, columns[regions[i]]) += moment[row] / (length * weight);
        }
    }
    Eigen::VectorXd rhs(6);
    for (int row = 0; row < 3; ++row) {
        rhs[row] = force[row];
        rhs[row + 3] = torque[row] / length;
    }
    const Eigen::VectorXd solution
        = matrix.jacobiSvd(Eigen::ComputeThinU | Eigen::ComputeThinV).solve(rhs);
    if (!solution.allFinite()
        || (matrix * solution - rhs).norm() > 1.0e-9 * std::max(1.0, rhs.norm())) {
        throw std::runtime_error(
            std::string("Annular ") + name
            + " cannot satisfy force/moment equilibrium; refine the contact face mesh."
        );
    }
    for (size_t i = 0; i < nodes.size(); ++i) {
        const double weight = weights[regions[i]];
        result[i] = bases[i] * (solution[columns[regions[i]]] / weight);
    }
    checkAnnularWrench(nodes, origin, result, force, torque, length, tolerance, name);
    return result;
}
}  // namespace

MbDFEM::AnnuAnnuFacePair::FaceLoad MbDFEM::AnnuAnnuFacePair::distribute(
    const ValidatedGeometry& geometry,
    const Base::Placement& meshPlacement,
    const Base::Placement& annulusPlacement,
    const std::vector<Node>& input,
    const Base::Vector3d& forceOnI,
    const Base::Vector3d& torqueOnIAtOrigin,
    double sign
) const
{
    if (!finiteVector(forceOnI) || !finiteVector(torqueOnIAtOrigin)) {
        throw std::runtime_error("Annular force and torque must be finite.");
    }
    const auto axes = loadAxes(geometry.annulus.axis, annulusPlacement, forceOnI, torqueOnIAtOrigin);
    const auto inverse = meshPlacement.inverse();
    FaceLoad result;
    result.annulusIsFaceI = geometry.annulusIsFaceI;
    inverse.multVec(geometry.annulus.center, result.origin);
    const auto rotate = [&inverse](const Base::Vector3d& vector) {
        Base::Vector3d result;
        inverse.getRotation().multVec(vector, result);
        return result;
    };
    result.xAxis = rotate(axes.fx);
    result.yAxis = rotate(axes.fy);
    result.zAxis = rotate(axes.z);
    result.torqueXAxis = rotate(axes.tx);
    result.torqueYAxis = rotate(axes.ty);
    result.force = rotate(forceOnI * sign);
    result.torque = rotate(torqueOnIAtOrigin * sign);
    const double tolerance = 0.001;  // Contact-node selection distance, mm.
    std::vector<Node> nodes;
    std::unordered_set<int> ids;
    for (const auto& node : input) {
        if (node.id <= 0 || !finiteVector(node.position) || !ids.insert(node.id).second) {
            throw std::runtime_error(
                "Annular mesh nodes require distinct positive IDs and finite coordinates."
            );
        }
        const auto relative = node.position - result.origin;
        const double height = relative.Dot(result.zAxis);
        const double radius = (relative - result.zAxis * height).Length();
        if (std::abs(height) <= tolerance && radius >= geometry.annulus.innerRadius - tolerance
            && radius <= geometry.annulus.outerRadius + tolerance) {
            nodes.push_back(node);
        }
    }
    std::sort(nodes.begin(), nodes.end(), [](const auto& a, const auto& b) { return a.id < b.id; });
    std::vector<int> forceRegions, torqueRegions;
    std::vector<Base::Vector3d> fxBasis, zBasis, bendingBasis, tangentBasis;
    for (const auto& node : nodes) {
        const auto relative = node.position - result.origin;
        const auto radial = relative - result.zAxis * relative.Dot(result.zAxis);
        if (radial.Length() <= Precision::Confusion()) {
            throw std::runtime_error("Annular node has no radial direction.");
        }
        const int fq = quadrant(relative.Dot(result.xAxis), relative.Dot(result.yAxis));
        const int tq = quadrant(relative.Dot(result.torqueXAxis), relative.Dot(result.torqueYAxis));
        forceRegions.push_back(fq);
        torqueRegions.push_back(tq);
        result.forceQuadrants[fq].push_back(node.id);
        result.torqueQuadrants[tq].push_back(node.id);
        fxBasis.push_back(result.xAxis);
        zBasis.push_back(result.zAxis);
        bendingBasis.push_back(result.zAxis * relative.Dot(result.torqueXAxis));
        tangentBasis.push_back(result.zAxis.Cross(radial) / radial.Length());
    }
    const bool nodalCost = loadCost.getValue() == 1;
    const auto fx = result.xAxis * result.force.Dot(result.xAxis);
    const auto fz = result.zAxis * result.force.Dot(result.zAxis);
    const auto ty = result.torqueYAxis * result.torque.Dot(result.torqueYAxis);
    const auto tz = result.zAxis * result.torque.Dot(result.zAxis);
    const auto solve = [&](const auto& regions,
                           const auto& bases,
                           const auto& force,
                           const auto& torque,
                           const char* name) {
        return distributeComponent(
            nodes,
            result.origin,
            regions,
            bases,
            result.zAxis,
            force,
            torque,
            geometry.annulus.outerRadius,
            tolerance,
            nodalCost,
            name
        );
    };
    const auto transverse = solve(forceRegions, fxBasis, fx, Base::Vector3d(), "transverse force");
    const auto axial = solve(forceRegions, zBasis, fz, Base::Vector3d(), "axial force");
    const auto bending = solve(torqueRegions, bendingBasis, Base::Vector3d(), ty, "bending torque");
    const auto torsion = solve(torqueRegions, tangentBasis, Base::Vector3d(), tz, "axial torque");
    result.transverseForce = records(nodes, transverse);
    result.axialForce = records(nodes, axial);
    result.bendingTorque = records(nodes, bending);
    result.axialTorque = records(nodes, torsion);
    std::vector<Base::Vector3d> combined(nodes.size());
    for (size_t i = 0; i < nodes.size(); ++i) {
        combined[i] = transverse[i] + axial[i] + bending[i] + torsion[i];
    }
    checkAnnularWrench(
        nodes,
        result.origin,
        combined,
        result.force,
        result.torque,
        geometry.annulus.outerRadius,
        tolerance,
        "combined load"
    );
    result.cloads = records(nodes, combined);
    return result;
}

MbDFEM::AnnuAnnuFacePair::FaceLoad MbDFEM::AnnuAnnuFacePair::faceLoad(
    const App::GeoFeature& part,
    const std::vector<Node>& nodes,
    const Base::Vector3d& force,
    const Base::Vector3d& torque,
    const Base::Vector3d& markerOrigin
) const
{
    if (faceI.getValue() != &part && faceJ.getValue() != &part) {
        throw std::runtime_error("Requested part is not a side of the annular FacePair.");
    }
    if (!finiteVector(markerOrigin)) {
        throw std::runtime_error("Annular marker origin must be finite.");
    }
    const auto geometry = validateGeometry();
    const auto* annulusPart = freecad_cast<const App::GeoFeature*>(
        geometry.annulusIsFaceI ? faceI.getValue() : faceJ.getValue()
    );
    if (!annulusPart) {
        throw std::runtime_error("Annular face must belong to a geometric part.");
    }
    const auto placement = part.globalPlacement();
    Base::Vector3d globalForce, globalTorque, globalMarker;
    placement.getRotation().multVec(force, globalForce);
    placement.getRotation().multVec(torque, globalTorque);
    placement.multVec(markerOrigin, globalMarker);
    globalTorque += (globalMarker - geometry.annulus.center).Cross(globalForce);
    const double sign = faceI.getValue() == &part ? 1.0 : -1.0;
    return distribute(
        geometry,
        placement,
        annulusPart->globalPlacement(),
        nodes,
        globalForce * sign,
        globalTorque * sign,
        sign
    );
}

MbDFEM::AnnuAnnuFacePair::ValidatedGeometry MbDFEM::AnnuAnnuFacePair::validateSampledGeometry(
    int lower,
    int upper,
    double ratio
) const
{
    if (!std::isfinite(ratio) || ratio < 0.0 || ratio > 1.0) {
        throw std::runtime_error("Joint sample interpolation ratio must be between zero and one.");
    }
    const auto* partI = freecad_cast<MbDPart*>(faceI.getValue());
    const auto* partJ = freecad_cast<MbDPart*>(faceJ.getValue());
    if (!partI || !partJ) {
        throw std::runtime_error("Annular joint loading requires MbDPart face references.");
    }
    if (upper < 0) {
        upper = lower;
    }
    using JointLoadUtils::sampledPlacement;
    return validateFaces(
        sampledFace(faceI, "I", sampledPlacement(*partI, lower, upper, ratio)),
        sampledFace(faceJ, "J", sampledPlacement(*partJ, lower, upper, ratio)),
        -1.0,
        -1.0
    );
}

MbDFEM::AnnuAnnuFacePair::FaceLoad MbDFEM::AnnuAnnuFacePair::jointAnnulusLoad(
    const MbDJoint& joint,
    const MbDPart& part,
    const std::vector<Node>& nodes,
    const std::vector<FacePair*>& participatingPairs,
    int lower,
    int upper,
    double ratio
)
{
    return jointLoad(joint, part, nodes, participatingPairs, lower, upper, ratio, LoadSide::Annulus);
}

MbDFEM::AnnuAnnuFacePair::FaceLoad MbDFEM::AnnuAnnuFacePair::jointOtherAnnulusLoad(
    const MbDJoint& joint,
    const MbDPart& part,
    const std::vector<Node>& nodes,
    const std::vector<FacePair*>& participatingPairs,
    int lower,
    int upper,
    double ratio
)
{
    return jointLoad(joint, part, nodes, participatingPairs, lower, upper, ratio, LoadSide::Other);
}

MbDFEM::AnnuAnnuFacePair::FaceLoad MbDFEM::AnnuAnnuFacePair::jointLoad(
    const MbDJoint& joint,
    const MbDPart& part,
    const std::vector<Node>& nodes,
    const std::vector<FacePair*>& participatingPairs,
    int lower,
    int upper,
    double ratio,
    LoadSide side
)
{
    using namespace JointLoadUtils;
    if (!std::isfinite(ratio) || ratio < 0.0 || ratio > 1.0) {
        throw std::runtime_error("Joint sample interpolation ratio must be between zero and one.");
    }
    if (upper < 0) {
        upper = lower;
    }
    const auto* markerI = freecad_cast<MbDMarker*>(joint.markerI.getValue());
    const auto* markerJ = freecad_cast<MbDMarker*>(joint.markerJ.getValue());
    const auto* partI = markerPart(markerI);
    const auto* partJ = markerPart(markerJ);
    if (partI == partJ || (&part != partI && &part != partJ)) {
        throw std::runtime_error("Requested part does not identify one side of the joint.");
    }
    std::unordered_set<const FacePair*> participants;
    for (const auto* pair : participatingPairs) {
        if (pair
            && ((pair->faceI.getValue() == partI && pair->faceJ.getValue() == partJ)
                || (pair->faceI.getValue() == partJ && pair->faceJ.getValue() == partI))) {
            participants.insert(pair);
        }
    }
    if (!participants.count(this)) {
        throw std::runtime_error("Annular FacePair is not a participant of this joint.");
    }
    const auto* facePartI = freecad_cast<MbDPart*>(faceI.getValue());
    const auto* facePartJ = freecad_cast<MbDPart*>(faceJ.getValue());
    const auto placementI = sampledPlacement(*facePartI, lower, upper, ratio);
    const auto placementJ = sampledPlacement(*facePartJ, lower, upper, ratio);
    const auto geometry = validateFaces(
        sampledFace(faceI, "I", placementI),
        sampledFace(faceJ, "J", placementJ),
        -1.0,
        -1.0
    );
    const auto* annulusPart = geometry.annulusIsFaceI ? facePartI : facePartJ;
    if ((side == LoadSide::Annulus && &part != annulusPart)
        || (side == LoadSide::Other && &part == annulusPart)) {
        throw std::runtime_error(
            side == LoadSide::Annulus
                ? "Requested FacePair side is not the selected annulus."
                : "Requested FacePair side is not the other annulus contact part."
        );
    }
    const auto markerPlacement = sampledPlacement(*partI, lower, upper, ratio)
        * markerI->Placement.getValue();
    const auto sample = [=](const auto& series) {
        return (sampleValue(series, lower) * (1.0 - ratio) + sampleValue(series, upper) * ratio)
            / double(participants.size());
    };
    const bool specialized = FEMHole2PinFlangeJoint::updateParticipatingPairs(
        joint,
        participatingPairs,
        lower,
        upper,
        ratio
    );
    Base::Vector3d force, shiftedTorque;
    if (specialized) {
        force = forceOnFaceIatOrigin;
        shiftedTorque = torqueOnFaceIatOrigin;
    }
    else {
        force = Base::Vector3d(sample(joint.fxs), sample(joint.fys), sample(joint.fzs));
        const Base::Vector3d torque(sample(joint.txs), sample(joint.tys), sample(joint.tzs));
        shiftedTorque = torque * siTorqueToFEMTorque
            + (markerPlacement.getPosition() - geometry.annulus.center).Cross(force);
    }
    const auto& annulusPlacement = geometry.annulusIsFaceI ? placementI : placementJ;
    const auto meshPlacement = sampledPlacement(part, lower, upper, ratio);
    auto result = distribute(
        geometry,
        meshPlacement,
        annulusPlacement,
        nodes,
        force,
        shiftedTorque,
        &part == partI ? 1.0 : -1.0
    );
    const auto axes = loadAxes(geometry.annulus.axis, annulusPlacement, force, shiftedTorque);
    forceOnFaceIatOrigin = force;
    torqueOnFaceIatOrigin = shiftedTorque;
    forceCoord = loadFrame(geometry.annulus.center, axes.fx, axes.fy, axes.z);
    torqueCoord = loadFrame(geometry.annulus.center, axes.tx, axes.ty, axes.z);
    coordsOnFace = geometry.annulusIsFaceI ? IJUkn::I : IJUkn::J;
    return result;
}
