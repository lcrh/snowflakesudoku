"""Parametric snowflake sudoku topology builder.

Each snowflake is described by a list of hexagon positions in axial (q, r) coordinates.
Each hexagon has 6 triangular cells (one per direction: NE, E, SE, SW, W, NW).
Cells are indexed sequentially: hexagon 0 gets cells 0-5, hexagon 1 gets cells 6-11, etc.

Meeting points — vertices where exactly 6 cells converge — are detected geometrically
and also become constraints.
"""

import math
import random
from typing import Dict, List, Sequence, Tuple
from dataclasses import dataclass

@dataclass(frozen=True)
class HexCell:
    """A triangular cell identified by its parent hexagon (q, r) and direction."""
    q: int
    r: int
    direction: str  # one of DIRECTIONS

# Clockwise from NE
DIRECTIONS = ["NE", "E", "SE", "SW", "W", "NW"]

# Clockwise axial-coordinate neighbors.  Consecutive entries meet the center
# hexagon at a common vertex, so filling two consecutive neighbors creates one
# six-cell meeting-point constraint.
HEX_NEIGHBORS = [
    (1, 0),
    (1, -1),
    (0, -1),
    (-1, 0),
    (-1, 1),
    (0, 1),
]

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


def _varied_hex_coords(n: int, rng: random.Random) -> List[Tuple[int, int]]:
    """Generate a compact random topology with connected meeting constraints.

    Starting from one hexagon, the second is placed next to it and the third
    completes a three-hexagon meeting point.  Every later hexagon is sampled
    from empty positions that complete at least one additional meeting point.
    Consequently, for n >= 3 the constraint hypergraph stays connected rather
    than degenerating into independent edge-adjacent hexagons.
    """
    if n < 1:
        raise ValueError(f"n must be positive, got {n}")

    coords = [(0, 0)]
    occupied = {(0, 0)}
    if n == 1:
        return coords

    orientation = rng.randrange(len(HEX_NEIGHBORS))
    first = HEX_NEIGHBORS[orientation]
    coords.append(first)
    occupied.add(first)
    if n == 2:
        return coords

    # The two consecutive neighbors and the origin share a vertex.
    second = HEX_NEIGHBORS[(orientation + 1) % len(HEX_NEIGHBORS)]
    coords.append(second)
    occupied.add(second)

    while len(coords) < n:
        candidates = set()
        for q, r in occupied:
            for dq, dr in HEX_NEIGHBORS:
                candidate = (q + dq, r + dr)
                if candidate in occupied:
                    continue

                cq, cr = candidate
                # Two adjacent occupied neighbors plus the candidate make a
                # three-hexagon cluster around one geometric meeting point.
                if any(
                    (cq + HEX_NEIGHBORS[i][0],
                     cr + HEX_NEIGHBORS[i][1]) in occupied
                    and
                    (cq + HEX_NEIGHBORS[(i + 1) % 6][0],
                     cr + HEX_NEIGHBORS[(i + 1) % 6][1]) in occupied
                    for i in range(6)
                ):
                    candidates.add(candidate)

        if not candidates:  # Defensive: triangle-connected growth should not stall.
            raise RuntimeError(
                f"unable to extend varied topology after {len(coords)} hexagons"
            )
        chosen = rng.choice(sorted(candidates))
        coords.append(chosen)
        occupied.add(chosen)

    return coords


def get_hex_coords(
    n: int,
    *,
    topology_seed: int | None = None,
) -> List[Tuple[int, int]]:
    """Return the hexagon coordinates for an ``n``-hexagon topology.

    With no ``topology_seed`` this returns the historical concentric-ring
    topology exactly.  Supplying a seed opts into a deterministic varied
    topology; different seeds can produce different connected layouts.
    """
    if n not in HEX_COORDS_BY_N:
        raise NotImplementedError(
            f"n={n} not supported. Available: {sorted(HEX_COORDS_BY_N)}"
        )
    if topology_seed is None:
        return list(HEX_COORDS_BY_N[n])
    return _varied_hex_coords(n, random.Random(topology_seed))


