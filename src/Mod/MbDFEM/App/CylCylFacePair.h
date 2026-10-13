// SPDX-License-Identifier: LGPL-2.1-or-later

#pragma once

#include "FacePair.h"

#include <Base/Vector3D.h>
#include <App/PropertyStandard.h>

#include <string>
#include <vector>
#include <array>

namespace MbDFEM
{
class MbDJoint;
class MbDPart;

class MbDFEMExport CylCylFacePair: public FacePair
{
    PROPERTY_HEADER_WITH_OVERRIDE(MbDFEM::CylCylFacePair);

public:
    // C minimizes region coefficients; C2 minimizes all nodal force magnitudes.
    App::PropertyEnumeration loadCost;
    static const char* LoadCostEnums[];

    enum class CylindricalFaceRole
    {
        Unknown,
        Hole,
        Pin
    };

    struct CylindricalFaceGeometry
    {
        Base::Vector3d axisPoint;
        Base::Vector3d axisDirection;
        double axialMin = 0.0;
        double axialMax = 0.0;
        Base::Vector3d samplePoint;
        Base::Vector3d outwardNormal;
    };

    struct FaceRoles
    {
        CylindricalFaceRole faceI = CylindricalFaceRole::Unknown;
        CylindricalFaceRole faceJ = CylindricalFaceRole::Unknown;

        bool hasHoleAndPin() const;
        bool faceIIsHole() const;
        bool faceJIsHole() const;
    };

    struct HoleNode
    {
        int id = 0;
        Base::Vector3d position;
    };

    struct NodalForce
    {
        int nodeId = 0;
        Base::Vector3d force;
    };

    struct CLOAD
    {
        int nodeId = 0;
        int dof = 0;
        double value = 0.0;
    };

    struct HoleLoadComponents
    {
        std::vector<CLOAD> transverseForce;
        std::vector<CLOAD> axialForce;
        std::vector<CLOAD> bendingTorque;
        std::vector<CLOAD> axialTorque;
    };

    struct JointHoleLoad
    {
        Base::Vector3d origin, xAxis, yAxis, zAxis;
        Base::Vector3d force, torque;
        std::array<std::vector<int>, 8> octants;
        HoleLoadComponents components;
    };

    // Refresh the FacePair's global frames and share of the marker-I reaction for this
    // sample. The hole defines the common origin/Z axis for either joint side.
    void updateJointState(
        const MbDJoint& joint,
        int lower = -1,
        int upper = -1,
        double ratio = 0.0,
        int participatingPairCount = 1
    );

    // Finalized domain entry point: geometry, reaction sampling/sign, frame
    // conversion, joint-specific sharing, moment transfer, discretization and validation.
    // lower < 0 uses current placements and the first reaction sample.
    JointHoleLoad jointHoleLoad(
        const MbDJoint& joint,
        const MbDPart& part,
        const std::vector<HoleNode>& nodes,
        const std::vector<FacePair*>& participatingPairs,
        int lower = -1,
        int upper = -1,
        double ratio = 0.0
    );

    // Loads pin nodes touching the sampled hole face, using the common hole
    // origin/axis and contact regions, with opposite nodal tractions.
    JointHoleLoad jointPinLoad(
        const MbDJoint& joint,
        const MbDPart& part,
        const std::vector<HoleNode>& nodes,
        const std::vector<FacePair*>& participatingPairs,
        int lower = -1,
        int upper = -1,
        double ratio = 0.0
    );

    struct PinCoverage
    {
        bool hasGeometry = false;
        bool coversHole = false;
        double holeZMin = 0.0;
        double holeZMax = 0.0;
        double pinZMin = 0.0;
        double pinZMax = 0.0;
    };

    CylCylFacePair();
    CylCylFacePair(
        App::DocumentObject* objectI,
        std::string subNameI,
        App::DocumentObject* objectJ,
        std::string subNameJ
    );

    static CylindricalFaceRole cylindricalFaceRole(
        const CylindricalFaceGeometry& geometry,
        double tolerance = -1.0
    );
    static FaceRoles classifyFaces(
        const CylindricalFaceGeometry& faceIGeometry,
        const CylindricalFaceGeometry& faceJGeometry,
        double tolerance = -1.0
    );

    std::vector<HoleNode> holeSurfaceNodes(
        const std::vector<HoleNode>& nodes,
        const Base::Vector3d& holeCenter,
        const Base::Vector3d& holeAxis,
        double holeRadius,
        double axialMin,
        double axialMax,
        double tolerance = -1.0
    ) const;

    void updatePinCoverage(
        const CylindricalFaceGeometry& faceIGeometry,
        const CylindricalFaceGeometry& faceJGeometry,
        double tolerance = -1.0
    );

    std::vector<NodalForce> holeNodalForces(
        const std::vector<HoleNode>& nodes,
        const Base::Vector3d& holeCenter,
        const Base::Vector3d& holeAxis,
        double holeRadius,
        double axialMin,
        double axialMax,
        const Base::Vector3d& centerForce,
        double tolerance = -1.0
    ) const;

    std::vector<NodalForce> holeAxisNodalForces(
        const std::vector<HoleNode>& nodes,
        const Base::Vector3d& holeCenter,
        const Base::Vector3d& holeAxis,
        const Base::Vector3d& forceXAxis,
        double holeRadius,
        double axialMin,
        double axialMax,
        double forceAxis,
        double tolerance = -1.0
    ) const;

    std::vector<CLOAD> holeCLOADs(
        const std::vector<HoleNode>& nodes,
        const Base::Vector3d& holeCenter,
        const Base::Vector3d& holeAxis,
        double holeRadius,
        double axialMin,
        double axialMax,
        const Base::Vector3d& centerForce,
        double tolerance = -1.0
    ) const;

    std::vector<CLOAD> holeAxisCLOADs(
        const std::vector<HoleNode>& nodes,
        const Base::Vector3d& holeCenter,
        const Base::Vector3d& holeAxis,
        const Base::Vector3d& forceXAxis,
        double holeRadius,
        double axialMin,
        double axialMax,
        double forceAxis,
        double tolerance = -1.0
    ) const;

    // All vectors and the torque reference point are in mesh coordinates.
    // Throws if any requested component cannot be represented in equilibrium.
    // Contributions remain separate even when they share a node and DOF.
    HoleLoadComponents holeCLOADs(
        const std::vector<HoleNode>& nodes,
        const Base::Vector3d& holeCenter,
        const Base::Vector3d& holeAxis,
        double holeRadius,
        double axialMin,
        double axialMax,
        const Base::Vector3d& centerForce,
        const Base::Vector3d& centerTorque,
        double tolerance = -1.0
    ) const;

    PinCoverage pinCoverage;
    std::string pinCoverageWarning;

private:
    JointHoleLoad jointLoad(
        const MbDJoint& joint,
        const MbDPart& part,
        const std::vector<HoleNode>& nodes,
        const std::vector<FacePair*>& participatingPairs,
        int lower,
        int upper,
        double ratio,
        bool holeSide
    );
    static bool solve3x3(double matrix[3][3], const double rhs[3], double solution[3], double tolerance);
};

}  // namespace MbDFEM
