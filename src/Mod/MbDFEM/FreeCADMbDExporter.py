# SPDX-License-Identifier: LGPL-2.1-or-later

"""Compatibility wrapper for C++ FreeCADMbD ASMT export."""

from pathlib import Path

import MbDFEM


def export_assembly(assembly, filename):
    """Write *assembly* to *filename* as native ASMT text and return the path."""
    Path(filename).parent.mkdir(parents=True, exist_ok=True)
    return MbDFEM.exportAssemblyAsmt(assembly, str(filename))
