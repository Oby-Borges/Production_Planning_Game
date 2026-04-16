"""Entry point for Production Planning Game deterministic planning workflow."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

import pandas as pd

from aggregate_planning import build_all_strategies, choose_best_strategy
from data_loader import load_inputs
from disaggregate import build_disaggregate_plan
from mps import build_mps
from mrp import build_all_mrp, mrp_rows_to_df
from reporting import (
    aggregate_plan_df,
    print_terminal_summary,
    strategy_comparison_df,
    write_summary_report,
)
from utils import ensure_dir, project_root


def _compute_requested_aggregate_outcomes(inputs: Dict[str, Any]) -> Dict[str, Any]:
    """Compute the exact chase and level outcomes from the user's simplified aggregate rules."""
    cfg = inputs["aggregate"]
    demands = [cfg["forecast_quarterly_demand"][f"Q{i}"] for i in range(1, 4)]
    labor_per_unit = cfg["average_labor_hours_per_unit"]
    material_cost = cfg["average_material_cost_per_unit"]
    reg_rate = cfg["regular_labor_cost_per_hour"]
    train_rate = cfg["training_cost_per_hour_change"]
    reloc_rate = cfg["relocation_cost_per_hour_change"]
    hold_rate = cfg["holding_cost_per_unit_quarter"]
    initial_regular = cfg["initial_regular_hours_q1"]

    total_units = sum(demands)

    chase_regular = [d * labor_per_unit for d in demands]
    chase_training = max(0, chase_regular[0] - initial_regular) * train_rate
    for prev, curr in zip(chase_regular, chase_regular[1:]):
        if curr > prev:
            chase_training += (curr - prev) * train_rate
    chase_relocation = sum(max(0, prev - curr) * reloc_rate for prev, curr in zip(chase_regular, chase_regular[1:]))
    chase_rows = []
    for quarter_idx, demand in enumerate(demands):
        chase_rows.append(
            {
                "Quarter": f"Q{quarter_idx + 1}",
                "Demand": demand,
                "Production": demand,
                "Total Labor Hours": chase_regular[quarter_idx],
                "Ending Inventory": 0,
            }
        )

    # Level strategy per the user's exact instructions:
    # minimum feasible constant production with no backorders.
    level_production = max(
        demands[0],
        (demands[0] + demands[1] + 1) // 2,
        (sum(demands) + 2) // 3,
    )
    level_regular_hours = level_production * labor_per_unit
    level_inventory = []
    on_hand = 0
    for demand in demands:
        on_hand = on_hand + level_production - demand
        level_inventory.append(on_hand)
    level_rows = []
    for quarter_idx, demand in enumerate(demands):
        level_rows.append(
            {
                "Quarter": f"Q{quarter_idx + 1}",
                "Demand": demand,
                "Production": level_production,
                "Total Labor Hours": level_regular_hours,
                "Ending Inventory": level_inventory[quarter_idx],
            }
        )

    return {
        "chase": {
            "plan_rows": chase_rows,
            "labor_rows": [
                {"Quarter": "Q1", "Regular Hours": chase_regular[0], "Overtime Hours": 0},
                {"Quarter": "Q2", "Regular Hours": chase_regular[1], "Overtime Hours": 0},
                {"Quarter": "Q3", "Regular Hours": chase_regular[2], "Overtime Hours": 0},
            ],
            "costs": {
                "material_cost": total_units * material_cost,
                "regular_labor_cost": sum(chase_regular) * reg_rate,
                "training_cost": chase_training,
                "relocation_cost": chase_relocation,
                "inventory_holding_cost": 0,
                "total_cost": (total_units * material_cost) + (sum(chase_regular) * reg_rate) + chase_training + chase_relocation,
            },
        },
        "level": {
            "plan_rows": level_rows,
            "labor_rows": [
                {"Quarter": "Q1", "Regular Hours": level_regular_hours, "Overtime Hours": 0},
                {"Quarter": "Q2", "Regular Hours": level_regular_hours, "Overtime Hours": 0},
                {"Quarter": "Q3", "Regular Hours": level_regular_hours, "Overtime Hours": 0},
            ],
            "costs": {
                "material_cost": total_units * material_cost,
                "regular_labor_cost": (level_regular_hours * 3) * reg_rate,
                "training_cost": max(0, level_regular_hours - initial_regular) * train_rate,
                "relocation_cost": 0,
                "inventory_holding_cost": sum(level_inventory) * hold_rate,
                "total_cost": (
                    (total_units * material_cost)
                    + ((level_regular_hours * 3) * reg_rate)
                    + (max(0, level_regular_hours - initial_regular) * train_rate)
                    + (sum(level_inventory) * hold_rate)
                ),
            },
            "constant_production": level_production,
        },
    }


