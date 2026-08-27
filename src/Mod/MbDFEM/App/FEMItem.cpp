// SPDX-License-Identifier: LGPL-2.1-or-later

#include "FEMItem.h"

PROPERTY_SOURCE(MbDFEM::FEMItem, App::DocumentObject)

MbDFEM::FEMItem::FEMItem()
{
    ADD_PROPERTY_TYPE(mbdItem,
                      (nullptr),
                      "MbDFEM",
                      App::Prop_None,
                      "Multibody item represented by this FEM item");
    mbdItem.setScope(App::LinkScope::Global);
}
