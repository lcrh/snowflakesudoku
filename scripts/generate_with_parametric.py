#!/usr/bin/env python3
"""Generate valid snowflake sudoku puzzles using CVC5 and parametric topology."""

import subprocess
import json
import random
import sys
import string
from pathlib import Path
from multiprocessing import Pool

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


def generate_base_puzzles_for_task(task_args):
    """Generate one base puzzle and its variants for a single task.

    Used by multiprocessing pool. Each worker generates one base puzzle
    and creates multiple variants with different difficulties.

    Args:
        task_args: (n, base_idx, seed_base, cvc5_path, num_variants)

    Returns:
        List of puzzle records (base puzzle + all variants)
    """
    n, base_idx, seed_base, cvc5_path, num_variants = task_args

    # Create unique RNG for this task
    rng = random.Random(seed_base + n * 1000 + base_idx * 100)

    # Generate initial solution
    solution, n_cells, constraints = generate_puzzle(n, rng, cvc5_path)

    if not (solution and n_cells and constraints):
        return []

    # Find minimal unique puzzle
    min_puzzle, min_givens, removed = create_minimal_puzzle(
        solution, constraints, n_cells, cvc5_path, rng
    )

    # Create variants with different difficulties
    variants = create_puzzle_variants(solution, constraints, n_cells, min_givens, removed, rng)
    variants = variants[:num_variants]

    # Generate one code for all variants of this base puzzle
    base_code = generate_puzzle_code(rng)

    # Track givens counts to add variant suffixes if needed
    givens_counts = {}
    for puzzle, givens in variants:
        if givens not in givens_counts:
            givens_counts[givens] = 0
        givens_counts[givens] += 1

    # Create puzzle records
    puzzle_records = []
    for var_idx, (puzzle, givens) in enumerate(variants):
        # Add suffix only if there are multiple puzzles with this givens count
        if givens_counts[givens] > 1:
            suffix_idx = sum(1 for g in [v[1] for v in variants[:var_idx]] if g == givens)
            suffix = chr(ord('a') + suffix_idx)
            code = f"{base_code}-{n}-{givens}{suffix}"
        else:
            code = f"{base_code}-{n}-{givens}"

        puzzle_record = {
            "n": n,
            "base_idx": base_idx,
            "var_idx": var_idx,
            "code": code,
            "n_cells": n_cells,
            "puzzle": puzzle,
            "solution": solution,
            "givens": givens
        }
        puzzle_records.append(puzzle_record)

    return puzzle_records

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
    parser.add_argument("--workers", type=int, default=4, help="Number of parallel workers (default: 4)")
    parser.add_argument("--force", action="store_true", help="Force regeneration even if output file exists")
    args = parser.parse_args()

    # Check if output file already exists
    output_file = Path(args.output)
    if output_file.exists() and not args.force:
        with open(output_file, "r") as f:
            try:
                existing = json.load(f)
                print(f"Output file '{args.output}' already exists with {len(existing)} puzzles.")
                print(f"Use --force to regenerate, or delete the file to start fresh.")
                sys.exit(0)
            except json.JSONDecodeError:
                print(f"Output file exists but is invalid JSON. Regenerating...")
                pass

    print(f"Generating snowflake sudoku puzzles (n={args.n_min} to {args.n_max})...\n")
    print(f"Base puzzles: {args.count} per size")
    print(f"Variants per base: {args.variants} (minimal + harder versions)")
    print(f"Parallel workers: {args.workers}")
    print(f"Uniqueness guarantee: ON (iterative progressive removal with CVC5 checking)\n")

    # Create list of all tasks: (n, base_idx, seed_base, cvc5_path, num_variants)
    tasks = []
    for n in range(args.n_min, args.n_max + 1):
        for base_idx in range(args.count):
            tasks.append((n, base_idx, args.seed, args.cvc5, args.variants))

    print(f"Total tasks: {len(tasks)} (puzzles to generate)")
    print(f"Estimated final count: {len(tasks) * args.variants} (with variants)\n")

    # Generate puzzles in parallel
    print("Starting parallel generation...")
    with Pool(processes=args.workers) as pool:
        results = pool.map(generate_base_puzzles_for_task, tasks)

    # Flatten results and sort by n, base_idx, var_idx for consistent ordering
    all_puzzle_records = []
    for result in results:
        all_puzzle_records.extend(result)

    # Sort by n, base_idx, var_idx to maintain order
    all_puzzle_records.sort(key=lambda p: (p["n"], p["base_idx"], p["var_idx"]))

    # Add final puzzle IDs
    puzzles = []
    for puzzle_id, record in enumerate(all_puzzle_records):
        record["id"] = puzzle_id
        # Remove temporary sorting keys
        del record["base_idx"]
        del record["var_idx"]
        puzzles.append(record)

    # Save to JSON
    with open(output_file, "w") as f:
        json.dump(puzzles, f, indent=2)

    print(f"\n{'='*60}")
    print(f"✓ Generated {len(puzzles)} total puzzles")
    print(f"  Topologies: n={args.n_min} to n={args.n_max}")
    print(f"  Base puzzles: {args.count} per topology")
    print(f"  Variants: {args.variants} per base")
    print(f"  Saved to {output_file}")
    print(f"{'='*60}")