def _round_nested(value: Any) -> Any:
    """Round nested float values for cleaner JSON serialization."""
    if isinstance(value, dict):
        return {k: _round_nested(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_round_nested(v) for v in value]
    if isinstance(value, float):
        return round(value, 2)
    return value


def generate_plan_results(write_outputs: bool = True, print_summary: bool = False) -> Dict[str, Any]:
    """Run the full planning workflow and return a serializable result bundle."""
    inputs = load_inputs()
    requested_aggregate_outcomes = _compute_requested_aggregate_outcomes(inputs)
    outputs_dir = project_root() / "outputs"
    if write_outputs:
        ensure_dir(outputs_dir)

    # 1) Aggregate strategy generation and comparison.
    plans = build_all_strategies(inputs)
    scenario_runs: Dict[str, Dict[str, Any]] = {}
    for strategy_name, plan in plans.items():
        disagg_df, disagg_detail = build_disaggregate_plan(inputs, plan.to_dict())
        mps_df, mps_summary = build_mps(inputs, plan.to_dict(), disagg_detail)
        mrp_results, mrp_summary_df = build_all_mrp(inputs, mps_summary["period_product_production"])

        mps_feasible = len(mps_summary["warnings"]) == 0
        mrp_feasible = all(result["feasible"] for result in mrp_results.values())
        total_planning_cost = (
            plan.cost_breakdown["total_cost"]
            + mps_summary["setup_cost"]
            + float(mrp_summary_df["chosen_total_cost"].sum())
        )

        scenario_runs[strategy_name] = {
            "disaggregate_df": disagg_df,
            "disaggregate_detail": disagg_detail,
            "mps_df": mps_df,
            "mps_summary": mps_summary,
            "mrp_results": mrp_results,
            "mrp_summary_df": mrp_summary_df,
            "mps_feasible": mps_feasible,
            "mrp_feasible": mrp_feasible,
            "full_feasible": plan.feasible and mps_feasible and mrp_feasible,
            "total_planning_cost": total_planning_cost,
        }

    fully_feasible = [name for name, run in scenario_runs.items() if run["full_feasible"]]
    if fully_feasible:
        best_name = min(fully_feasible, key=lambda name: scenario_runs[name]["total_planning_cost"])
    else:
        best_name = choose_best_strategy(plans).strategy
    best_plan = plans[best_name]
    best_run = scenario_runs[best_name]

    comparison_df = strategy_comparison_df(plans)
    comparison_df["mps_feasible"] = comparison_df["strategy"].map(
        lambda name: scenario_runs[name]["mps_feasible"]
    )
    comparison_df["mrp_feasible"] = comparison_df["strategy"].map(
        lambda name: scenario_runs[name]["mrp_feasible"]
    )
    comparison_df["full_feasible"] = comparison_df["strategy"].map(
        lambda name: scenario_runs[name]["full_feasible"]
    )
    comparison_df["setup_cost"] = comparison_df["strategy"].map(
        lambda name: scenario_runs[name]["mps_summary"]["setup_cost"]
    )
    comparison_df["mrp_chosen_cost"] = comparison_df["strategy"].map(
        lambda name: float(scenario_runs[name]["mrp_summary_df"]["chosen_total_cost"].sum())
    )
    comparison_df["total_planning_cost"] = comparison_df["strategy"].map(
        lambda name: scenario_runs[name]["total_planning_cost"]
    )
    if write_outputs:
        comparison_df.to_csv(outputs_dir / "strategy_cost_comparison.csv", index=False)

    aggregate_tables: Dict[str, pd.DataFrame] = {}
    for strategy_name, plan in plans.items():
        plan_df = aggregate_plan_df(plan)
        aggregate_tables[strategy_name] = plan_df
        if write_outputs:
            plan_df.to_csv(outputs_dir / f"aggregate_plan_{strategy_name}.csv", index=False)

    # 2) Use the fully evaluated best strategy for downstream outputs.
    disagg_df = best_run["disaggregate_df"]
    disagg_detail = best_run["disaggregate_detail"]
    if write_outputs:
        disagg_df.to_csv(outputs_dir / "disaggregate_plan_best.csv", index=False)

    # 3) Best-strategy MPS.
    mps_df = best_run["mps_df"]
    mps_summary = best_run["mps_summary"]
    if write_outputs:
        mps_df.to_csv(outputs_dir / "mps_best.csv", index=False)

    # 4) Best-strategy MRP and lot-sizing comparisons.
    mrp_results = best_run["mrp_results"]
    mrp_summary_df = best_run["mrp_summary_df"]
    if write_outputs:
        mrp_summary_df.to_csv(outputs_dir / "mrp_best_summary.csv", index=False)

    for fruit, res in mrp_results.items():
        key = fruit.lower().replace(" ", "_")
        if write_outputs:
            mrp_rows_to_df(res["l4l"]["rows"]).to_csv(outputs_dir / f"mrp_{key}_l4l.csv", index=False)
            mrp_rows_to_df(res["silver_meal"]["rows"]).to_csv(
                outputs_dir / f"mrp_{key}_silver_meal.csv", index=False
            )

    # 5) Human-readable report + terminal summary.
    report_path = outputs_dir / "summary_report.txt"
    if write_outputs:
        write_summary_report(report_path, best_name, plans, mps_summary, mrp_summary_df)
        report_text = report_path.read_text(encoding="utf-8")
    else:
        temp_report = project_root() / "summary_report_preview.txt"
        write_summary_report(temp_report, best_name, plans, mps_summary, mrp_summary_df)
        report_text = temp_report.read_text(encoding="utf-8")
        temp_report.unlink(missing_ok=True)

    if print_summary:
        print_terminal_summary(best_name, plans, mps_summary, mrp_summary_df)

    mrp_warnings = []
    for fruit_result in mrp_results.values():
        mrp_warnings.extend(fruit_result["l4l"]["warnings"])
        mrp_warnings.extend(fruit_result["silver_meal"]["warnings"])
    all_warnings = best_plan.warnings + mps_summary["warnings"] + mrp_warnings
    output_files = sorted(path.name for path in outputs_dir.glob("*")) if outputs_dir.exists() else []
    serialized_plans = {}
    for name, plan in plans.items():
        serialized_plans[name] = {
            **plan.to_dict(),
            "selected": name == best_name,
            "mps_feasible": scenario_runs[name]["mps_feasible"],
            "mrp_feasible": scenario_runs[name]["mrp_feasible"],
            "full_feasible": scenario_runs[name]["full_feasible"],
            "total_planning_cost": scenario_runs[name]["total_planning_cost"],
        }

    mrp_tables: Dict[str, Dict[str, Any]] = {}
    for fruit, result in mrp_results.items():
        mrp_tables[fruit] = {
            "chosen": result["chosen"],
            "initial_inventory": result["initial_inventory"],
            "l4l": {
                "rows": result["l4l"]["rows"],
                "cost": result["l4l"]["cost"],
            },
            "silver_meal": {
                "rows": result["silver_meal"]["rows"],
                "cost": result["silver_meal"]["cost"],
            },
        }

    return _round_nested(
        {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "best_strategy": best_name,
            "summary": {
                "best_strategy": best_name,
                "best_total_cost": scenario_runs[best_name]["total_planning_cost"],
                "aggregate_cost": plans[best_name].cost_breakdown["total_cost"],
                "setup_cost": mps_summary["setup_cost"],
                "mrp_chosen_cost": float(mrp_summary_df["chosen_total_cost"].sum()),
                "setup_switches": mps_summary["setup_switches"],
                "warnings_count": len(all_warnings),
                "warnings": all_warnings,
                "overtime_by_period": mps_summary["overtime_by_period"],
                "regular_by_period": mps_summary["regular_by_period"],
                "output_files": output_files,
            },
            "inputs": inputs,
            "requested_aggregate_outcomes": requested_aggregate_outcomes,
            "strategy_comparison": comparison_df.to_dict(orient="records"),
            "aggregate_tables": {
                name: df.to_dict(orient="records")
                for name, df in aggregate_tables.items()
            },
            "plans": serialized_plans,
            "disaggregate": disagg_df.to_dict(orient="records"),
            "mps": {
                "rows": mps_df.to_dict(orient="records"),
                "summary": mps_summary,
            },
            "mrp_summary": mrp_summary_df.to_dict(orient="records"),
            "mrp_tables": mrp_tables,
            "summary_report": report_text,
        }
    )


def run() -> None:
    """Run full planning pipeline and export required outputs."""
    generate_plan_results(write_outputs=True, print_summary=True)


if __name__ == "__main__":
    run()
