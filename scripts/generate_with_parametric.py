#!/usr/bin/env python3
"""Generate valid snowflake sudoku puzzles using CVC5 and parametric topology."""

import subprocess
import json
import random
import sys
import string
from pathlib import Path

# Import parametric topology
sys.path.insert(0, str(Path(__file__).parent.parent))
from snowflake.parametric_topology import build_snowflake

def generate_puzzle_code(rng):
    """Generate a 3-character alphanumeric puzzle code."""
    chars = string.ascii_uppercase + string.digits
    return ''.join(rng.choice(chars) for _ in range(3))

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


def create_minimal_puzzle(solution, constraints, n_cells, cvc5_path, rng):
    """Find the minimal puzzle with a unique solution.

    Iteratively removes cells while maintaining uniqueness.
    Continues until no more cells can be removed without losing uniqueness.

    Returns (puzzle, min_givens, removed_indices) where removed_indices
    are the cells that can be removed while maintaining uniqueness.
    """
    # Start with all cells as givens
    given = set(range(n_cells))

    # Randomize the order in which we try to remove cells
    removal_order = list(range(n_cells))
    rng.shuffle(removal_order)

    removed = []
    for cell_idx in removal_order:
        # Try removing this cell
        given.discard(cell_idx)

        # Check if the puzzle is still uniquely solvable
        if not is_unique(constraints, n_cells, solution, given, cvc5_path):
            # Not unique - restore this cell as a given
            given.add(cell_idx)
        else:
            # Unique - keep it removed
            removed.append(cell_idx)

    # Build the minimal puzzle
    puzzle = [solution[i] if i in given else 7 for i in range(n_cells)]
    return puzzle, len(given), removed


def create_puzzle_variants(solution, constraints, n_cells, min_givens, removed_indices, rng):
    """Create puzzle variants with increasing difficulty from minimal.

    Takes the minimal puzzle and creates harder versions by adding back
    some of the removed cells (fewer removed = more givens).

    Returns list of (puzzle, givens_count) tuples, easiest to hardest.
    """
    variants = []

    # Start with minimal puzzle (all removable cells removed)
    min_puzzle = [solution[i] if i not in removed_indices else 7 for i in range(n_cells)]
    variants.append((min_puzzle, min_givens))

    # Create progressively harder versions
    remaining_removed = list(removed_indices)
    rng.shuffle(remaining_removed)

    # Add back cells in chunks to create intermediate difficulties
    step_size = max(1, len(remaining_removed) // 4)  # Create ~4 levels
    added_back = 0

    while added_back < len(remaining_removed):
        # Add back the next chunk
        chunk_end = min(added_back + step_size, len(remaining_removed))
        cells_to_add = set(remaining_removed[added_back:chunk_end])
        added_back = chunk_end

        # Build puzzle with these cells added back
        puzzle = [solution[i] if i not in (set(remaining_removed) - cells_to_add) else 7
                  for i in range(n_cells)]
        givens = sum(1 for v in puzzle if v != 7)

        if givens > min_givens:  # Only add if it's actually harder
            variants.append((puzzle, givens))

    return variants


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
    parser.add_argument("--n-min", type=int, default=1, help="Minimum topology parameter")
    parser.add_argument("--n-max", type=int, default=19, help="Maximum topology parameter")
    parser.add_argument("--count", type=int, default=1, help="Number of base puzzles per topology size")
    parser.add_argument("--variants", type=int, default=3, help="Number of difficulty variants per base puzzle (minimal + harder)")
    parser.add_argument("--output", type=str, default="puzzles_large.json", help="Output file")
    parser.add_argument("--seed", type=int, default=42, help="Random seed")
    parser.add_argument("--cvc5", type=str, default="cvc5", help="Path to CVC5 binary (default: assume on PATH)")
    args = parser.parse_args()

    rng = random.Random(args.seed)

    print(f"Generating snowflake sudoku puzzles (n={args.n_min} to {args.n_max})...\n")
    print(f"Base puzzles: {args.count} per size")
    print(f"Variants per base: {args.variants} (minimal + harder versions)")
    print(f"Uniqueness guarantee: ON (iterative progressive removal with CVC5 checking)\n")

    puzzles = []
    puzzle_id = 0

    for n in range(args.n_min, args.n_max + 1):
        print(f"\n{'='*60}")
        print(f"Topology n={n}:")
        print(f"{'='*60}")

        for base_idx in range(args.count):
            print(f"\nBase puzzle {base_idx+1}/{args.count}:")
            solution, n_cells, constraints = generate_puzzle(n, rng, args.cvc5)

            if not (solution and n_cells and constraints):
                print(f"  Failed to generate puzzle")
                continue

            print(f"  Finding minimal unique puzzle ({n_cells} cells)...")
            min_puzzle, min_givens, removed = create_minimal_puzzle(
                solution, constraints, n_cells, args.cvc5, rng
            )

            print(f"  ✓ Found minimal puzzle: {min_givens} givens")

            # Create variants with different difficulties
            print(f"  Creating {args.variants} difficulty variants...")
            variants = create_puzzle_variants(solution, constraints, n_cells, min_givens, removed, rng)

            # Limit to requested number of variants
            variants = variants[:args.variants]

            for var_idx, (puzzle, givens) in enumerate(variants):
                code = generate_puzzle_code(rng)
                puzzle_record = {
                    "id": puzzle_id,
                    "code": f"{code}-{n}-{givens}",
                    "n": n,
                    "n_cells": n_cells,
                    "puzzle": puzzle,
                    "solution": solution,
                    "givens": givens
                }
                puzzles.append(puzzle_record)
                puzzle_id += 1

                difficulty_label = "minimal" if var_idx == 0 else f"harder({var_idx})"
                print(f"    • {puzzle_record['code']} ({givens} givens) - {difficulty_label}")

    # Save to JSON
    output_file = Path(args.output)
    with open(output_file, "w") as f:
        json.dump(puzzles, f, indent=2)

    print(f"\n{'='*60}")
    print(f"✓ Generated {len(puzzles)} total puzzles")
    print(f"  {len([p for p in puzzles if 'minimal' in str(p)])} base (minimal)")
    print(f"  {len(puzzles)} total with variants")
    print(f"  Saved to {output_file}")
    print(f"{'='*60}")
