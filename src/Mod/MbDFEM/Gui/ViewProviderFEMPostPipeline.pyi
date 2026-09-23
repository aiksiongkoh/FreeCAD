# SPDX-License-Identifier: LGPL-2.1-or-later

from Base.Metadata import export
from FemGui.ViewProviderFemPostPipeline import ViewProviderFemPostPipeline


@export(
    Include="Mod/MbDFEM/Gui/ViewProviderFEMPostPipeline.h",
    Namespace="MbDFEMGui",
    FatherInclude="Mod/Fem/Gui/ViewProviderFemPostPipelinePy.h",
    FatherNamespace="FemGui",
)
class ViewProviderFEMPostPipeline(ViewProviderFemPostPipeline):
    """FEM result display with MbDFEM contour and legend controls."""

    def updateColorBars(self) -> None:
        """Refresh the colors while preserving MbDFEM display options."""
        ...
