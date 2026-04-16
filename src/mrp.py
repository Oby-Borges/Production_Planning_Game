"""MRP generation with L4L and Silver-Meal lot sizing."""

from __future__ import annotations

import math
from typing import Dict, List, Tuple

import pandas as pd

from costing import mrp_total_cost


def build_gross_requirements(inputs: Dict, mps_period_production: Dict[str, List[int]]) -> Dict[str, List[int]]:
    """Translate smoothie MPS into fruit gross requirements by period."""
    bom = inputs["bom"]
    fruits = inputs["fruits"]
    gross = {fruit: [0] * 9 for fruit in fruits}

    for product, prod_list in mps_period_production.items():
        usage = bom[product]
        for t, qty in enumerate(prod_list):
            for fruit, units in usage.items():
                gross[fruit][t] += qty * units

    return gross


def _silver_meal_schedule(net_requirements: List[int], order_cost: float, holding_cost: float) -> List[int]:
    """Return planned good-unit deliveries with Silver-Meal heuristic."""
    n = len(net_requirements)
    deliveries = [0] * n
    t = 0
    while t < n:
        if net_requirements[t] <= 0:
            t += 1
            continue

        k = 1
        best_avg = float("inf")
        best_k = 1
        while t + k - 1 < n:
            holding = 0.0
            for j in range(k):
                holding += j * holding_cost * net_requirements[t + j]
            avg = (order_cost + holding) / k
            if avg <= best_avg + 1e-9:
                best_avg = avg
                best_k = k
                k += 1
            else:
                break

        cover_qty = sum(net_requirements[t : t + best_k])
        deliveries[t] = cover_qty
        t += best_k

    return deliveries


def _l4l_schedule(net_requirements: List[int]) -> List[int]:
    """L4L means order exactly what is required each period."""
    return [max(0, n) for n in net_requirements]


def _run_mrp_with_deliveries(
    gross_reqs: List[int],
    lead_time: int,
    quality: float,
    initial_inventory: int,
    deliveries_good_units: List[int],
) -> Dict:
    """Simulate MRP table using planned good-unit deliveries as target."""
    n = len(gross_reqs)
    rows: List[Dict] = []
    projected = initial_inventory
    releases = [0] * n
    warnings: List[str] = []
    feasible = True

    for t in range(n):
        requested_good_delivery = deliveries_good_units[t]
        if t < lead_time and requested_good_delivery > 0:
            feasible = False
            warnings.append(
                f"Period {t+1}: lead time {lead_time} prevents delivery in this period; more initial inventory is required."
            )

        order_delivery = 0
        usable_delivery = 0
        if t >= lead_time and requested_good_delivery > 0:
            order_delivery = math.ceil(requested_good_delivery / quality)
            usable_delivery = math.floor(order_delivery * quality)
            rel_idx = t - lead_time
            releases[rel_idx] += order_delivery

        projected_start = projected
        projected = projected + usable_delivery - gross_reqs[t]
        net_req = max(0, gross_reqs[t] - projected_start)
        if projected < 0:
            # The packet's lead-time rules do not allow same-period rescue orders.
            # Preserve the shortage as an infeasibility signal instead of masking it.
            feasible = False
            warnings.append(
                f"Period {t+1}: shortage of {abs(projected)} units after respecting lead-time constraints."
            )
            projected = 0

        rows.append(
            {
                "Period": t + 1,
                "Gross Requirements": gross_reqs[t],
                "Scheduled Receipts": 0,
                "Projected On-hand Inventory": projected_start,
                "Net Requirements": net_req,
                "Time-Phased Requirements": gross_reqs[t],
                "Planned Order Release": 0,  # filled after loop using lead-time shift
                "Planned Order Delivery": order_delivery,
                "Projected Ending Inventory": projected,
            }
        )

    for t in range(n):
        rows[t]["Planned Order Release"] = releases[t]

    return {"rows": rows, "warnings": warnings, "feasible": feasible}


