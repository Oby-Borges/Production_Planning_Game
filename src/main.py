"""Entry point for Production Planning Game deterministic planning workflow."""

from __future__ import annotations

from pathlib import Path

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


def run() -> None:
    """Run full planning pipeline and export required outputs."""
    inputs = load_inputs()
    outputs_dir = project_root() / "outputs"
    ensure_dir(outputs_dir)

    # 1) Aggregate strategy generation and comparison.
    plans = build_all_strategies(inputs)
    best_plan = choose_best_strategy(plans)
    best_name = best_plan.strategy

    comparison_df = strategy_comparison_df(plans)
    comparison_df.to_csv(outputs_dir / "strategy_cost_comparison.csv", index=False)

    for strategy_name, plan in plans.items():
        aggregate_plan_df(plan).to_csv(outputs_dir / f"aggregate_plan_{strategy_name}.csv", index=False)

    # 2) Disaggregate best strategy to product level.
    disagg_df, disagg_detail = build_disaggregate_plan(inputs, best_plan.to_dict())
    disagg_df.to_csv(outputs_dir / "disaggregate_plan_best.csv", index=False)

    # 3) Build MPS for best strategy.
    mps_df, mps_summary = build_mps(inputs, best_plan.to_dict(), disagg_detail)
    mps_df.to_csv(outputs_dir / "mps_best.csv", index=False)

    # 4) Build MRP and lot-sizing comparisons.
    mrp_results, mrp_summary_df = build_all_mrp(inputs, mps_summary["period_product_production"])
    mrp_summary_df.to_csv(outputs_dir / "mrp_best_summary.csv", index=False)

    for fruit, res in mrp_results.items():
        key = fruit.lower().replace(" ", "_")
        mrp_rows_to_df(res["l4l"]["rows"]).to_csv(outputs_dir / f"mrp_{key}_l4l.csv", index=False)
        mrp_rows_to_df(res["silver_meal"]["rows"]).to_csv(
            outputs_dir / f"mrp_{key}_silver_meal.csv", index=False
        )

    # 5) Human-readable report + terminal summary.
    write_summary_report(outputs_dir / "summary_report.txt", best_name, plans, mps_summary, mrp_summary_df)
    print_terminal_summary(best_name, plans, mps_summary, mrp_summary_df)


if __name__ == "__main__":
    run()
