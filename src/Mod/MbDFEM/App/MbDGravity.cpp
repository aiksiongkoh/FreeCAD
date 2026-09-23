// SPDX-License-Identifier: LGPL-2.1-or-later

#include "MbDGravity.h"

PROPERTY_SOURCE(MbDFEM::MbDGravity, App::DocumentObject)

MbDFEM::MbDGravity::MbDGravity()
{
    ADD_PROPERTY_TYPE(gravity,
                      (Base::Vector3d(0.0, 0.0, -9810.0)),
                      "MbDFEM",
                      App::Prop_None,
                      "Gravity acceleration vector for this assembly (mm/s^2)");
}
