// SPDX-License-Identifier: LGPL-2.1-or-later

#pragma once

#include <App/DocumentObject.h>
#include <App/PropertyLinks.h>
#include <Base/Placement.h>
#include <Base/Vector3D.h>
#include <Mod/MbDFEM/MbDFEMGlobal.h>

#include <string>

namespace MbDFEM
{

class MbDFEMExport FacePair: public App::DocumentObject
{
    PROPERTY_HEADER_WITH_OVERRIDE(MbDFEM::FacePair);

public:
    enum class IJUkn
    {
        I,
        J,
        Unknown
    };

    FacePair();
    ~FacePair() override = default;

    FacePair(
        App::DocumentObject* objectI,
        std::string subNameI,
        App::DocumentObject* objectJ,
        std::string subNameJ
    );

    App::PropertyLinkSub faceI;
    App::PropertyLinkSub faceJ;

    // Coordinate frames and reaction vectors expressed in global coordinates.
    // Loads on the marker-I part at forceCoord's origin, in global coordinates.
    Base::Vector3d forceOnFaceIatOrigin {};   // N.
    Base::Vector3d torqueOnFaceIatOrigin {};  // N mm.
    Base::Placement forceCoord {};            // Origin and orientation of the force frame.
    Base::Placement torqueCoord {};           // Origin and orientation of the torque frame.
    IJUkn coordsOnFace = IJUkn::Unknown;      // Face supplying the geometry for both frames.
};

}  // namespace MbDFEM
