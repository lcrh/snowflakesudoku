"""Sanity tests for parametric topology module."""

import pytest
from snowflake.parametric_topology import (
    build_snowflake,
    get_cell_positions,
    get_hex_coords,
    translate_hex_coords,
    HEX_COORDS_BY_N,
    _hex_ring,
    _hex_coords_up_to_n,
)


class TestRingGeneration:
    """Test hexagonal ring generation."""

    def test_ring_0_is_center(self):
        """Ring 0 should be just the center hexagon."""
        ring = _hex_ring(0)
        assert ring == [(0, 0)]
        assert len(ring) == 1

    def test_ring_1_has_6_hexagons(self):
        """Ring 1 should have 6 hexagons."""
        ring = _hex_ring(1)
        assert len(ring) == 6

    def test_ring_2_has_12_hexagons(self):
        """Ring 2 should have 12 hexagons."""
        ring = _hex_ring(2)
        assert len(ring) == 12

    def test_ring_k_has_6k_hexagons(self):
        """Ring k should have 6k hexagons."""
        for k in range(1, 5):
            ring = _hex_ring(k)
            assert len(ring) == 6 * k, f"Ring {k} should have {6*k} hexagons, got {len(ring)}"


class TestCoordinateGeneration:
    """Test coordinate list generation."""

    def test_n1_produces_1_hexagon(self):
        """n=1 should produce exactly 1 hexagon."""
        coords = _hex_coords_up_to_n(1)
        assert len(coords) == 1
        assert coords == [(0, 0)]

    def test_n7_produces_7_hexagons(self):
        """n=7 should produce exactly 7 hexagons (ring 0 + ring 1)."""
        coords = _hex_coords_up_to_n(7)
        assert len(coords) == 7

    def test_n13_produces_13_hexagons(self):
        """n=13 should produce exactly 13 hexagons (rings 0, 1, 2)."""
        coords = _hex_coords_up_to_n(13)
        assert len(coords) == 13

    def test_hex_coords_by_n_available(self):
        """HEX_COORDS_BY_N should have entries for at least n=1..10."""
        for n in range(1, 11):
            assert n in HEX_COORDS_BY_N
            coords = HEX_COORDS_BY_N[n]
            assert len(coords) == n, f"HEX_COORDS_BY_N[{n}] should have {n} entries"


class TestTopologyGeneration:
    """Test constraint and cell generation."""

    def test_n1_has_1_constraint(self):
        """n=1 (single hexagon) should have 1 constraint."""
        constraints, n_cells = build_snowflake(1)
        assert n_cells == 6, "1 hexagon = 6 cells"
        assert len(constraints) == 1, "1 hexagon = 1 constraint"

    def test_n2_has_2_constraints(self):
        """n=2 (two hexagons, no overlap) should have 2 constraints."""
        constraints, n_cells = build_snowflake(2)
        assert n_cells == 12, "2 hexagons = 12 cells"
        assert len(constraints) == 2, "2 hexagons = 2 constraints (no meeting points yet)"

    def test_n3_has_4_constraints(self):
        """n=3 (three hexagons) should have 3 hexagon + 1 meeting point = 4 constraints."""
        constraints, n_cells = build_snowflake(3)
        assert n_cells == 18, "3 hexagons = 18 cells"
        assert len(constraints) == 4, f"n=3 should have 4 constraints, got {len(constraints)}"

    def test_n4_has_6_constraints(self):
        """n=4 (four hexagons) should have 4 hexagon + 1 meeting point = 5 constraints. But if no meeting points, 4."""
        constraints, n_cells = build_snowflake(4)
        assert n_cells == 24, "4 hexagons = 24 cells"
        # n=4 topology should produce meeting point(s)
        assert len(constraints) >= 4, f"n=4 should have at least 4 constraints, got {len(constraints)}"

    def test_n7_has_13_constraints(self):
        """n=7 (complete ring 1) should have 13 constraints (7 hexagons + 6 meeting points or similar)."""
        constraints, n_cells = build_snowflake(7)
        assert n_cells == 42, "7 hexagons = 42 cells"
        assert len(constraints) == 13, f"n=7 should have 13 constraints, got {len(constraints)}"

    def test_n13_has_27_constraints(self):
        """n=13 (complete rings 1+2) should have 27 constraints."""
        constraints, n_cells = build_snowflake(13)
        assert n_cells == 78, "13 hexagons = 78 cells"
        assert len(constraints) == 27, f"n=13 should have 27 constraints, got {len(constraints)}"

    def test_constraint_size_is_6(self):
        """Each constraint should contain exactly 6 cell indices (hexagon size)."""
        for n in [1, 2, 4, 7]:
            constraints, n_cells = build_snowflake(n)
            for constraint in constraints:
                assert len(constraint) == 6, f"Constraint should have 6 cells, got {len(constraint)}"

    def test_constraint_indices_in_range(self):
        """All cell indices in constraints should be in valid range [0, n_cells)."""
        for n in [1, 2, 4, 7]:
            constraints, n_cells = build_snowflake(n)
            for constraint in constraints:
                for cell_idx in constraint:
                    assert 0 <= cell_idx < n_cells, f"Cell index {cell_idx} out of range [0, {n_cells})"


