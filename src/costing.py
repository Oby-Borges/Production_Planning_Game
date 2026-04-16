"""Cost calculation helpers for aggregate planning and MRP."""

from __future__ import annotations

from typing import Dict, List


def aggregate_cost_breakdown(plan: Dict, aggregate_cfg: Dict) -> Dict[str, float]:
    """Compute cost breakdown for one aggregate plan dictionary."""
    reg_rate = aggregate_cfg["regular_labor_cost_per_hour"]
    ot_rate = aggregate_cfg["overtime_labor_cost_per_hour"]
    train_rate = aggregate_cfg["training_cost_per_hour_change"]
    reloc_rate = aggregate_cfg["relocation_cost_per_hour_change"]
    hold_rate = aggregate_cfg["holding_cost_per_unit_quarter"]
    init_inv_rate = aggregate_cfg["initial_inventory_acquisition_cost_per_unit"]

    regular_cost = sum(plan["regular_hours"]) * reg_rate
    overtime_cost = sum(plan["overtime_hours"]) * ot_rate

    training_cost = 0.0
    relocation_cost = 0.0
    prev = aggregate_cfg["initial_regular_hours_q1"]
    for q_hours in plan["regular_hours"]:
        delta = q_hours - prev
        if delta > 0:
            training_cost += delta * train_rate
        elif delta < 0:
            relocation_cost += abs(delta) * reloc_rate
        prev = q_hours

    holding_cost = sum(plan["ending_inventory"]) * hold_rate
    initial_inventory_cost = plan["initial_inventory"] * init_inv_rate

    total = (
        regular_cost
        + overtime_cost
        + training_cost
        + relocation_cost
        + holding_cost
        + initial_inventory_cost
    )

    return {
        "regular_labor_cost": regular_cost,
        "overtime_labor_cost": overtime_cost,
        "training_cost": training_cost,
        "relocation_cost": relocation_cost,
        "aggregate_inventory_holding_cost": holding_cost,
        "initial_inventory_acquisition_cost": initial_inventory_cost,
        "total_cost": total,
    }


def setup_cost_from_switches(num_switches: int, setup_cost_per_switch: float) -> float:
    """Convert counted setup switches to cost."""
    return num_switches * setup_cost_per_switch


def mrp_total_cost(rows: List[Dict], purchase_cost: float, order_cost: float, hold_cost: float) -> Dict[str, float]:
    """Compute purchase + ordering + holding for one fruit MRP result."""
    ordered_qty = sum(r["Planned Order Delivery"] for r in rows)
    num_orders = sum(1 for r in rows if r["Planned Order Delivery"] > 0)
    ending_inv_total = sum(r["Projected Ending Inventory"] for r in rows)

    purchase = ordered_qty * purchase_cost
    ordering = num_orders * order_cost
    holding = ending_inv_total * hold_cost

    return {
        "purchase_cost": purchase,
        "ordering_cost": ordering,
        "holding_cost": holding,
        "total_cost": purchase + ordering + holding,
    }
