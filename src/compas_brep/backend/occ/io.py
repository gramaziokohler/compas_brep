"""OCC file import/export."""

from __future__ import annotations

from typing import TYPE_CHECKING
from typing import Any

from .conversion import brep_to_occ
from .conversion import occ_to_brep

if TYPE_CHECKING:
    from compas_brep.brep import Brep


def occ_to_step(brep: Brep, filepath: str, **kwargs: Any) -> None:
    """Export a Brep to a STEP file."""
    from OCP.IFSelect import IFSelect_RetDone
    from OCP.STEPControl import STEPControl_AsIs
    from OCP.STEPControl import STEPControl_Writer

    shape = brep_to_occ(brep)
    writer = STEPControl_Writer()
    writer.Transfer(shape, STEPControl_AsIs)
    status = writer.Write(str(filepath))
    if status != IFSelect_RetDone:
        raise RuntimeError(f"Failed to write STEP file: {filepath}")


def occ_from_step(filepath: str) -> Brep:
    """Import a Brep from a STEP file."""
    from OCP.IFSelect import IFSelect_RetDone
    from OCP.STEPControl import STEPControl_Reader

    reader = STEPControl_Reader()
    status = reader.ReadFile(str(filepath))
    if status != IFSelect_RetDone:
        raise RuntimeError(f"Failed to read STEP file: {filepath}")
    reader.TransferRoots()
    shape = reader.OneShape()
    return occ_to_brep(shape)


def occ_to_stl(brep: Brep, filepath: str, linear_deflection: float = 1e-3, angular_deflection: float = 0.5) -> None:
    """Export a Brep to an STL file."""
    from OCP.BRepMesh import BRepMesh_IncrementalMesh
    from OCP.StlAPI import StlAPI_Writer

    shape = brep_to_occ(brep)
    BRepMesh_IncrementalMesh(shape, linear_deflection, True, angular_deflection)
    writer = StlAPI_Writer()
    writer.Write(shape, str(filepath))


def occ_to_iges(brep: Brep, filepath: str) -> None:
    """Export a Brep to an IGES file."""
    from OCP.IGESControl import IGESControl_Writer

    shape = brep_to_occ(brep)
    writer = IGESControl_Writer()
    writer.AddShape(shape)
    writer.Write(str(filepath))


def occ_from_iges(filepath: str) -> Brep:
    """Import a Brep from an IGES file."""
    from OCP.IGESControl import IGESControl_Reader

    reader = IGESControl_Reader()
    reader.ReadFile(str(filepath))
    reader.TransferRoots()
    shape = reader.OneShape()
    return occ_to_brep(shape)
