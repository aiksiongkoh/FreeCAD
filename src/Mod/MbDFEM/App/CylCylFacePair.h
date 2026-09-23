// SPDX-License-Identifier: LGPL-2.1-or-later

#pragma once

#include "FacePair.h"

#include <Base/Vector3D.h>

#include <string>
#include <vector>

class TopoDS_Face;

namespace MbDFEM
{

class MbDFEMExport CylCylFacePair: public FacePair
{
    PROPERTY_HEADER_WITH_OVERRIDE(MbDFEM::CylCylFacePair);

public:
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

    struct PinCoverage
    {
        bool hasGeometry = false;
        bool coversHole = false;
        double holeZMin = 0.0;
        double holeZMax = 0.0;
        double pinZMin = 0.0;
        double pinZMax = 0.0;
    };

    CylCylFacePair() = default;
    CylCylFacePair(App::DocumentObject* objectI,
                   std::string subNameI,
                   App::DocumentObject* objectJ,
                   std::string subNameJ);

    static CylindricalFaceRole cylindricalFaceRole(const CylindricalFaceGeometry& geometry,
                                                  double tolerance = -1.0);
    static FaceRoles classifyFaces(const CylindricalFaceGeometry& faceIGeometry,
                                   const CylindricalFaceGeometry& faceJGeometry,
                                   double tolerance = -1.0);

    std::vector<HoleNode> holeSurfaceNodes(const std::vector<HoleNode>& nodes,
                                           const Base::Vector3d& holeCenter,
                                           const Base::Vector3d& holeAxis,
                                           double holeRadius,
                                           double axialMin,
                                           double axialMax,
                                           double tolerance = -1.0) const;

    void updatePinCoverage(const CylindricalFaceGeometry& faceIGeometry,
                           const CylindricalFaceGeometry& faceJGeometry,
                           double tolerance = -1.0);

    std::vector<NodalForce> holeNodalForces(const std::vector<HoleNode>& nodes,
                                            const Base::Vector3d& holeCenter,
                                            const Base::Vector3d& holeAxis,
                                            double holeRadius,
                                            double axialMin,
                                            double axialMax,
                                            const Base::Vector3d& centerForce,
                                            double tolerance = -1.0) const;

    std::vector<NodalForce> holeAxisNodalForces(const std::vector<HoleNode>& nodes,
                                                const Base::Vector3d& holeCenter,
                                                const Base::Vector3d& holeAxis,
                                                const Base::Vector3d& forceXAxis,
                                                double holeRadius,
                                                double axialMin,
                                                double axialMax,
                                                double forceAxis,
                                                double tolerance = -1.0) const;

    std::vector<CLOAD> holeCLOADs(const std::vector<HoleNode>& nodes,
                                  const Base::Vector3d& holeCenter,
                                  const Base::Vector3d& holeAxis,
                                  double holeRadius,
                                  double axialMin,
                                  double axialMax,
                                  const Base::Vector3d& centerForce,
                                  double tolerance = -1.0) const;

    std::vector<CLOAD> holeAxisCLOADs(const std::vector<HoleNode>& nodes,
                                      const Base::Vector3d& holeCenter,
                                      const Base::Vector3d& holeAxis,
                                      const Base::Vector3d& forceXAxis,
                                      double holeRadius,
                                      double axialMin,
                                      double axialMax,
                                      double forceAxis,
                                      double tolerance = -1.0) const;

    std::vector<NodalForce> pinNodalForces(const std::vector<HoleNode>& pinNodes,
                                           const Base::Vector3d& pinCenter,
                                           const Base::Vector3d& pinAxis,
                                           double pinRadius,
                                           double pinAxialMin,
                                           double pinAxialMax,
                                           const TopoDS_Face& holeContactFace,
                                           const Base::Vector3d& pinForceFrameOrigin,
                                           const Base::Vector3d& pinForceFrameXAxis,
                                           const Base::Vector3d& pinForceFrameYAxis,
                                           const Base::Vector3d& pinForceFrameZAxis,
                                           const Base::Vector3d& forceOnPin,
                                           double tolerance = -1.0) const;

    std::vector<NodalForce> pinAxisNodalForces(const std::vector<HoleNode>& pinNodes,
                                               const Base::Vector3d& pinCenter,
                                               const Base::Vector3d& pinAxis,
                                               double pinRadius,
                                               double pinAxialMin,
                                               double pinAxialMax,
                                               const TopoDS_Face& holeContactFace,
                                               const Base::Vector3d& pinForceFrameOrigin,
                                               const Base::Vector3d& pinForceFrameXAxis,
                                               const Base::Vector3d& pinForceFrameYAxis,
                                               const Base::Vector3d& pinForceFrameZAxis,
                                               double forceOnPinAxis,
                                               double tolerance = -1.0) const;

    std::vector<CLOAD> pinCLOADs(const std::vector<HoleNode>& pinNodes,
                                 const Base::Vector3d& pinCenter,
                                 const Base::Vector3d& pinAxis,
                                 double pinRadius,
                                 double pinAxialMin,
                                 double pinAxialMax,
                                 const TopoDS_Face& holeContactFace,
                                 const Base::Vector3d& pinForceFrameOrigin,
                                 const Base::Vector3d& pinForceFrameXAxis,
                                 const Base::Vector3d& pinForceFrameYAxis,
                                 const Base::Vector3d& pinForceFrameZAxis,
                                 const Base::Vector3d& forceOnPin,
                                 double tolerance = -1.0) const;

    std::vector<CLOAD> pinAxisCLOADs(const std::vector<HoleNode>& pinNodes,
                                     const Base::Vector3d& pinCenter,
                                     const Base::Vector3d& pinAxis,
                                     double pinRadius,
                                     double pinAxialMin,
                                     double pinAxialMax,
                                     const TopoDS_Face& holeContactFace,
                                     const Base::Vector3d& pinForceFrameOrigin,
                                     const Base::Vector3d& pinForceFrameXAxis,
                                     const Base::Vector3d& pinForceFrameYAxis,
                                     const Base::Vector3d& pinForceFrameZAxis,
                                     double forceOnPinAxis,
                                     double tolerance = -1.0) const;

    PinCoverage pinCoverage;
    std::string pinCoverageWarning;

private:
    static bool solve3x3(double matrix[3][3], const double rhs[3], double solution[3], double tolerance);
};

}  // namespace MbDFEM
