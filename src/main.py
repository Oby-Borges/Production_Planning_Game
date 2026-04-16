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
    outputs_dir = project_root() / "outputs"
    if write_outputs:
        ensure_dir(outputs_dir)

    # 1) Aggregate strategy generation and comparison.
    plans = build_all_strategies(inputs)
    best_plan = choose_best_strategy(plans)
    best_name = best_plan.strategy

    comparison_df = strategy_comparison_df(plans)
    if write_outputs:
        comparison_df.to_csv(outputs_dir / "strategy_cost_comparison.csv", index=False)

    aggregate_tables: Dict[str, pd.DataFrame] = {}
    for strategy_name, plan in plans.items():
        plan_df = aggregate_plan_df(plan)
        aggregate_tables[strategy_name] = plan_df
        if write_outputs:
            plan_df.to_csv(outputs_dir / f"aggregate_plan_{strategy_name}.csv", index=False)

    # 2) Disaggregate best strategy to product level.
    disagg_df, disagg_detail = build_disaggregate_plan(inputs, best_plan.to_dict())
    if write_outputs:
        disagg_df.to_csv(outputs_dir / "disaggregate_plan_best.csv", index=False)

    # 3) Build MPS for best strategy.
    mps_df, mps_summary = build_mps(inputs, best_plan.to_dict(), disagg_detail)
    if write_outputs:
        mps_df.to_csv(outputs_dir / "mps_best.csv", index=False)

    # 4) Build MRP and lot-sizing comparisons.
    mrp_results, mrp_summary_df = build_all_mrp(inputs, mps_summary["period_product_production"])
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

    all_warnings = best_plan.warnings + mps_summary["warnings"]
    output_files = sorted(path.name for path in outputs_dir.glob("*")) if outputs_dir.exists() else []
    serialized_plans = {}
    for name, plan in plans.items():
        serialized_plans[name] = {
            **plan.to_dict(),
            "selected": name == best_name,
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
                "best_total_cost": plans[best_name].cost_breakdown["total_cost"],
                "setup_cost": mps_summary["setup_cost"],
                "setup_switches": mps_summary["setup_switches"],
                "warnings_count": len(all_warnings),
                "warnings": all_warnings,
                "overtime_by_period": mps_summary["overtime_by_period"],
                "regular_by_period": mps_summary["regular_by_period"],
                "output_files": output_files,
            },
            "inputs": inputs,
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
