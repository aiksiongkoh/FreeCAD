// SPDX-License-Identifier: LGPL-2.1-or-later

#pragma once

#include <Base/Vector3D.h>
#include <Mod/MbDFEM/MbDFEMGlobal.h>

namespace Fem
{
class FemMesh;
}

namespace MbDFEM
{

MbDFEMExport Base::Vector3d elementCentroidLocal(const Fem::FemMesh& mesh, int elementId);

}  // namespace MbDFEM
