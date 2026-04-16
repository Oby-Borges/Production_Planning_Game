"""Aggregate planning strategy generation (chase, level, hybrid)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional

from costing import aggregate_cost_breakdown
from utils import round_up_to_multiple


@dataclass
class AggregatePlan:
    """Container for one complete aggregate strategy."""

    strategy: str
    initial_inventory: int
    production: List[int]
    demand: List[int]
    ending_inventory: List[int]
    regular_hours: List[int]
    overtime_hours: List[int]
    overtime_units: List[int]
    regular_units: List[int]
    feasible: bool
    warnings: List[str]
    cost_breakdown: Dict[str, float]

    def to_dict(self) -> Dict:
        return {
            "strategy": self.strategy,
            "initial_inventory": self.initial_inventory,
            "production": self.production,
            "demand": self.demand,
            "ending_inventory": self.ending_inventory,
            "regular_hours": self.regular_hours,
            "overtime_hours": self.overtime_hours,
            "overtime_units": self.overtime_units,
            "regular_units": self.regular_units,
            "feasible": self.feasible,
            "warnings": self.warnings,
            "cost_breakdown": self.cost_breakdown,
        }


def _simulate_plan(
    strategy_name: str,
    demands: List[int],
    regular_hours: List[int],
    initial_inventory: int,
    cfg: Dict,
) -> AggregatePlan:
    """Simulate quarter-level inventory flow under proposed regular hours."""
    avg_labor = cfg["average_labor_hours_per_unit"]
    max_ot_ratio = cfg["max_overtime_ratio_per_period"]
    periods_per_q = 3

    inventory = initial_inventory
    ending_inventory: List[int] = []
    production: List[int] = []
    regular_units: List[int] = []
    overtime_units: List[int] = []
    overtime_hours: List[int] = []
    warnings: List[str] = []
    feasible = True

    for q, demand in enumerate(demands):
        reg_hours = regular_hours[q]
        reg_units = reg_hours // avg_labor

        # Overtime cap is per period, but quarter cap equals 3 * (0.5 * reg_per_period) = 0.5 * quarter regular.
        ot_cap_hours = int(reg_hours * max_ot_ratio)
        deficit_units = max(0, demand - (inventory + reg_units))
        needed_ot_hours = deficit_units * avg_labor
        ot_hours = min(ot_cap_hours, needed_ot_hours)
        ot_units = ot_hours // avg_labor

        produced = reg_units + ot_units
        inventory = inventory + produced - demand

        if inventory < 0:
            feasible = False
            warnings.append(f"Quarter {q+1}: demand shortfall of {abs(inventory)} units")
            inventory = 0

        if needed_ot_hours > ot_cap_hours:
            feasible = False
            warnings.append(
                f"Quarter {q+1}: overtime cap exceeded by {needed_ot_hours - ot_cap_hours} labor-hours"
            )

        ending_inventory.append(inventory)
        production.append(produced)
        regular_units.append(reg_units)
        overtime_units.append(ot_units)
        overtime_hours.append(ot_hours)

    pseudo = {
        "regular_hours": regular_hours,
        "overtime_hours": overtime_hours,
        "ending_inventory": ending_inventory,
        "initial_inventory": initial_inventory,
    }
    cost_breakdown = aggregate_cost_breakdown(pseudo, cfg)

    return AggregatePlan(
        strategy=strategy_name,
        initial_inventory=initial_inventory,
        production=production,
        demand=demands,
        ending_inventory=ending_inventory,
        regular_hours=regular_hours,
        overtime_hours=overtime_hours,
        overtime_units=overtime_units,
        regular_units=regular_units,
        feasible=feasible,
        warnings=warnings,
        cost_breakdown=cost_breakdown,
    )


def _best_initial_inventory_for_plan(strategy_name: str, demands: List[int], regular_hours: List[int], cfg: Dict) -> AggregatePlan:
    """Try a bounded initial inventory candidate set and keep lowest-cost feasible option."""
    best: Optional[AggregatePlan] = None

    # Practical speed-up:
    # The original exhaustive search over every inventory value was too expensive
    # when nested inside the strategy search loops. A bounded candidate list keeps
    # the model fast and explainable for a class planning exercise.
    #
    # Instead of testing every inventory value (0..max) for every candidate plan,
    # we use a bounded list. This keeps runtime predictable while still sampling
    # low/medium/high initial inventory levels suitable for a class planning model.
    raw_candidates = [0, 5, 10, 15, 20]
    max_initial = cfg["max_initial_finished_goods"]
    init_candidates = sorted({min(c, max_initial) for c in raw_candidates if c <= max_initial})
    if max_initial not in init_candidates:
        init_candidates.append(max_initial)

    for init_inv in init_candidates:
        plan = _simulate_plan(strategy_name, demands, regular_hours, init_inv, cfg)
        if not plan.feasible:
            continue
        if best is None or plan.cost_breakdown["total_cost"] < best.cost_breakdown["total_cost"]:
            best = plan

    # If nothing feasible under constraints, return lowest-cost plan even if infeasible to show warnings.
    if best is None:
        fallback = _simulate_plan(strategy_name, demands, regular_hours, cfg["max_initial_finished_goods"], cfg)
        return fallback
    return best


def build_chase_strategy(inputs: Dict) -> AggregatePlan:
    """Build chase plan by setting regular hours near required quarter labor."""
    cfg = inputs["aggregate"]
    demands = [cfg["forecast_quarterly_demand"][f"Q{i}"] for i in range(1, 4)]

    reg_multiple = cfg["regular_hours_must_be_divisible_by"]
    avg_labor = cfg["average_labor_hours_per_unit"]

    regular_hours = []
    for demand in demands:
        req_hours = demand * avg_labor
        regular_hours.append(round_up_to_multiple(req_hours, reg_multiple))

    # Respect "initial regular labor available in Q1 is 300" as baseline; chase can still increase/decrease.
    regular_hours[0] = max(regular_hours[0], cfg["initial_regular_hours_q1"])
    regular_hours[0] = round_up_to_multiple(regular_hours[0], reg_multiple)

    return _best_initial_inventory_for_plan("chase", demands, regular_hours, cfg)


def build_level_strategy(inputs: Dict) -> AggregatePlan:
    """Enumerate constant regular labor and keep minimum-cost feasible plan."""
    cfg = inputs["aggregate"]
    demands = [cfg["forecast_quarterly_demand"][f"Q{i}"] for i in range(1, 4)]

    reg_multiple = cfg["regular_hours_must_be_divisible_by"]
    min_candidate = cfg["initial_regular_hours_q1"]
    max_candidate = 1500

    best: Optional[AggregatePlan] = None
    for reg in range(min_candidate, max_candidate + 1, reg_multiple):
        candidate = _best_initial_inventory_for_plan("level", demands, [reg, reg, reg], cfg)
        if not candidate.feasible:
            continue
        if best is None or candidate.cost_breakdown["total_cost"] < best.cost_breakdown["total_cost"]:
            best = candidate

    if best is None:
        # Safety fallback if constraints impossible.
        best = _best_initial_inventory_for_plan("level", demands, [max_candidate] * 3, cfg)
    return best


def build_hybrid_strategy(inputs: Dict, chase: AggregatePlan, level: AggregatePlan) -> AggregatePlan:
    """Search moderate quarter-by-quarter regular hours for lower-cost feasible compromise."""
    cfg = inputs["aggregate"]
    demands = [cfg["forecast_quarterly_demand"][f"Q{i}"] for i in range(1, 4)]
    reg_multiple = cfg["regular_hours_must_be_divisible_by"]

    baseline = [cfg["initial_regular_hours_q1"], cfg["initial_regular_hours_q1"], cfg["initial_regular_hours_q1"]]

    # Practical speed-up:
    # The original broad/fine-grained enumeration produced a very large search
    # space and made runtime too slow. We now use a bounded candidate set that
    # still represents low/mid/high regular-hour plans and preserves the hybrid
    # intent without excessive brute-force computation.
    base_candidates = [300, 330, 360, 390, 420]
    hour_candidates = [c for c in base_candidates if c % reg_multiple == 0]
    if not hour_candidates:
        hour_candidates = [cfg["initial_regular_hours_q1"]]

    best: Optional[AggregatePlan] = None
    for q1 in hour_candidates:
        for q2 in hour_candidates:
            for q3 in hour_candidates:
                # Keep "hybrid" moderate by restricting abrupt quarter-to-quarter changes.
                if abs(q2 - q1) > 450 or abs(q3 - q2) > 450:
                    continue
                if [q1, q2, q3] == chase.regular_hours or [q1, q2, q3] == level.regular_hours:
                    continue
                candidate = _best_initial_inventory_for_plan("hybrid", demands, [q1, q2, q3], cfg)
                if not candidate.feasible:
                    continue
                if best is None or candidate.cost_breakdown["total_cost"] < best.cost_breakdown["total_cost"]:
                    best = candidate

    if best is None:
        best = _best_initial_inventory_for_plan("hybrid", demands, baseline, cfg)
    return best


def build_all_strategies(inputs: Dict) -> Dict[str, AggregatePlan]:
    """Create chase, level, and hybrid plans."""
    chase = build_chase_strategy(inputs)
    level = build_level_strategy(inputs)
    hybrid = build_hybrid_strategy(inputs, chase, level)
    return {"chase": chase, "level": level, "hybrid": hybrid}


def choose_best_strategy(plans: Dict[str, AggregatePlan]) -> AggregatePlan:
    """Select feasible strategy with lowest total cost."""
    feasible_plans = [p for p in plans.values() if p.feasible]
    if not feasible_plans:
        # If all infeasible, still pick minimum cost for transparency.
        return min(plans.values(), key=lambda p: p.cost_breakdown["total_cost"])
    return min(feasible_plans, key=lambda p: p.cost_breakdown["total_cost"])
