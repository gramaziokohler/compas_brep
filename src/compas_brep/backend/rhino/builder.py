"""Low-level Rhino Brep construction.

Ported from ``compas_rhino.geometry.brep.builder._RhinoBrepBuilder``.

Faces are assembled through RhinoCommon's low-level API — ``AddSurface``,
``Faces.Add``, ``AddEdgeCurve``, ``AddTrimCurve``, ``Trims.Add``,
``Trims.AddSingularTrim`` — rather than by calling ``ToBrep()`` on a surface and
stitching the results with ``JoinBreps``. Only that path can represent a
genuinely trimmed face; see ADR-0002.

Edges are shared by index rather than rediscovered by proximity, so the builder
runs at ``TOL.absolute`` and has no join tolerance to fudge.
"""

from __future__ import annotations

from typing import Any

import Rhino  # type: ignore
from compas.tolerance import TOL

from compas_brep.errors import BrepInvalidError


class _RhinoLoopBuilder:
    """Builds a single Brep loop. Created by :meth:`_RhinoFaceBuilder.add_loop`."""

    def __init__(self, loop: Any, brep: Any) -> None:
        self._loop = loop
        self._brep = brep

    def add_trim(
        self,
        curve: Any,
        edge_index: int,
        is_reversed: bool,
        iso_status: Any,
        vertex_index: int,
    ) -> Any:
        """Add a trim to the loop.

        Parameters
        ----------
        curve
            The 2D pcurve of this trim, in the face surface's parameter space.
        edge_index
            Index of the already-added edge this trim runs along, or ``-1`` for a
            singular trim (one with no edge, e.g. at the pole of a sphere).
        is_reversed
            Whether this trim runs against its edge's direction.
        iso_status
            The trim's ``Rhino.Geometry.IsoStatus``.
        vertex_index
            Index of the vertex a singular trim collapses to. Unused otherwise.

        """
        c_index = self._brep.AddTrimCurve(curve)
        if edge_index == -1:
            vertex = self._brep.Vertices[vertex_index]
            trim = self._brep.Trims.AddSingularTrim(vertex, self._loop, iso_status, c_index)
        else:
            edge = self._brep.Edges[edge_index]
            trim = self._brep.Trims.Add(edge, is_reversed, self._loop, c_index)
        trim.IsoStatus = iso_status
        trim.SetTolerances(TOL.absolute, TOL.absolute)
        return trim

    @property
    def result(self) -> Any:
        return self._loop


class _RhinoFaceBuilder:
    """Builds a single BrepFace. Created by :meth:`_RhinoBrepBuilder.add_face`."""

    def __init__(self, face: Any, brep: Any) -> None:
        self._face = face
        self._brep = brep

    def add_loop(self, loop_type: Any) -> _RhinoLoopBuilder:
        """Add a loop of ``loop_type`` to this face, returning a builder for its trims."""
        loop = self._brep.Loops.Add(loop_type, self._face)
        return _RhinoLoopBuilder(loop, self._brep)

    @property
    def result(self) -> Any:
        return self._face


class _RhinoBrepBuilder:
    """Reconstructs a ``Rhino.Geometry.Brep`` from canonical compas_brep topology."""

    def __init__(self) -> None:
        self._brep = Rhino.Geometry.Brep()

    def add_vertex(self, point: Any) -> Any:
        """Add a vertex at a :class:`compas.geometry.Point`."""
        rhino_point = Rhino.Geometry.Point3d(point.x, point.y, point.z)
        return self._brep.Vertices.Add(rhino_point, TOL.absolute)

    def add_edge(self, edge_curve: Any, start_vertex: int, end_vertex: int) -> Any:
        """Add an edge running along ``edge_curve`` between two vertex indices."""
        curve_index = self._brep.AddEdgeCurve(edge_curve)
        s_vertex = self._brep.Vertices[start_vertex]
        e_vertex = self._brep.Vertices[end_vertex]
        return self._brep.Edges.Add(s_vertex, e_vertex, curve_index, TOL.absolute)

    def add_face(self, surface: Any, is_reversed: bool = False) -> _RhinoFaceBuilder:
        """Add a face on ``surface``, returning a builder for its loops."""
        surface_index = self._brep.AddSurface(surface)
        face = self._brep.Faces.Add(surface_index)
        if is_reversed:
            face.OrientationIsReversed = True
        return _RhinoFaceBuilder(face=face, brep=self._brep)

    @property
    def result(self) -> Any:
        """The finished Brep.

        Raises
        ------
        BrepInvalidError
            If Rhino reports the reconstruction as invalid.

        """
        self._brep.SetTrimIsoFlags()
        self._brep.Compact()
        is_valid, log = self._brep.IsValidWithLog()
        if not is_valid:
            raise BrepInvalidError(f"Brep reconstruction failed!\n{log}")
        return self._brep
