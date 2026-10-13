// SPDX-License-Identifier: LGPL-2.1-or-later

#pragma once

#include "FacePair.h"

#include <Base/Vector3D.h>
#include <App/PropertyStandard.h>

#include <array>
#include <vector>

class TopoDS_Face;
namespace App
{
class GeoFeature;
}

namespace MbDFEM
{
class MbDJoint;
class MbDPart;

class MbDFEMExport AnnuAnnuFacePair: public FacePair
{
    PROPERTY_HEADER_WITH_OVERRIDE(MbDFEM::AnnuAnnuFacePair);

public:
    struct AnnulusGeometry
    {
        Base::Vector3d center;
        Base::Vector3d axis;
        double innerRadius = 0.0;
        double outerRadius = 0.0;
    };

    struct ValidatedGeometry
    {
        bool annulusIsFaceI = false;
        AnnulusGeometry annulus;
    };

    // C minimizes quadrant coefficients; C2 minimizes all nodal magnitudes.
    App::PropertyEnumeration loadCost;
    static const char* LoadCostEnums[];

    struct Node
    {
        int id = 0;
        Base::Vector3d position;
    };

    struct CLOAD
    {
        int nodeId = 0;
        int dof = 0;
        double value = 0.0;
    };

    struct FaceLoad
    {
        Base::Vector3d origin, xAxis, yAxis, zAxis;
        Base::Vector3d torqueXAxis, torqueYAxis;
        Base::Vector3d force, torque;
        std::array<std::vector<int>, 4> forceQuadrants, torqueQuadrants;
        std::vector<CLOAD> transverseForce, axialForce, bendingTorque, axialTorque;
        // Contributions coalesced into one record per node and DOF for export.
        std::vector<CLOAD> cloads;
        bool annulusIsFaceI = false;
    };

    AnnuAnnuFacePair();
    AnnuAnnuFacePair(
        App::DocumentObject* objectI,
        std::string subNameI,
        App::DocumentObject* objectJ,
        std::string subNameJ
    );

    // Resolves current face references in assembly coordinates. Throws with a
    // diagnostic if the pair is invalid. Call before distributing joint loads;
    // the result must not be cached across shape or placement changes.
    ValidatedGeometry validateGeometry(
        double linearTolerance = -1.0,
        double angularTolerance = -1.0
    ) const;
    ValidatedGeometry validateSampledGeometry(int lower = -1, int upper = -1, double ratio = 0.0) const;

    App::DocumentObjectExecReturn* execute() override;

    // Supplied wrench, origin and nodes are in the referenced part's mesh
    // coordinates. The torque is about markerOrigin, before moment transfer.
    FaceLoad faceLoad(
        const App::GeoFeature& part,
        const std::vector<Node>& nodes,
        const Base::Vector3d& force,
        const Base::Vector3d& torque,
        const Base::Vector3d& markerOrigin
    ) const;

    // Role-specific entry points. Annulus means the selected contact annulus,
    // including when both referenced faces are annular.
    FaceLoad jointAnnulusLoad(
        const MbDJoint& joint,
        const MbDPart& part,
        const std::vector<Node>& nodes,
        const std::vector<FacePair*>& participatingPairs,
        int lower = -1,
        int upper = -1,
        double ratio = 0.0
    );
    FaceLoad jointOtherAnnulusLoad(
        const MbDJoint& joint,
        const MbDPart& part,
        const std::vector<Node>& nodes,
        const std::vector<FacePair*>& participatingPairs,
        int lower = -1,
        int upper = -1,
        double ratio = 0.0
    );

private:
    enum class LoadSide
    {
        Annulus,
        Other
    };
    FaceLoad jointLoad(
        const MbDJoint& joint,
        const MbDPart& part,
        const std::vector<Node>& nodes,
        const std::vector<FacePair*>& participatingPairs,
        int lower,
        int upper,
        double ratio,
        LoadSide side
    );
    static ValidatedGeometry validateFaces(
        const TopoDS_Face& first,
        const TopoDS_Face& second,
        double linearTolerance,
        double angularTolerance
    );
    FaceLoad distribute(
        const ValidatedGeometry& geometry,
        const Base::Placement& meshPlacement,
        const Base::Placement& annulusPlacement,
        const std::vector<Node>& nodes,
        const Base::Vector3d& forceOnI,
        const Base::Vector3d& torqueOnIAtOrigin,
        double sign
    ) const;
    static bool annulusGeometry(
        const TopoDS_Face& face,
        AnnulusGeometry& geometry,
        double linearTolerance,
        double angularTolerance
    );
    static bool areCoplanar(
        const TopoDS_Face& faceI,
        const TopoDS_Face& faceJ,
        double linearTolerance,
        double angularTolerance
    );
    static bool isAnnulusContained(
        const TopoDS_Face& annulus,
        const TopoDS_Face& other,
        double linearTolerance
    );
};

}  // namespace MbDFEM