class TestCellPositions:
    """Test cell position generation."""

    def test_cell_positions_count_matches_n_cells(self):
        """get_cell_positions should return exactly n_cells entries."""
        for n in [1, 2, 4, 7]:
            cell_positions = get_cell_positions(n)
            assert len(cell_positions) == n * 6, f"n={n} should have {n*6} cells"

    def test_cell_position_has_required_fields(self):
        """Each cell position should have q, r, and direction."""
        for n in [1, 2, 4]:
            cell_positions = get_cell_positions(n)
            for idx, pos in cell_positions.items():
                assert "q" in pos, f"Cell {idx} missing 'q'"
                assert "r" in pos, f"Cell {idx} missing 'r'"
                assert "direction" in pos, f"Cell {idx} missing 'direction'"
                assert pos["direction"] in ["NE", "E", "SE", "SW", "W", "NW"]

    def test_all_cells_indexed(self):
        """All cells should be indexed sequentially from 0."""
        for n in [1, 2, 4, 7]:
            cell_positions = get_cell_positions(n)
            indices = set(cell_positions.keys())
            expected = set(range(n * 6))
            assert indices == expected, f"Cell indices mismatch for n={n}"


class TestNonRegressions:
    """Test that known values don't change."""

    def test_known_topology_sizes(self):
        """Verify known topology sizes match expectations."""
        test_cases = [
            (1, 6, 1),      # n, n_cells, num_constraints
            (2, 12, 2),
            (3, 18, 4),     # 3 hexagons + 1 meeting point
            (4, 24, 6),     # 4 hexagons + 2 meeting points (or similar)
            (7, 42, 13),
            (13, 78, 27),
        ]
        for n, expected_cells, expected_constraints in test_cases:
            constraints, n_cells = build_snowflake(n)
            assert n_cells == expected_cells, f"n={n}: expected {expected_cells} cells, got {n_cells}"
            assert len(constraints) == expected_constraints, \
                f"n={n}: expected {expected_constraints} constraints, got {len(constraints)}"


class TestVariedTopologies:
    """Test deterministic opt-in topology variation."""

    def test_default_calls_keep_canonical_topology(self):
        for n in HEX_COORDS_BY_N:
            assert get_hex_coords(n) == HEX_COORDS_BY_N[n]
            assert get_cell_positions(n) == get_cell_positions(
                n, HEX_COORDS_BY_N[n]
            )
            assert build_snowflake(n) == build_snowflake(
                n, HEX_COORDS_BY_N[n]
            )

    def test_seeded_topology_is_deterministic(self):
        assert get_hex_coords(8, topology_seed=42) == get_hex_coords(
            8, topology_seed=42
        )
        assert build_snowflake(8, topology_seed=42) == build_snowflake(
            8, topology_seed=42
        )
        assert get_cell_positions(8, topology_seed=42) == get_cell_positions(
            8, topology_seed=42
        )

    def test_seeds_produce_varied_layouts(self):
        # Small orders have few polyhexes; pin the observed shape counts so a
        # sampler regression is visible. Larger orders just need diversity.
        expected_min_shapes = {4: 3, 5: 6, 8: 10}
        for n, min_shapes in expected_min_shapes.items():
            layouts = {
                tuple(get_hex_coords(n, topology_seed=seed))
                for seed in range(40)
            }
            assert len(layouts) >= min_shapes
            assert all(len(layout) == n for layout in layouts)
            assert all(len(set(layout)) == n for layout in layouts)

    def test_varied_constraint_hypergraph_is_connected(self):
        for n in [3, 4, 8, 13]:
            for seed in range(10):
                constraints, _ = build_snowflake(n, topology_seed=seed)
                adjacency = {hex_idx: set() for hex_idx in range(n)}
                # Meeting points span >1 hexagon; do not rely on constraint order.
                for group in constraints:
                    hexagons = {cell_idx // 6 for cell_idx in group}
                    if len(hexagons) < 2:
                        continue
                    for left in hexagons:
                        adjacency[left].update(hexagons - {left})

                seen = {0}
                frontier = [0]
                while frontier:
                    current = frontier.pop()
                    new = adjacency[current] - seen
                    seen.update(new)
                    frontier.extend(new)
                assert seen == set(range(n))

    def test_explicit_coords_drive_constraints_and_positions(self):
        coords = [(0, 0), (1, -1), (0, -1), (1, 0)]
        constraints, n_cells = build_snowflake(4, coords)
        positions = get_cell_positions(4, coords)
        assert n_cells == 24
        assert len(constraints) == 6
        assert {
            (position["q"], position["r"])
            for position in positions.values()
        } == set(coords)

    def test_explicit_coords_and_seed_are_mutually_exclusive(self):
        with pytest.raises(ValueError, match="either hex_coords or topology_seed"):
            build_snowflake(
                1,
                [(0, 0)],
                topology_seed=1,
            )

    def test_translate_hex_coords_fits_covering_box(self):
        for n in range(4, 9):
            for seed in range(40):
                coords = get_hex_coords(n, topology_seed=seed)
                fitted = translate_hex_coords(
                    coords, q_min=-2, q_max=2, r_min=-2, r_max=2
                )
                assert len(fitted) == n
                assert all(-2 <= q <= 2 and -2 <= r <= 2 for q, r in fitted)
                # Relative geometry is preserved.
                origin = set(
                    (q - coords[0][0], r - coords[0][1]) for q, r in coords
                )
                fitted_origin = set(
                    (q - fitted[0][0], r - fitted[0][1]) for q, r in fitted
                )
                assert origin == fitted_origin

    def test_translate_hex_coords_rejects_oversized_layout(self):
        # A 6-hex strip is wider than the 5x5 covering box.
        strip = [(i, 0) for i in range(6)]
        with pytest.raises(ValueError, match="cannot fit"):
            translate_hex_coords(
                strip, q_min=-2, q_max=2, r_min=-2, r_max=2
            )

    def test_build_snowflake_invariant_under_translation(self):
        coords = get_hex_coords(8, topology_seed=7)
        fitted = translate_hex_coords(
            coords, q_min=-2, q_max=2, r_min=-2, r_max=2
        )
        assert build_snowflake(8, coords) == build_snowflake(8, fitted)
