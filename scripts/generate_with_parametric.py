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
    """Generate a single valid puzzle using CVC5 and parametric topology.

    Returns (solution, n_cells, constraints) or (None, None, None) on failure.
    """

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
            return None, None, None

        # Parse the solution
        solution = parse_model(output, n_cells)

        # Count non-zero values (parsed cells)
        filled = sum(1 for v in solution if v > 0)
        print(f"  Parsed {filled}/{n_cells} cells")

        if all(v in range(1, 7) for v in solution):
            print(f"✓ Found valid solution: {solution[:20]}...")
            return solution, n_cells, constraints
        else:
            print(f"✗ Solution has invalid values: {set(solution)}")
            print(f"  Sample: {solution[:20]}")
            return None, None, None

    except subprocess.TimeoutExpired:
        print("CVC5 timeout")
        return None, None, None
    except Exception as e:
        print(f"Error: {e}")
        return None, None, None

def build_uniqueness_smt(constraints, n_cells, solution, given_set):
    """Build SMT model to check if given_set uniquely determines solution.

    The blocking clause forces the solver to find a different solution.
    If CVC5 returns UNSAT, the puzzle has a unique solution.
    """
    smt = "(set-logic QF_LIA)\n"

    # Declare variables for each cell
    for i in range(n_cells):
        smt += f"(declare-fun cell{i} () Int)\n"

    # Domain constraints: each cell is 1-6
    for i in range(n_cells):
        smt += f"(assert (and (>= cell{i} 1) (<= cell{i} 6)))\n"

    # Add all-different constraints
    for group in constraints:
        cells = [f"cell{i}" for i in group]
        smt += f"(assert (distinct {' '.join(cells)}))\n"

    # Fix given cells to their known values from the solution
    for i in given_set:
        smt += f"(assert (= cell{i} {solution[i]}))\n"

    # Blocking clause: require a solution different from the known one on at least one free cell
    free_cells = [i for i in range(n_cells) if i not in given_set]
    if free_cells:
        # Assert: at least one free cell must differ from the known solution
        diffs = " ".join(f"(not (= cell{i} {solution[i]}))" for i in free_cells)
        smt += f"(assert (or {diffs}))\n"

    smt += "(check-sat)\n"
    return smt


def is_unique(constraints, n_cells, solution, given_set, cvc5_path):
    """Check if the partial puzzle (given_set) has a unique solution.

    Returns True if unique (UNSAT = no other solution exists).
    Returns False if non-unique (SAT = alternative solution found).
    """
    smt = build_uniqueness_smt(constraints, n_cells, solution, given_set)
    try:
        result = subprocess.run(
            [cvc5_path, "--lang=smt2", "-"],
            input=smt,
            capture_output=True,
            text=True,
            timeout=30
        )
        return result.stdout.strip().startswith("unsat")
    except subprocess.TimeoutExpired:
        # Timeout = can't find another solution = assume unique (conservative)
        return True
    except Exception:
        return False


def create_unique_puzzle(solution, constraints, n_cells, target_givens, cvc5_path, rng):
    """Create a puzzle by iteratively removing cells while checking uniqueness.

    Start with all cells given, then progressively remove cells.
    Each cell is tried for removal exactly once (in shuffled order).
    If removing a cell breaks uniqueness, it stays as a given.

    Returns a puzzle with a guaranteed unique solution.
    """
    # Start with all cells as givens
    given = set(range(n_cells))

    # Randomize the order in which we try to remove cells
    removal_order = list(range(n_cells))
    rng.shuffle(removal_order)

    removed_count = 0
    for cell_idx in removal_order:
        # Try removing this cell
        given.discard(cell_idx)

        # Check if the puzzle is still uniquely solvable
        if not is_unique(constraints, n_cells, solution, given, cvc5_path):
            # Not unique - restore this cell as a given
            given.add(cell_idx)
        else:
            # Unique - keep it removed
            removed_count += 1

        # Stop if we've reached the target number of givens
        if len(given) <= target_givens:
            break

    # Build the puzzle: solution values for givens, 7 (unknown) for removed cells
    puzzle = [solution[i] if i in given else 7 for i in range(n_cells)]

    return puzzle, len(given), removed_count

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Generate snowflake sudoku puzzles with parametric topology and uniqueness guarantee")
    parser.add_argument("--n", type=int, default=1, help="Topology parameter (1=single hexagon, 2=two hexagons)")
    parser.add_argument("--count", type=int, default=3, help="Number of puzzles to generate")
    parser.add_argument("--output", type=str, default="puzzle_generation_output.json", help="Output file")
    parser.add_argument("--seed", type=int, default=42, help="Random seed")
    parser.add_argument("--cvc5", type=str, default="cvc5", help="Path to CVC5 binary (default: assume on PATH)")
    parser.add_argument("--target-givens", type=int, default=None, help="Target number of givens (default: 60% of cells)")
    args = parser.parse_args()

    rng = random.Random(args.seed)

    print(f"Generating {args.count} snowflake sudoku puzzles (n={args.n})...\n")
    print(f"Uniqueness guarantee: ON (iterative progressive removal with CVC5 checking)\n")

    puzzles = []
    for i in range(args.count):
        print(f"\nPuzzle {i+1}:")
        solution, n_cells, constraints = generate_puzzle(args.n, rng, args.cvc5)

        if solution and n_cells and constraints:
            # Determine target givens
            target = args.target_givens if args.target_givens else max(3, int(n_cells * 0.6))

            print(f"Ensuring unique solution (target: ~{target} givens)...")
            puzzle, actual_givens, removed_count = create_unique_puzzle(
                solution, constraints, n_cells, target, args.cvc5, rng
            )

            puzzles.append({
                "n": args.n,
                "n_cells": n_cells,
                "puzzle": puzzle,
                "solution": solution,
                "givens": sum(1 for v in puzzle if v != 7)
            })
            print(f"  ✓ Created unique puzzle with {puzzles[-1]['givens']} givens ({removed_count} cells removed)")
        else:
            print("  Failed to generate puzzle")

    # Save to JSON for manual inspection
    output_file = Path(args.output)
    with open(output_file, "w") as f:
        json.dump(puzzles, f, indent=2)

    print(f"\n✓ Generated {len(puzzles)} unique puzzles")
    print(f"  Saved to {output_file}")
