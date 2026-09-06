# SPDX-License-Identifier: LGPL-2.1-or-later

from Base.Metadata import export
from Base.Vector import Vector
from App.DocumentObject import DocumentObject
from PartFeature import PartFeature


@export(
    Include="Mod/MbDFEM/App/FEMPart.h",
    Namespace="MbDFEM",
    FatherInclude="Mod/Part/App/PartFeaturePy.h",
    FatherNamespace="Part",
)
class FEMPart(PartFeature):
    """A FEM representation of an MbD part."""

    def elementCentroidLocal(self, element_id: int, /) -> Vector:
        """Return the linked FEM element corner-node centroid in this FEM part's local coordinates."""
        ...

    def elementCentroidGlobal(self, element_id: int, /) -> Vector:
        """Return the linked FEM element corner-node centroid in global coordinates."""
        ...

    def resultForState(self, state_index: int, /) -> object:
        """Return the FEM result whose list index corresponds to an MbD solved state index."""
        ...

    def validateResultSeries(self) -> None:
        """Require FEM results to match the linked MbDPart state series and MbDAssembly times."""
        ...

    def getResultsFolder(self) -> DocumentObject:
        """Return the lightweight Results tree folder."""
        ...

    def ensureResultsFolder(self) -> DocumentObject:
        """Create and return the lightweight Results tree folder."""
        ...

    def synchronizeResultsFolder(self) -> None:
        """Synchronize the Results tree folder with the ordered results link list."""
        ...