def translate_hex_coords(
    hex_coords: Sequence[Tuple[int, int]],
    *,
    q_min: int,
    q_max: int,
    r_min: int,
    r_max: int,
) -> List[Tuple[int, int]]:
    """Translate a topology so every hexagon lies inside an axial bounding box.

    Prefers the translation that keeps the centroid as close to the origin as
    possible.  Raises ``ValueError`` if no translation fits.
    """
    coords = [(int(q), int(r)) for q, r in hex_coords]
    if not coords:
        return []

    qs = [q for q, _ in coords]
    rs = [r for _, r in coords]
    dq_lo = q_min - min(qs)
    dq_hi = q_max - max(qs)
    dr_lo = r_min - min(rs)
    dr_hi = r_max - max(rs)
    if dq_lo > dq_hi or dr_lo > dr_hi:
        raise ValueError(
            f"topology with bbox q=[{min(qs)},{max(qs)}] r=[{min(rs)},{max(rs)}] "
            f"cannot fit in q=[{q_min},{q_max}] r=[{r_min},{r_max}]"
        )

    best = None
    best_key = None
    for dq in range(dq_lo, dq_hi + 1):
        for dr in range(dr_lo, dr_hi + 1):
            shifted = [(q + dq, r + dr) for q, r in coords]
            mean_q = sum(q for q, _ in shifted) / len(shifted)
            mean_r = sum(r for _, r in shifted) / len(shifted)
            key = (mean_q * mean_q + mean_r * mean_r, abs(dq) + abs(dr), dq, dr)
            if best_key is None or key < best_key:
                best_key = key
                best = shifted
    assert best is not None
    return best


def _resolve_hex_coords(
    n: int,
    hex_coords: Sequence[Tuple[int, int]] | None,
    topology_seed: int | None,
) -> List[Tuple[int, int]]:
    if hex_coords is not None and topology_seed is not None:
        raise ValueError("pass either hex_coords or topology_seed, not both")
    if hex_coords is None:
        return get_hex_coords(n, topology_seed=topology_seed)

    resolved = [(int(q), int(r)) for q, r in hex_coords]
    if len(resolved) != n:
        raise ValueError(
            f"hex_coords must contain exactly n={n} coordinates, got {len(resolved)}"
        )
    if len(set(resolved)) != len(resolved):
        raise ValueError("hex_coords must not contain duplicates")
    return resolved


def get_cell_positions(
    n: int,
    hex_coords: Sequence[Tuple[int, int]] | None = None,
    *,
    topology_seed: int | None = None,
) -> Dict[int, Dict]:
    """Return {cell_idx: {q, r, direction}} for rendering each cell as a triangle.

    Cells are indexed in hex-major order: all 6 cells of hexagon 0,
    then all 6 of hexagon 1, etc.
    """
    resolved_coords = _resolve_hex_coords(n, hex_coords, topology_seed)
    positions = {}
    idx = 0
    for q, r in resolved_coords:
        for direction in DIRECTIONS:
            positions[idx] = {"q": q, "r": r, "direction": direction}
            idx += 1
    return positions


def build_snowflake(
    n: int,
    hex_coords: Sequence[Tuple[int, int]] | None = None,
    *,
    topology_seed: int | None = None,
) -> Tuple[List[List[int]], int]:
    """Build constraints and cell count for a snowflake with n hexagons.

    Returns:
        constraints: list of groups; each group is a list of cell indices
                     that must all contain distinct digits 1-6.
        n_cells:     total number of cells (n * 6).
    """
    resolved_coords = _resolve_hex_coords(n, hex_coords, topology_seed)

    # Build cell index map
    # Each cell is indexed uniquely by (hexagon_q, hexagon_r, direction)
    # NO shared cells - each hexagon has its own 6 cells
    cell_to_idx: Dict[HexCell, int] = {}
    idx_to_cell: Dict[int, HexCell] = {}
    next_idx = 0

    # For each hexagon, add its 6 cells
    for q, r in resolved_coords:
        for direction in DIRECTIONS:
            cell = HexCell(q, r, direction)
            cell_to_idx[cell] = next_idx
            idx_to_cell[next_idx] = cell
            next_idx += 1

    n_cells = next_idx

    # Build hexagon constraints
    # Each hexagon at (q, r) has 6 cells (one in each direction)
    constraints = []
    for q, r in resolved_coords:
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
