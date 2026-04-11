"""Parametric snowflake sudoku topology builder.

Each snowflake is described by a list of hexagon positions in axial (q, r) coordinates.
Each hexagon has 6 triangular cells (one per direction: NE, E, SE, SW, W, NW).
Cells are indexed sequentially: hexagon 0 gets cells 0-5, hexagon 1 gets cells 6-11, etc.

Meeting points — vertices where exactly 6 cells converge — are detected geometrically
and also become constraints.
"""

import math
from typing import Dict, List, Tuple
from dataclasses import dataclass

@dataclass(frozen=True)
class HexCell:
    """A triangular cell identified by its parent hexagon (q, r) and direction."""
    q: int
    r: int
    direction: str  # one of DIRECTIONS

# Clockwise from NE
DIRECTIONS = ["NE", "E", "SE", "SW", "W", "NW"]

def _hex_ring(ring: int) -> List[Tuple[int, int]]:
    """Generate hexagon coordinates for a single ring in concentric hexagonal pattern.

    Ring 0 is the center (0, 0).
    Ring k (k > 0) contains 6k hexagons arranged in a hexagonal ring.
    Uses axial coordinates (q, r).
    """
    if ring == 0:
        return [(0, 0)]

    coords = []
    # Start at the "East" corner of the ring: (ring, -ring)
    q, r = ring, -ring

    # Six directions: move around the hexagon
    # Each side of the ring has 'ring' hexagons
    directions = [
        (-1, 0),   # NW
        (-1, 1),   # W
        (0, 1),    # SW
        (1, 0),    # SE
        (1, -1),   # E
        (0, -1),   # NE
    ]

    for direction in directions:
        dq, dr = direction
        for _ in range(ring):
            coords.append((q, r))
            q += dq
            r += dr

    return coords


def _hex_coords_up_to_n(n: int) -> List[Tuple[int, int]]:
    """Generate all hexagon coordinates for topologies with n total hexagons.

    Generates rings from the center outward until we have at least n hexagons total.
    Returns exactly n coordinates.
    """
    coords = []
    ring = 0
    while len(coords) < n:
        coords.extend(_hex_ring(ring))
        ring += 1
    return coords[:n]


# Build dictionary dynamically for supported n values (can now extend to larger values)
HEX_COORDS_BY_N: Dict[int, List[Tuple[int, int]]] = {
    n: _hex_coords_up_to_n(n) for n in range(1, 20)
}


def get_cell_positions(n: int) -> Dict[int, Dict]:
    """Return {cell_idx: {q, r, direction}} for rendering each cell as a triangle.

    Cells are indexed in hex-major order: all 6 cells of hexagon 0,
    then all 6 of hexagon 1, etc.
    """
    positions = {}
    idx = 0
    for q, r in HEX_COORDS_BY_N[n]:
        for direction in DIRECTIONS:
            positions[idx] = {"q": q, "r": r, "direction": direction}
            idx += 1
    return positions


def build_snowflake(n: int) -> Tuple[List[List[int]], int]:
    """Build constraints and cell count for a snowflake with n hexagons.

    Returns:
        constraints: list of groups; each group is a list of cell indices
                     that must all contain distinct digits 1-6.
        n_cells:     total number of cells (n * 6).
    """
    if n not in HEX_COORDS_BY_N:
        raise NotImplementedError(f"n={n} not supported. Available: {sorted(HEX_COORDS_BY_N)}")

    hex_coords = HEX_COORDS_BY_N[n]

    # Build cell index map
    # Each cell is indexed uniquely by (hexagon_q, hexagon_r, direction)
    # NO shared cells - each hexagon has its own 6 cells
    cell_to_idx: Dict[HexCell, int] = {}
    idx_to_cell: Dict[int, HexCell] = {}
    next_idx = 0

    # For each hexagon, add its 6 cells
    for q, r in hex_coords:
        for direction in DIRECTIONS:
            cell = HexCell(q, r, direction)
            cell_to_idx[cell] = next_idx
            idx_to_cell[next_idx] = cell
            next_idx += 1

    n_cells = next_idx

    # Build hexagon constraints
    # Each hexagon at (q, r) has 6 cells (one in each direction)
    constraints = []
    for q, r in hex_coords:
        hexagon_cells = []
        for direction in DIRECTIONS:
            cell = HexCell(q, r, direction)
            hexagon_cells.append(cell_to_idx[cell])
        constraints.append(sorted(hexagon_cells))

    # Meeting points: vertices where exactly 6 cells converge form additional constraints
    meeting_points = _find_meeting_points(idx_to_cell)
    meeting_points = [mp for mp in meeting_points if sorted(mp) not in constraints]

    return constraints + meeting_points, n_cells


def _find_meeting_points(idx_to_cell: Dict) -> List[List[int]]:
    """Find all vertices where exactly 6 cells meet and return them as constraint groups.

    Each triangular cell has 3 vertices: the hex center, and two boundary points.
    When 6 cells from different hexagons share a vertex, that vertex defines a
    new all-distinct constraint (just like a hexagon center does).
    """
    # Angle of each direction's first boundary edge (degrees, clockwise from east)
    DIRECTION_ANGLES = {"NE": 0, "E": 60, "SE": 120, "SW": 180, "W": 240, "NW": 300}
    HEX_SIZE = 100  # arbitrary scale; only relative positions matter

    vertex_to_cells: Dict[Tuple[float, float], List[int]] = {}

    for cell_idx, cell in idx_to_cell.items():
        # Hex center in cartesian coordinates (pointy-top axial layout)
        hx = HEX_SIZE * (3/2 * cell.q)
        hy = HEX_SIZE * (math.sqrt(3)/2 * cell.q + math.sqrt(3) * cell.r)

        angle_deg = DIRECTION_ANGLES[cell.direction]
        a1 = math.radians(angle_deg)
        a2 = math.radians(angle_deg + 60)

        vertices = [
            (round(hx, 1),                              round(hy, 1)),
            (round(hx + HEX_SIZE * math.cos(a1), 1),   round(hy + HEX_SIZE * math.sin(a1), 1)),
            (round(hx + HEX_SIZE * math.cos(a2), 1),   round(hy + HEX_SIZE * math.sin(a2), 1)),
        ]
        for v in vertices:
            vertex_to_cells.setdefault(v, []).append(cell_idx)

    # A vertex shared by exactly 6 distinct cells forms a hexagon constraint
    seen = set()
    meeting_points = []
    for cells in vertex_to_cells.values():
        if len(cells) == 6 and len(set(cells)) == 6:
            key = tuple(sorted(cells))
            if key not in seen:
                seen.add(key)
                meeting_points.append(list(key))

    return meeting_points

if __name__ == "__main__":
    for n in sorted(HEX_COORDS_BY_N):
        constraints, n_cells = build_snowflake(n)
        print(f"n={n}: {n_cells} cells, {len(constraints)} constraints")