def evaluate_item_mrp(
    fruit_name: str,
    item_cfg: Dict,
    gross_requirements: List[int],
    order_cost: float,
    initial_inventory: int,
) -> Dict:
    """Evaluate L4L and Silver-Meal methods for one fruit and return both."""
    lead_time = item_cfg["lead_time"]
    quality = item_cfg["quality"]
    hold = item_cfg["holding_cost"]
    purchase = item_cfg["purchase_cost"]

    # Estimate net requirements ignoring lot-size interactions for heuristic schedules.
    projected = initial_inventory
    net = []
    for g in gross_requirements:
        req = max(0, g - projected)
        net.append(req)
        projected = max(0, projected - g)

    l4l_good = _l4l_schedule(net)
    sm_good = _silver_meal_schedule(net, order_cost, hold)

    l4l_result = _run_mrp_with_deliveries(gross_requirements, lead_time, quality, initial_inventory, l4l_good)
    sm_result = _run_mrp_with_deliveries(gross_requirements, lead_time, quality, initial_inventory, sm_good)

    l4l_cost = mrp_total_cost(l4l_result["rows"], purchase, order_cost, hold, initial_inventory=initial_inventory)
    sm_cost = mrp_total_cost(sm_result["rows"], purchase, order_cost, hold, initial_inventory=initial_inventory)

    feasible_methods = []
    if l4l_result["feasible"]:
        feasible_methods.append(("L4L", l4l_cost["total_cost"]))
    if sm_result["feasible"]:
        feasible_methods.append(("Silver-Meal", sm_cost["total_cost"]))

    if feasible_methods:
        chosen = min(feasible_methods, key=lambda item: item[1])[0]
        feasible = True
    else:
        chosen = "L4L" if l4l_cost["total_cost"] <= sm_cost["total_cost"] else "Silver-Meal"
        feasible = False

    return {
        "fruit": fruit_name,
        "l4l": {"rows": l4l_result["rows"], "cost": l4l_cost, "feasible": l4l_result["feasible"], "warnings": l4l_result["warnings"]},
        "silver_meal": {
            "rows": sm_result["rows"],
            "cost": sm_cost,
            "feasible": sm_result["feasible"],
            "warnings": sm_result["warnings"],
        },
        "chosen": chosen,
        "initial_inventory": initial_inventory,
        "feasible": feasible,
    }


def choose_initial_fruit_inventory(item_cfg: Dict, gross_requirements: List[int], max_initial: int, order_cost: float) -> int:
    """Practical search over 0..max initial inventory for lower total item cost (L4L baseline)."""
    best_inv = 0
    best_cost = float("inf")
    for init_inv in range(max_initial + 1):
        result = evaluate_item_mrp("tmp", item_cfg, gross_requirements, order_cost, init_inv)
        feasible_costs = []
        if result["l4l"]["feasible"]:
            feasible_costs.append(result["l4l"]["cost"]["total_cost"])
        if result["silver_meal"]["feasible"]:
            feasible_costs.append(result["silver_meal"]["cost"]["total_cost"])

        if not feasible_costs:
            continue

        total = min(feasible_costs)
        if total < best_cost:
            best_cost = total
            best_inv = init_inv
    return best_inv


def build_all_mrp(inputs: Dict, mps_period_production: Dict[str, List[int]]) -> Tuple[Dict, pd.DataFrame]:
    """Build MRP results for all fruits and summarize chosen methods."""
    fruits = inputs["fruits"]
    order_cost = inputs["mrp"]["order_cost"]
    max_init = inputs["mrp"]["max_initial_fruit_inventory"]

    gross = build_gross_requirements(inputs, mps_period_production)
    results = {}
    summary_rows = []

    for fruit, cfg in fruits.items():
        init_inv = choose_initial_fruit_inventory(cfg, gross[fruit], max_init, order_cost)
        item_res = evaluate_item_mrp(fruit, cfg, gross[fruit], order_cost, init_inv)
        results[fruit] = item_res

        chosen_key = "l4l" if item_res["chosen"] == "L4L" else "silver_meal"
        chosen_cost = item_res[chosen_key]["cost"]["total_cost"]

        summary_rows.append(
            {
                "fruit": fruit,
                "initial_inventory": init_inv,
                "chosen_method": item_res["chosen"],
                "feasible": item_res["feasible"],
                "l4l_total_cost": item_res["l4l"]["cost"]["total_cost"],
                "silver_meal_total_cost": item_res["silver_meal"]["cost"]["total_cost"],
                "chosen_total_cost": chosen_cost,
            }
        )

    return results, pd.DataFrame(summary_rows)


def mrp_rows_to_df(rows: List[Dict]) -> pd.DataFrame:
    """Convert row list to dataframe with stable column order."""
    col_order = [
        "Period",
        "Gross Requirements",
        "Scheduled Receipts",
        "Projected On-hand Inventory",
        "Net Requirements",
        "Time-Phased Requirements",
        "Planned Order Release",
        "Planned Order Delivery",
        "Projected Ending Inventory",
    ]
    return pd.DataFrame(rows)[col_order]
