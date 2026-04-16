"""Build 9-period deterministic MPS for best aggregate strategy."""

from __future__ import annotations

from typing import Dict, List, Tuple

import pandas as pd

from costing import setup_cost_from_switches


def _period_demands(inputs: Dict) -> List[Dict[str, int]]:
    """Expand quarter means to 9 period product demands."""
    products = inputs["products"]
    periods: List[Dict[str, int]] = []
    for q in ["Q1", "Q2", "Q3"]:
        for _ in range(3):
            periods.append({p: int(products[p]["period_demand"][q]["mean"]) for p in products})
    return periods


def _expand_quarter_production(disagg_detail: Dict[str, Dict[str, int]]) -> Dict[str, List[int]]:
    """Split quarterly production into period-level using near-even integers."""
    result: Dict[str, List[int]] = {}
    for product, vals in disagg_detail.items():
        period_vals: List[int] = []
        for q in ["Q1", "Q2", "Q3"]:
            q_total = vals[q]
            base = q_total // 3
            rem = q_total % 3
            arr = [base, base, base]
            for i in range(rem):
                arr[i] += 1
            period_vals.extend(arr)
        result[product] = period_vals
    return result


def _sequence_and_count_setups(produced_items: List[str], prev_last: str | None) -> Tuple[List[str], int, str | None]:
    """Choose production sequence to reduce setups and count switches."""
    if not produced_items:
        return [], 0, prev_last

    unique = list(dict.fromkeys(produced_items))
    if prev_last in unique:
        unique.remove(prev_last)
        sequence = [prev_last] + unique
    else:
        sequence = unique

    setups = 0
    current = prev_last
    for item in sequence:
        if current != item:
            setups += 1
        current = item

    last_item = sequence[-1]
    return sequence, setups, last_item


def build_mps(inputs: Dict, best_plan: Dict, disagg_detail: Dict[str, Dict[str, int]]) -> Tuple[pd.DataFrame, Dict]:
    """Build detailed period-by-period MPS with inventory and labor checks."""
    products = inputs["products"]
    period_demand = _period_demands(inputs)
    period_prod = _expand_quarter_production(disagg_detail)
    setup_cost = inputs["mps"]["setup_cost"]

    init_inventory = {p: disagg_detail[p]["initial_inventory"] for p in products}
    inventory = init_inventory.copy()

    regular_per_period: List[int] = []
    overtime_per_period: List[int] = []
    warnings: List[str] = []
    rows: List[Dict] = []

    setup_switches = 0
    prev_last_product = None

    absentee_cfg = inputs["mps"]["q3_absenteeism"]

    for period_idx in range(9):
        quarter_idx = period_idx // 3
        quarter_reg_hours = best_plan["regular_hours"][quarter_idx]
        quarter_ot_hours = best_plan["overtime_hours"][quarter_idx]

        reg_hours = quarter_reg_hours // 3
        ot_hours = quarter_ot_hours // 3
        # Push any remainder overtime to the final period of each quarter.
        if period_idx % 3 == 2:
            ot_hours += quarter_ot_hours - (quarter_ot_hours // 3) * 3

        if absentee_cfg.get("enabled") and period_idx == absentee_cfg.get("period_index"):
            reg_hours = int(round(reg_hours * (1.0 - absentee_cfg.get("reduction_ratio", 0.0))))

        regular_per_period.append(reg_hours)
        overtime_per_period.append(ot_hours)

        produced_items = [p for p in products if period_prod[p][period_idx] > 0]
        sequence, switches, prev_last_product = _sequence_and_count_setups(produced_items, prev_last_product)
        setup_switches += switches

        period_row = {
            "Period": period_idx + 1,
            "Quarter": quarter_idx + 1,
            "Regular Labor Hours": reg_hours,
            "Overtime Labor Hours": ot_hours,
            "Total Labor Hours Used": 0,
            "Setup Sequence": " -> ".join(sequence) if sequence else "No production",
            "Setup Switches": switches,
        }

        used_hours = 0
        for product, info in products.items():
            beg_inv = inventory[product]
            prod_qty = period_prod[product][period_idx]
            dem_qty = period_demand[period_idx][product]
            end_inv = beg_inv + prod_qty - dem_qty
            if end_inv < 0:
                warnings.append(
                    f"Period {period_idx+1} {product}: negative inventory {end_inv}; adjusted with emergency production."
                )
                # Emergency correction to keep no-backorder requirement intact.
                prod_qty += abs(end_inv)
                end_inv = 0
                period_prod[product][period_idx] = prod_qty

            used_hours += prod_qty * info["labor_hours"]
            inventory[product] = end_inv

            period_row[f"{product} Beg Inv"] = beg_inv
            period_row[f"{product} Demand"] = dem_qty
            period_row[f"{product} Production"] = prod_qty
            period_row[f"{product} End Inv"] = end_inv

        period_row["Total Labor Hours Used"] = used_hours

        if used_hours > reg_hours + ot_hours:
            warnings.append(
                f"Period {period_idx+1}: labor usage {used_hours} exceeds available {reg_hours + ot_hours}."
            )

        period_row["Feasible Labor?\n"] = "Yes" if used_hours <= reg_hours + ot_hours else "No"
        rows.append(period_row)

    df = pd.DataFrame(rows)
    total_setup_cost = setup_cost_from_switches(setup_switches, setup_cost)

    summary = {
        "warnings": warnings,
        "setup_switches": setup_switches,
        "setup_cost": total_setup_cost,
        "regular_by_period": regular_per_period,
        "overtime_by_period": overtime_per_period,
        "period_product_production": period_prod,
    }
    return df, summary
