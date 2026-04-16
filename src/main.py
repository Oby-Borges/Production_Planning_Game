"""Entry point for Production Planning Game deterministic planning workflow."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

import pandas as pd

from aggregate_planning import (
    build_chase_strategy,
    build_hybrid_candidates,
    build_level_strategy,
)
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


def _candidate_display_name(candidate: Dict[str, Any]) -> str:
    """Return a short display label for a candidate plan."""
    if candidate["strategy"] == "hybrid" and candidate.get("hybrid_rank") is not None:
        return f"Hybrid #{candidate['hybrid_rank']}"
    return candidate["strategy"].capitalize()


def generate_plan_results(write_outputs: bool = True, print_summary: bool = False) -> Dict[str, Any]:
    """Run the full planning workflow and return a serializable result bundle."""
    inputs = load_inputs()
    requested_aggregate_outcomes = _compute_requested_aggregate_outcomes(inputs)
    outputs_dir = project_root() / "outputs"
    if write_outputs:
        ensure_dir(outputs_dir)

    # 1) Aggregate search: keep benchmarks plus the top K hybrid candidates.
    chase_plan = build_chase_strategy(inputs)
    level_plan = build_level_strategy(inputs)
    hybrid_candidates = build_hybrid_candidates(inputs, limit=5)
    candidate_pool: List[Dict[str, Any]] = [
        {"candidate_id": "chase", "strategy": "chase", "plan": chase_plan, "hybrid_rank": None},
        {"candidate_id": "level", "strategy": "level", "plan": level_plan, "hybrid_rank": None},
    ]
    for idx, plan in enumerate(hybrid_candidates, start=1):
        candidate_pool.append(
            {
                "candidate_id": f"hybrid_{idx}",
                "strategy": "hybrid",
                "plan": plan,
                "hybrid_rank": idx,
            }
        )

    stage_runs: Dict[str, Dict[str, Any]] = {}
    aggregate_stage_rows: List[Dict[str, Any]] = []
    for candidate in candidate_pool:
        plan = candidate["plan"]
        candidate_id = candidate["candidate_id"]
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

        stage_runs[candidate_id] = {
            "candidate_id": candidate_id,
            "display_name": _candidate_display_name(candidate),
            "strategy": candidate["strategy"],
            "hybrid_rank": candidate["hybrid_rank"],
            "aggregate_plan": plan,
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

        costs = plan.cost_breakdown
        if candidate["strategy"] == "chase":
            requested = requested_aggregate_outcomes["chase"]
            display_total = requested["costs"]["total_cost"]
        elif candidate["strategy"] == "level":
            requested = requested_aggregate_outcomes["level"]
            display_total = requested["costs"]["total_cost"]
        else:
            display_total = costs["total_cost"]

        feasibility_summary = plan.to_dict().get("feasibility_summary", {})
        aggregate_stage_rows.append(
            {
                "candidate_id": candidate_id,
                "display_name": _candidate_display_name(candidate),
                "strategy": candidate["strategy"],
                "hybrid_rank": candidate["hybrid_rank"],
                "feasible": plan.feasible,
                "aggregate_feasible": feasibility_summary.get("aggregate_feasible", plan.feasible),
                "inventory_constraints_satisfied": feasibility_summary.get("inventory_constraints_satisfied", plan.feasible),
                "overtime_constraints_satisfied": feasibility_summary.get("overtime_constraints_satisfied", True),
                "divisibility_rules_satisfied": feasibility_summary.get("divisibility_rules_satisfied", True),
                "initial_inventory": plan.initial_inventory,
                "regular_hours_q1": plan.regular_hours[0],
                "regular_hours_q2": plan.regular_hours[1],
                "regular_hours_q3": plan.regular_hours[2],
                "overtime_hours_q1": plan.overtime_hours[0],
                "overtime_hours_q2": plan.overtime_hours[1],
                "overtime_hours_q3": plan.overtime_hours[2],
                "material_cost": costs["material_cost"],
                "regular_labor_cost": costs["regular_labor_cost"],
                "overtime_labor_cost": costs["overtime_labor_cost"],
                "training_cost": costs["training_cost"],
                "relocation_cost": costs["relocation_cost"],
                "aggregate_inventory_holding_cost": costs["aggregate_inventory_holding_cost"],
                "initial_inventory_acquisition_cost": costs["initial_inventory_acquisition_cost"],
                "total_cost": display_total,
                "warnings": " | ".join(plan.warnings),
            }
        )
    aggregate_stage_rows = sorted(aggregate_stage_rows, key=lambda row: row["total_cost"])
    for rank, row in enumerate(aggregate_stage_rows, start=1):
        row["aggregate_rank"] = rank
    comparison_df = pd.DataFrame(aggregate_stage_rows)
    if write_outputs:
        comparison_df.to_csv(outputs_dir / "strategy_cost_comparison.csv", index=False)

    # Stage-aware final selection: only full-feasible candidates can win.
    full_feasible_ids = [cid for cid, run in stage_runs.items() if run["full_feasible"]]
    if full_feasible_ids:
        best_candidate_id = min(full_feasible_ids, key=lambda cid: stage_runs[cid]["total_planning_cost"])
    else:
        best_candidate_id = aggregate_stage_rows[0]["candidate_id"]
    best_run = stage_runs[best_candidate_id]
    best_plan = best_run["aggregate_plan"]
    best_name = best_run["strategy"]

    aggregate_tables: Dict[str, pd.DataFrame] = {}
    for candidate in candidate_pool:
        plan_df = aggregate_plan_df(candidate["plan"])
        aggregate_tables[candidate["candidate_id"]] = plan_df
        if write_outputs:
            plan_df.to_csv(outputs_dir / f"aggregate_plan_{candidate['candidate_id']}.csv", index=False)

    # 2) Use the best fully feasible final plan for downstream outputs.
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
    report_best_name = best_run["display_name"] if best_run["display_name"] in {
        _candidate_display_name(candidate)
        for candidate in candidate_pool
        if candidate["candidate_id"] in {"chase", "level", "hybrid_1", best_candidate_id}
    } else best_name
    plans_for_report = {
        _candidate_display_name(candidate): candidate["plan"]
        for candidate in candidate_pool
        if candidate["candidate_id"] in {"chase", "level", "hybrid_1", best_candidate_id}
    }
    if write_outputs:
        write_summary_report(report_path, report_best_name, plans_for_report, mps_summary, mrp_summary_df)
        report_text = report_path.read_text(encoding="utf-8")
    else:
        temp_report = project_root() / "summary_report_preview.txt"
        write_summary_report(temp_report, report_best_name, plans_for_report, mps_summary, mrp_summary_df)
        report_text = temp_report.read_text(encoding="utf-8")
        temp_report.unlink(missing_ok=True)

    if print_summary:
        print_terminal_summary(report_best_name, plans_for_report, mps_summary, mrp_summary_df)

    mrp_warnings = []
    for fruit_result in mrp_results.values():
        mrp_warnings.extend(fruit_result["l4l"]["warnings"])
        mrp_warnings.extend(fruit_result["silver_meal"]["warnings"])
    all_warnings = best_plan.warnings + mps_summary["warnings"] + mrp_warnings
    output_files = sorted(path.name for path in outputs_dir.glob("*")) if outputs_dir.exists() else []
    serialized_plans = {}
    for candidate in candidate_pool:
        cid = candidate["candidate_id"]
        plan = candidate["plan"]
        serialized_plans[cid] = {
            **plan.to_dict(),
            "display_name": _candidate_display_name(candidate),
            "selected": cid == best_candidate_id,
            "mps_feasible": stage_runs[cid]["mps_feasible"],
            "mrp_feasible": stage_runs[cid]["mrp_feasible"],
            "full_feasible": stage_runs[cid]["full_feasible"],
            "total_planning_cost": stage_runs[cid]["total_planning_cost"],
            "candidate_id": cid,
        }

    # Preserve benchmark aliases for existing UI sections.
    serialized_plans["chase_benchmark"] = serialized_plans["chase"]
    serialized_plans["level_benchmark"] = serialized_plans["level"]
    if hybrid_candidates:
        serialized_plans["hybrid_benchmark"] = serialized_plans["hybrid_1"]

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
                "best_candidate_id": best_candidate_id,
                "best_strategy": best_run["display_name"],
                "best_strategy_type": best_run["strategy"],
                "best_total_cost": best_run["total_planning_cost"],
                "aggregate_cost": best_plan.cost_breakdown["total_cost"],
                "cheapest_aggregate_candidate_id": aggregate_stage_rows[0]["candidate_id"],
                "cheapest_aggregate_plan": aggregate_stage_rows[0]["display_name"],
                "cheapest_aggregate_cost": aggregate_stage_rows[0]["total_cost"],
                "cheapest_final_plan": best_run["display_name"],
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
            "aggregate_stage_summary": aggregate_stage_rows,
            "mps_stage_summary": [
                {
                    "candidate_id": cid,
                    "display_name": run["display_name"],
                    "strategy": run["strategy"],
                    "aggregate_cost": run["aggregate_plan"].cost_breakdown["total_cost"],
                    "aggregate_rank": next(row["aggregate_rank"] for row in aggregate_stage_rows if row["candidate_id"] == cid),
                    "mps_feasible": run["mps_feasible"],
                    "setup_switches": run["mps_summary"]["setup_switches"],
                    "setup_cost": run["mps_summary"]["setup_cost"],
                    "warnings": run["mps_summary"]["warnings"],
                }
                for cid, run in stage_runs.items()
            ],
            "mrp_stage_summary": [
                {
                    "candidate_id": cid,
                    "display_name": run["display_name"],
                    "strategy": run["strategy"],
                    "mps_feasible": run["mps_feasible"],
                    "mrp_feasible": run["mrp_feasible"],
                    "chosen_mrp_cost": float(run["mrp_summary_df"]["chosen_total_cost"].sum()),
                    "fruit_methods": [
                        {
                            "fruit": row["fruit"],
                            "initial_inventory": row["initial_inventory"],
                            "chosen_method": row["chosen_method"],
                            "chosen_total_cost": row["chosen_total_cost"],
                            "feasible": row["feasible"],
                        }
                        for row in run["mrp_summary_df"].to_dict(orient="records")
                    ],
                    "warnings": [
                        *sum((res["l4l"]["warnings"] for res in run["mrp_results"].values()), []),
                        *sum((res["silver_meal"]["warnings"] for res in run["mrp_results"].values()), []),
                    ],
                }
                for cid, run in stage_runs.items()
                if run["mps_feasible"]
            ],
            "final_ranking": sorted(
                [
                    {
                        "candidate_id": cid,
                        "display_name": run["display_name"],
                        "strategy": run["strategy"],
                        "aggregate_rank": next(row["aggregate_rank"] for row in aggregate_stage_rows if row["candidate_id"] == cid),
                        "aggregate_cost": run["aggregate_plan"].cost_breakdown["total_cost"],
                        "mps_feasible": run["mps_feasible"],
                        "setup_cost": run["mps_summary"]["setup_cost"],
                        "mrp_feasible": run["mrp_feasible"],
                        "mrp_chosen_cost": float(run["mrp_summary_df"]["chosen_total_cost"].sum()),
                        "final_total_cost": run["total_planning_cost"],
                        "full_feasible": run["full_feasible"],
                    }
                    for cid, run in stage_runs.items()
                ],
                key=lambda row: (not row["full_feasible"], row["final_total_cost"]),
            ),
            "aggregate_tables": {
                name: df.to_dict(orient="records")
                for name, df in aggregate_tables.items()
            },
            "aggregate_best_table": aggregate_plan_df(best_plan).to_dict(orient="records"),
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
