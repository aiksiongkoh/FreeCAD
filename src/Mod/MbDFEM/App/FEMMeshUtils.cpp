// SPDX-License-Identifier: LGPL-2.1-or-later

#include "FEMMeshUtils.h"

#include <Base/Exception.h>
#include <Mod/Fem/App/FemMesh.h>
#include <SMDS_MeshElement.hxx>
#include <SMDS_MeshNode.hxx>
#include <SMESHDS_Mesh.hxx>
#include <SMESH_Mesh.hxx>

Base::Vector3d MbDFEM::elementCentroidLocal(const Fem::FemMesh& mesh, int elementId)
{
    const SMESH_Mesh* smesh = mesh.getSMesh();
    if (!smesh || !smesh->GetMeshDS()) {
        throw Base::ValueError("elementCentroidLocal requires a valid FEM mesh");
    }

    const SMDS_MeshElement* element = smesh->GetMeshDS()->FindElement(elementId);
    if (!element) {
        throw Base::ValueError("No FEM element found for the given element id");
    }

    const int nodeCount = element->NbCornerNodes();
    if (nodeCount <= 0) {
        throw Base::ValueError("FEM element has no corner nodes");
    }

    // Use SMESH corner nodes so quadratic midside nodes do not bias this topology centroid.
    const Base::Matrix4D transform = mesh.getTransform();
    Base::Vector3d centroid;
    for (int i = 0; i < nodeCount; ++i) {
        const SMDS_MeshNode* node = element->GetNode(i);
        if (!node) {
            throw Base::ValueError("FEM element references an invalid node");
        }

        Base::Vector3d position(node->X(), node->Y(), node->Z());
        transform.multVec(position, position);
        centroid += position;
    }

    centroid /= static_cast<double>(nodeCount);
    return centroid;
}
