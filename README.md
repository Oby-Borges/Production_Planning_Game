# Production Planning Game (Deterministic Initial Planning Model)

This repository contains a complete Python planning workflow for a Production Planning Game class project.  
It compares three aggregate planning strategies, chooses the best one by total planned cost, disaggregates into product-level planning, builds a 9-period MPS, and generates MRP tables for key fruit components using multiple lot-sizing methods.

## Purpose

The model is designed to be:
- **Readable** for students (heavy inline comments + modular files)
- **Editable** (all key assumptions in one JSON file)
- **Practical** (integer plans, feasible constraints, clear outputs)

## Project Structure

```text
production-planning-game/
  data/
    game_inputs.json
  outputs/
  src/
    main.py
    data_loader.py
    aggregate_planning.py
    disaggregate.py
    mps.py
    mrp.py
    costing.py
    reporting.py
    utils.py
  README.md
  requirements.txt
```

## Installation

1. Create and activate a virtual environment (recommended):
   - macOS/Linux:
     ```bash
     python -m venv .venv
     source .venv/bin/activate
     ```
   - Windows (PowerShell):
     ```powershell
     python -m venv .venv
     .venv\Scripts\Activate.ps1
     ```

2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

## How to Run

From repository root:

```bash
python src/main.py
```

The script will:
1. Generate and compare aggregate strategies (chase, level, hybrid)
2. Choose best strategy by total planned cost
3. Create disaggregate product plan
4. Create 9-period MPS
5. Generate MRP tables for each fruit with L4L and Silver-Meal
6. Choose lower-cost method per fruit
7. Export CSVs and a text summary to `outputs/`
8. Print a readable terminal summary

## Outputs Produced

- `strategy_cost_comparison.csv`: cost breakdown and feasibility across strategies
- `aggregate_plan_chase.csv`: quarterly chase strategy details
- `aggregate_plan_level.csv`: quarterly level strategy details
- `aggregate_plan_hybrid.csv`: quarterly hybrid strategy details
- `disaggregate_plan_best.csv`: product allocation for best strategy
- `mps_best.csv`: 9-period MPS with inventory, labor, and setup columns
- `mrp_blueberry_l4l.csv`
- `mrp_blueberry_silver_meal.csv`
- `mrp_pear_l4l.csv`
- `mrp_pear_silver_meal.csv`
- `mrp_strawberry_l4l.csv`
- `mrp_strawberry_silver_meal.csv`
- `mrp_banana_l4l.csv`
- `mrp_banana_silver_meal.csv`
- `mrp_best_summary.csv`: chosen lot-size method and cost comparison per fruit
- `summary_report.txt`: readable planning report

## Key Assumptions

- This is an **initial deterministic plan** based on mean period demand (std dev values are stored for future simulation use).
- Aggregate strategy selection uses:
  - labor costs (regular + overtime)
  - workforce change costs (training/relocation)
  - aggregate inventory holding cost
  - initial finished-goods inventory acquisition cost
- No backorders are allowed in level planning logic.
- Overtime capacity is limited by the game rule (50% of regular labor per period).
- Quarter regular hours are constrained to be divisible by 3.
- MPS setup cost is estimated from product switching sequence across periods.
- MRP for strawberry and banana accounts for imperfect quality by inflating order quantity to satisfy expected usable units.
- Initial fruit inventory is selected using a practical bounded search (`0..50` per fruit).

## How Best Strategy Is Chosen

1. Build candidate plans for chase, level, and hybrid.
2. Enforce feasibility checks (inventory and overtime constraints).
3. Compute total planned cost breakdown for each.
4. Pick the feasible strategy with lowest total planned cost.

## How to Modify Inputs Later

Edit `data/game_inputs.json`:
- Demand values
- Labor rates and limits
- Product attributes
- BOM and fruit data
- MRP settings (order cost, initial inventory bounds)
- Absenteeism stress-test flag for Q3 period scenario

Then re-run:
```bash
python src/main.py
```

## Limitations / Next Improvements

- Hybrid search is an enumeration-based heuristic (practical and understandable, not full mathematical programming).
- Aggregate-to-disaggregate reconciliation uses weighted integer allocation; for different use cases, you may want optimization-based reconciliation.
- MRP currently uses L4L and Silver-Meal; adding LUC is straightforward in `src/mrp.py`.
