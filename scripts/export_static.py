#!/usr/bin/env python3
"""Export puzzle data to a self-contained JSON file for the static frontend.

Each puzzle record includes its topology (hex coords, cell positions, constraints)
so the frontend only needs to load a single file.

Usage:
    python scripts/export_static.py
    python scripts/export_static.py --input puzzle_generation_output_parametric.json \
                                    --output static/puzzles.json
"""

import json
import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))
from snowflake.parametric_topology import build_snowflake, HEX_COORDS_BY_N, get_cell_positions


def export(input_path: Path, output_path: Path) -> None:
    with open(input_path) as f:
        raw = json.load(f)

    puzzles = []
    for i, p in enumerate(raw):
        n = p["n"]
        constraints, n_cells = build_snowflake(n)
        hex_coords = HEX_COORDS_BY_N[n]
        cell_positions = get_cell_positions(n)

        puzzle_record = {
            "id": i,
            "n": n,
            "puzzle": p["puzzle"],
            "solution": p["solution"],
            "givens": sum(1 for v in p["puzzle"] if v != 7),
            "topology": {
                "n_cells": n_cells,
                "hex_coords": [{"q": q, "r": r} for q, r in hex_coords],
                "cell_positions": cell_positions,
                "constraints": [{"cells": c} for c in constraints],
            },
        }

        # Preserve code field if it exists
        if "code" in p:
            puzzle_record["code"] = p["code"]

        puzzles.append(puzzle_record)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(puzzles, f)

    print(f"Exported {len(puzzles)} puzzles to {output_path}")
    for n in sorted({p["n"] for p in puzzles}):
        count = sum(1 for p in puzzles if p["n"] == n)
        sample = next(p for p in puzzles if p["n"] == n)
        nc = sample["topology"]["n_cells"]
        nc_c = len(sample["topology"]["constraints"])
        print(f"  n={n}: {count} puzzles, {nc} cells, {nc_c} constraints each")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default="puzzle_generation_output_parametric.json")
    parser.add_argument("--output", default="static/puzzles.json")
    args = parser.parse_args()
    export(Path(args.input), Path(args.output))
