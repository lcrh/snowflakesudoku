#!/usr/bin/env python3
"""Generate valid snowflake sudoku puzzles using CVC5 and parametric topology."""

import subprocess
import json
import random
import sys
from pathlib import Path

# Import parametric topology
sys.path.insert(0, str(Path(__file__).parent.parent))
from snowflake.parametric_topology import build_snowflake

def generate_smt_model(constraints, n_cells):
    """Generate SMT-LIB2 model for snowflake sudoku with given constraints."""

    smt = "(set-logic QF_LIA)\n"

    # Declare variables for each cell (1-6)
    for i in range(n_cells):
        smt += f"(declare-fun cell{i} () Int)\n"

    # Add constraints: each cell is 1-6
    for i in range(n_cells):
        smt += f"(assert (and (>= cell{i} 1) (<= cell{i} 6)))\n"

    # Add all-different constraints for all hexagons
    for hex_idx, hexagon in enumerate(constraints):
        cells = [f"cell{i}" for i in hexagon]
        smt += f"(assert (distinct {' '.join(cells)}))\n"

    smt += "(check-sat)\n"
    smt += "(get-model)\n"

    return smt

def parse_model(output, n_cells):
    """Parse CVC5 model output to extract solution."""
    solution = [0] * n_cells

    for line in output.split('\n'):
        line = line.strip()
        if '(define-fun cell' in line:
            # Extract: (define-fun cell5 () Int 3)
            try:
                parts = line.split()
                # parts[1] is like "cell5"
                cell_str = parts[1]
                if cell_str.startswith('cell'):
                    cell_num = int(cell_str[4:])  # Extract number after "cell"
                    value = int(parts[-1].rstrip(')'))  # Last part, remove trailing )
                    if 0 <= cell_num < n_cells:
                        solution[cell_num] = value
            except (ValueError, IndexError, AttributeError) as e:
                pass

    return solution

def generate_puzzle(n, rng, cvc5_path):
    """Generate a single valid puzzle using CVC5 and parametric topology."""

    print(f"Building topology for n={n}...")
    constraints, n_cells = build_snowflake(n)

    print(f"  Cells: {n_cells}, Constraints: {len(constraints)}")
    print(f"Generating SMT model...")
    smt_model = generate_smt_model(constraints, n_cells)

    print(f"Solving with CVC5...")
    try:
        result = subprocess.run(
            [cvc5_path, "--produce-models", "--lang=smt2", "-"],
            input=smt_model,
            capture_output=True,
            text=True,
            timeout=30
        )

        output = result.stdout

        if "sat" not in output:
            print(f"CVC5: unsatisfiable")
            return None, None

        # Parse the solution
        solution = parse_model(output, n_cells)

        # Count non-zero values (parsed cells)
        filled = sum(1 for v in solution if v > 0)
        print(f"  Parsed {filled}/{n_cells} cells")

        if all(v in range(1, 7) for v in solution):
            print(f"✓ Found valid solution: {solution[:20]}...")
            return solution, n_cells
        else:
            print(f"✗ Solution has invalid values: {set(solution)}")
            print(f"  Sample: {solution[:20]}")
            return None, None

    except subprocess.TimeoutExpired:
        print("CVC5 timeout")
        return None, None
    except Exception as e:
        print(f"Error: {e}")
        return None, None

def create_puzzle_from_solution(solution, n_cells, num_givens=None):
    """Create a puzzle by removing cells from a solution."""
    if num_givens is None:
        # Default: remove about 30-40% of cells
        num_givens = max(3, int(n_cells * 0.6))

    puzzle = solution.copy()
    num_to_remove = n_cells - num_givens

    cells_to_remove = random.sample(range(n_cells), min(num_to_remove, n_cells))
    TOP = 7
    for cell_idx in cells_to_remove:
        puzzle[cell_idx] = TOP

    return puzzle

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Generate snowflake sudoku puzzles with parametric topology")
    parser.add_argument("--n", type=int, default=1, help="Topology parameter (1=single hexagon, 2=two hexagons)")
    parser.add_argument("--count", type=int, default=3, help="Number of puzzles to generate")
    parser.add_argument("--output", type=str, default="puzzle_generation_output.json", help="Output file")
    parser.add_argument("--seed", type=int, default=42, help="Random seed")
    parser.add_argument("--cvc5", type=str, default="cvc5", help="Path to CVC5 binary (default: assume on PATH)")
    args = parser.parse_args()

    rng = random.Random(args.seed)

    print(f"Generating {args.count} snowflake sudoku puzzles (n={args.n})...\n")

    puzzles = []
    for i in range(args.count):
        print(f"\nPuzzle {i+1}:")
        solution, n_cells = generate_puzzle(args.n, rng, args.cvc5)

        if solution and n_cells:
            puzzle = create_puzzle_from_solution(solution, n_cells)
            puzzles.append({
                "n": args.n,
                "n_cells": n_cells,
                "puzzle": puzzle,
                "solution": solution,
                "givens": sum(1 for v in puzzle if v != 7)
            })
            print(f"  Created puzzle with {puzzles[-1]['givens']} givens")
        else:
            print("  Failed to generate puzzle")

    # Save to JSON for manual inspection
    output_file = Path(args.output)
    with open(output_file, "w") as f:
        json.dump(puzzles, f, indent=2)

    print(f"\n✓ Generated {len(puzzles)} puzzles")
    print(f"  Saved to {output_file}")
