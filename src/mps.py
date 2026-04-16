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


def _period_labor_hours(best_plan: Dict, absentee_cfg: Dict) -> Tuple[List[int], List[int]]:
    """Expand aggregate quarterly hours into period-level regular and overtime hours."""
    regular_per_period: List[int] = []
    overtime_per_period: List[int] = []

    for period_idx in range(9):
        quarter_idx = period_idx // 3
        quarter_reg_hours = best_plan["regular_hours"][quarter_idx]
        quarter_ot_hours = best_plan["overtime_hours"][quarter_idx]

        reg_hours = quarter_reg_hours // 3
        ot_hours = quarter_ot_hours // 3
        if period_idx % 3 == 2:
            ot_hours += quarter_ot_hours - (quarter_ot_hours // 3) * 3

        if absentee_cfg.get("enabled") and period_idx == absentee_cfg.get("period_index"):
            reg_hours = int(round(reg_hours * (1.0 - absentee_cfg.get("reduction_ratio", 0.0))))

        regular_per_period.append(reg_hours)
        overtime_per_period.append(ot_hours)

    return regular_per_period, overtime_per_period


def _build_period_production(
    inputs: Dict,
    best_plan: Dict,
    disagg_detail: Dict[str, Dict[str, int]],
    period_demand: List[Dict[str, int]],
    regular_per_period: List[int],
    overtime_per_period: List[int],
) -> Dict[str, List[int]]:
    """Build a period MPS that respects quarter totals while delaying extra inventory when possible."""
    products = inputs["products"]
    names = list(products.keys())
    quarter_labels = ["Q1", "Q2", "Q3"]

    period_prod: Dict[str, List[int]] = {p: [0] * 9 for p in names}
    inventory = {p: disagg_detail[p]["initial_inventory"] for p in names}

    for quarter_idx, quarter_label in enumerate(quarter_labels):
        period_indices = list(range(quarter_idx * 3, quarter_idx * 3 + 3))
        remaining_quarter_prod = {p: disagg_detail[p][quarter_label] for p in names}
        remaining_capacity = {
            idx: regular_per_period[idx] + overtime_per_period[idx]
            for idx in period_indices
        }
        planning_inventory = inventory.copy()

        # First, produce the minimum needed each period to avoid product shortages
        # while honoring the quarter production totals selected earlier.
        for idx in period_indices:
            for product in names:
                demand = period_demand[idx][product]
                required = max(0, demand - planning_inventory[product])
                produce = min(required, remaining_quarter_prod[product])
                period_prod[product][idx] += produce
                remaining_quarter_prod[product] -= produce
                remaining_capacity[idx] -= produce * products[product]["labor_hours"]
                planning_inventory[product] += produce - demand

        # Then place the remaining quarter production as late as possible to keep
        # early-period finished-goods and component needs lower, which better
        # matches the packet's synchronization between MPS and MRP.
        for idx in reversed(period_indices):
            made_progress = True
            while made_progress:
                made_progress = False
                for product in sorted(names, key=lambda name: products[name]["labor_hours"]):
                    labor_hours = products[product]["labor_hours"]
                    if remaining_quarter_prod[product] <= 0 or remaining_capacity[idx] < labor_hours:
                        continue
                    period_prod[product][idx] += 1
                    remaining_quarter_prod[product] -= 1
                    remaining_capacity[idx] -= labor_hours
                    made_progress = True

        # Update inventory through the quarter using the finished plan so the next
        # quarter starts with the correct carryover.
        for idx in period_indices:
            for product in names:
                inventory[product] += period_prod[product][idx]
                inventory[product] -= period_demand[idx][product]

    return period_prod


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

    # The packet charges setup cost when switching from one smoothie to another.
    # Starting the very first product in period 1 is not a "switch", so we only
    # count transitions after there is already an active setup.
    setups = 0
    current = prev_last
    for item in sequence:
        if current is not None and current != item:
            setups += 1
        current = item

    last_item = sequence[-1]
    return sequence, setups, last_item


def build_mps(inputs: Dict, best_plan: Dict, disagg_detail: Dict[str, Dict[str, int]]) -> Tuple[pd.DataFrame, Dict]:
    """Build detailed period-by-period MPS with inventory and labor checks."""
    products = inputs["products"]
    period_demand = _period_demands(inputs)
    setup_cost = inputs["mps"]["setup_cost"]

    init_inventory = {p: disagg_detail[p]["initial_inventory"] for p in products}
    inventory = init_inventory.copy()
    warnings: List[str] = []
    rows: List[Dict] = []

    setup_switches = 0
    prev_last_product = None

    absentee_cfg = inputs["mps"]["q3_absenteeism"]
    regular_per_period, overtime_per_period = _period_labor_hours(best_plan, absentee_cfg)
    period_prod = _build_period_production(
        inputs,
        best_plan,
        disagg_detail,
        period_demand,
        regular_per_period,
        overtime_per_period,
    )

    for period_idx in range(9):
        quarter_idx = period_idx // 3
        reg_hours = regular_per_period[period_idx]
        ot_hours = overtime_per_period[period_idx]

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
