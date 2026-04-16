"""Disaggregate quarter-level aggregate plan into product-level plan."""

from __future__ import annotations

from typing import Dict, List, Tuple

import pandas as pd


def _allocate_integer(total: int, weights: List[float]) -> List[int]:
    """Allocate integer total by weights while preserving sum exactly."""
    raw = [total * w for w in weights]
    base = [int(x) for x in raw]
    remainder = total - sum(base)
    frac_order = sorted(range(len(raw)), key=lambda i: raw[i] - base[i], reverse=True)
    for i in range(remainder):
        base[frac_order[i % len(base)]] += 1
    return base


def build_disaggregate_plan(inputs: Dict, aggregate_plan: Dict) -> Tuple[pd.DataFrame, Dict[str, Dict[str, int]]]:
    """Allocate initial inventory and production by product demand mix."""
    products = inputs["products"]
    names = list(products.keys())
    quarters = ["Q1", "Q2", "Q3"]

    quarter_mix: Dict[str, List[float]] = {}
    for q in quarters:
        q_total = sum(products[p]["quarterly_demand"][q] for p in names)
        quarter_mix[q] = [products[p]["quarterly_demand"][q] / q_total for p in names]

    overall_demands = [sum(products[p]["quarterly_demand"][q] for q in quarters) for p in names]
    overall_weights = [d / sum(overall_demands) for d in overall_demands]
    init_alloc = _allocate_integer(aggregate_plan["initial_inventory"], overall_weights)

    production_alloc: Dict[str, List[int]] = {p: [] for p in names}
    for q_idx, q in enumerate(quarters):
        q_prod = aggregate_plan["production"][q_idx]
        shares = quarter_mix[q]
        alloc = _allocate_integer(q_prod, shares)
        for p_idx, p in enumerate(names):
            production_alloc[p].append(alloc[p_idx])

    rows = []
    for idx, p in enumerate(names):
        q_values = production_alloc[p]
        row = {
            "product": p,
            "initial_inventory": init_alloc[idx],
            "Q1": q_values[0],
            "Q2": q_values[1],
            "Q3": q_values[2],
        }
        row["total_production"] = row["Q1"] + row["Q2"] + row["Q3"]
        row["total_demand"] = sum(products[p]["quarterly_demand"][q] for q in quarters)
        rows.append(row)

    df = pd.DataFrame(rows)

    detail = {
        p: {
            "initial_inventory": init_alloc[i],
            "Q1": production_alloc[p][0],
            "Q2": production_alloc[p][1],
            "Q3": production_alloc[p][2],
        }
        for i, p in enumerate(names)
    }

    return df, detail
