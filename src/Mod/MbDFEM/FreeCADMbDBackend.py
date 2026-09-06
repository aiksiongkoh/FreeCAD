# SPDX-License-Identifier: LGPL-2.1-or-later

"""Process backend for running FreeCADMbD from MbDFEM."""

import os
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

import FreeCAD as App

import FreeCADMbDExporter
import FreeCADMbDResults


PREF_GROUP = "User parameter:BaseApp/Preferences/Mod/MbDFEM"
EXE_PREF = "FreeCADMbDExecutable"
CASE_DIR_NAME = "Case001"
CALCULIX_BASE_NAME = "calculix"
FRAME_DIR_DIGITS = 6
FEM_FILE_EXTENSIONS = (".inp", ".dat", ".frd", ".sta", ".cvg", ".log")


@dataclass
class SolveResult:
    asmt_file: str
    result_file: str | None
    return_code: int
    stdout: str
    stderr: str


class FreeCADMbDProcessBackend:
    """Run FreeCADMbD as a separate process."""

    def __init__(self, executable_path=None, work_dir=None, timeout=None):
        self.executable_path = executable_path or configured_executable()
        self.work_dir = Path(work_dir) if work_dir else None
        self.timeout = timeout

    def solve(self, assembly, asmt_file=None):
        asmt_path = Path(asmt_file) if asmt_file else default_asmt_path(assembly)
        asmt_path.parent.mkdir(parents=True, exist_ok=True)
        FreeCADMbDExporter.export_assembly(assembly, asmt_path)

        solved_asmt_path, completed = self.simulate_asmt(asmt_path)

        if solved_asmt_path.exists():
            FreeCADMbDResults.import_results(assembly, solved_asmt_path)

        return SolveResult(
            asmt_file=str(asmt_path),
            result_file=str(solved_asmt_path) if solved_asmt_path.exists() else None,
            return_code=completed.returncode,
            stdout=completed.stdout,
            stderr=completed.stderr,
        )

    def simulate_asmt(self, asmt_file, solved_asmt_file=None):
        """Run FreeCADMbD on an existing ASMT file without importing results."""
        if not self.executable_path:
            raise RuntimeError(
                "FreeCADMbD executable is not configured. Set the MbDFEM "
                f"preference '{EXE_PREF}' or the FREECADMBD_EXE environment variable."
            )

        executable = Path(self.executable_path)
        if not executable.exists():
            raise RuntimeError(f"FreeCADMbD executable does not exist: {executable}")

        asmt_path = Path(asmt_file)
        solved_asmt_path = Path(solved_asmt_file) if solved_asmt_file else asmt_path.with_suffix(".solved.asmt")
        command = [str(executable), str(asmt_path), str(solved_asmt_path)]
        completed = subprocess.run(
            command,
            cwd=str(self.work_dir or asmt_path.parent),
            text=True,
            capture_output=True,
            timeout=self.timeout,
            check=False,
        )

        if completed.returncode != 0:
            raise RuntimeError(
                "FreeCADMbD solve failed with exit code "
                f"{completed.returncode}.\n"
                f"Command: {' '.join(command)}\n"
                f"Working directory: {self.work_dir or asmt_path.parent}\n"
                f"ASMT file: {asmt_path}\n"
                f"stdout:\n{completed.stdout.strip()}\n"
                f"stderr:\n{completed.stderr.strip()}"
            )

        return solved_asmt_path, completed


def configured_executable():
    env_path = os.environ.get("FREECADMBD_EXE")
    if env_path:
        return env_path

    parameter_group = App.ParamGet(PREF_GROUP)
    configured = parameter_group.GetString(EXE_PREF, "")
    if configured:
        return configured

    return shutil.which("FreeCADMbD.exe") or shutil.which("FreeCADMbD")


def default_asmt_path(assembly):
    return default_case_dir(assembly) / "MbDAssembly.asmt"


def default_calculix_working_dir(fem_part, state_index):
    frame_name = f"Frame{int(state_index):0{FRAME_DIR_DIGITS}d}"
    path = default_case_dir(fem_part) / _fem_part_directory_name(fem_part) / frame_name
    path.mkdir(parents=True, exist_ok=True)
    return path


def asmt_freshness_warning(document, asmt_file):
    document_file = _document_file_path(document)
    if document_file is None:
        return ""
    return file_freshness_warning(
        asmt_file,
        document_file,
        "ASMT file",
        "FCStd file",
    )


def fem_files_freshness_warning(fem_part, state_index, asmt_file=None):
    asmt_path = Path(asmt_file) if asmt_file else default_asmt_path(fem_part)
    fem_files = existing_calculix_files(fem_part, state_index)
    stale_files = [path for path in fem_files if not _is_more_recent(path, asmt_path)]
    if not stale_files:
        return ""

    stale_list = "\n".join(str(path) for path in stale_files)
    return (
        "The FEM files for this state are older than the ASMT file.\n\n"
        f"ASMT file:\n{asmt_path}\n\n"
        f"Older FEM file(s):\n{stale_list}\n\n"
        "The displayed FEM results may not match the current MbD simulation."
    )


def existing_calculix_files(fem_part, state_index):
    working_dir = default_calculix_working_dir(fem_part, state_index)
    return [
        working_dir / f"{CALCULIX_BASE_NAME}{extension}"
        for extension in FEM_FILE_EXTENSIONS
        if (working_dir / f"{CALCULIX_BASE_NAME}{extension}").is_file()
    ]


def file_freshness_warning(file_path, reference_path, file_label, reference_label):
    file_path = Path(file_path)
    reference_path = Path(reference_path)
    if _is_more_recent(file_path, reference_path):
        return ""
    return (
        f"The {file_label} is not newer than the {reference_label}.\n\n"
        f"{file_label}:\n{file_path}\n\n"
        f"{reference_label}:\n{reference_path}\n\n"
        "The input may be stale."
    )


def _document_file_path(document):
    filename = getattr(document, "FileName", "") if document is not None else ""
    if not filename:
        return None
    path = Path(filename)
    return path if path.is_file() else None


def _is_more_recent(file_path, reference_path):
    file_path = Path(file_path)
    reference_path = Path(reference_path)
    try:
        return file_path.stat().st_mtime > reference_path.stat().st_mtime
    except OSError:
        return True


def default_case_dir(obj):
    document = getattr(obj, "Document", None)
    path = _document_project_dir(document) / "MbDFEM" / CASE_DIR_NAME
    path.mkdir(parents=True, exist_ok=True)
    return path


def _document_project_dir(document):
    if document and document.FileName:
        return Path(document.FileName).with_suffix("")

    document_name = _safe_path_part(getattr(document, "Name", "") or "Unsaved")
    return Path(tempfile.gettempdir()) / "FreeCAD" / "MbDFEM" / document_name


def _fem_part_directory_name(fem_part):
    mbd_part = getattr(fem_part, "mbdItem", None)
    name = getattr(mbd_part, "Name", None) or getattr(fem_part, "Name", "") or "FEMPart"
    return _safe_path_part(name)


def _safe_path_part(value):
    safe = re.sub(r"[^A-Za-z0-9_.-]+", "_", str(value)).strip("._")
    return safe or "Unnamed"
