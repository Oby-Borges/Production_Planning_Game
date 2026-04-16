"""Output export and terminal/report formatting helpers."""

from __future__ import annotations

from pathlib import Path
from typing import Dict

import pandas as pd


def strategy_comparison_df(plans: Dict[str, Dict]) -> pd.DataFrame:
    """Create strategy comparison dataframe for CSV export."""
    rows = []
    for name, plan in plans.items():
        c = plan.cost_breakdown
        rows.append(
            {
                "strategy": name,
                "feasible": plan.feasible,
                "initial_inventory": plan.initial_inventory,
                "regular_hours_q1": plan.regular_hours[0],
                "regular_hours_q2": plan.regular_hours[1],
                "regular_hours_q3": plan.regular_hours[2],
                "overtime_hours_q1": plan.overtime_hours[0],
                "overtime_hours_q2": plan.overtime_hours[1],
                "overtime_hours_q3": plan.overtime_hours[2],
                **c,
                "warnings": " | ".join(plan.warnings),
            }
        )
    return pd.DataFrame(rows).sort_values("total_cost")


def aggregate_plan_df(plan: Dict) -> pd.DataFrame:
    """Quarter-level aggregate detail table."""
    rows = []
    for q in range(3):
        rows.append(
            {
                "Quarter": q + 1,
                "Demand": plan.demand[q],
                "Production": plan.production[q],
                "Regular Hours": plan.regular_hours[q],
                "Overtime Hours": plan.overtime_hours[q],
                "Regular Units": plan.regular_units[q],
                "Overtime Units": plan.overtime_units[q],
                "Ending Inventory": plan.ending_inventory[q],
            }
        )
    return pd.DataFrame(rows)


def write_summary_report(
    out_path: Path,
    best_name: str,
    plans: Dict[str, Dict],
    mps_summary: Dict,
    mrp_summary_df: pd.DataFrame,
) -> None:
    """Write readable text summary for class submission."""
    lines = []
    lines.append("Production Planning Game - Deterministic Initial Plan Summary")
    lines.append("=" * 72)
    lines.append(f"Best aggregate strategy: {best_name}")
    lines.append("")
    lines.append("Strategy total planned costs:")
    for name, plan in plans.items():
        lines.append(f"- {name}: ${plan.cost_breakdown['total_cost']:,.2f}")

    best = plans[best_name]
    lines.append("")
    lines.append(f"Best strategy regular labor by quarter: {best.regular_hours}")
    lines.append(f"Best strategy overtime by quarter: {best.overtime_hours}")
    lines.append(f"Best strategy initial finished goods inventory: {best.initial_inventory}")

    lines.append("")
    lines.append("MPS notes:")
    lines.append(f"- Setup switches: {mps_summary['setup_switches']}")
    lines.append(f"- Setup cost: ${mps_summary['setup_cost']:,.2f}")

    lines.append("")
    lines.append("MRP chosen methods by fruit:")
    for _, r in mrp_summary_df.iterrows():
        lines.append(
            f"- {r['fruit']}: {r['chosen_method']} (initial inv={r['initial_inventory']}, chosen cost=${r['chosen_total_cost']:,.2f})"
        )

    if best.warnings or mps_summary["warnings"]:
        lines.append("")
        lines.append("Feasibility warnings:")
        for w in best.warnings:
            lines.append(f"- {w}")
        for w in mps_summary["warnings"]:
            lines.append(f"- {w}")

    out_path.write_text("\n".join(lines), encoding="utf-8")


def print_terminal_summary(
    best_name: str,
    plans: Dict[str, Dict],
    mps_summary: Dict,
    mrp_summary_df: pd.DataFrame,
) -> None:
    """Print short readable summary for terminal execution."""
    print("\n=== PRODUCTION PLANNING GAME SUMMARY ===")
    print(f"Best aggregate strategy: {best_name}")
    print("\nTotal cost by strategy:")
    for name, plan in plans.items():
        print(f"  - {name}: ${plan.cost_breakdown['total_cost']:,.2f}")

    best = plans[best_name]
    print(f"\nChosen regular labor by quarter: {best.regular_hours}")
    print(f"Overtime by quarter: {best.overtime_hours}")
    print(f"Initial finished-goods inventory: {best.initial_inventory}")
    print(f"Overtime by period (from MPS): {mps_summary['overtime_by_period']}")

    print("\nChosen lot-sizing rule per fruit:")
    for _, row in mrp_summary_df.iterrows():
        print(
            f"  - {row['fruit']}: {row['chosen_method']} (initial inv {row['initial_inventory']}, cost ${row['chosen_total_cost']:,.2f})"
        )

    warnings = best.warnings + mps_summary["warnings"]
    if warnings:
        print("\nFeasibility warnings:")
        for w in warnings:
            print(f"  - {w}")
    else:
        print("\nFeasibility warnings: None")
