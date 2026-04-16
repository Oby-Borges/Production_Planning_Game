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
    feasibility_summary: Dict[str, bool]

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
            "feasibility_summary": self.feasibility_summary,
        }


def _evaluate_candidate_plan(
    strategy_name: str,
    demands: List[int],
    regular_hours: List[int],
    overtime_hours: List[int],
    initial_inventory: int,
    cfg: Dict,
) -> AggregatePlan:
    """Evaluate one aggregate candidate using the app's packet-based rules."""
    avg_labor = cfg["average_labor_hours_per_unit"]
    max_ot_ratio = cfg["max_overtime_ratio_per_period"]

    inventory = initial_inventory
    ending_inventory: List[int] = []
    production: List[int] = []
    regular_units: List[int] = []
    overtime_units: List[int] = []
    warnings: List[str] = []

    inventory_ok = True
    overtime_ok = True
    divisibility_ok = True
    nonnegative_ok = True

    for q_idx, demand in enumerate(demands):
        reg_hours = regular_hours[q_idx]
        ot_hours = overtime_hours[q_idx]

        if reg_hours < 0 or ot_hours < 0:
            nonnegative_ok = False
            warnings.append(f"Quarter {q_idx + 1}: labor hours must be nonnegative.")

        if reg_hours % avg_labor != 0 or (reg_hours + ot_hours) % avg_labor != 0:
            divisibility_ok = False
            warnings.append(f"Quarter {q_idx + 1}: divisibility rule violated for labor hours.")

        ot_cap_hours = int(reg_hours * max_ot_ratio)
        if ot_hours > ot_cap_hours:
            overtime_ok = False
            warnings.append(f"Quarter {q_idx + 1}: overtime cap exceeded.")

        reg_units = reg_hours // avg_labor
        ot_units = ot_hours // avg_labor
        produced = reg_units + ot_units

        inventory = inventory + produced - demand
        if inventory < 0:
            inventory_ok = False
            warnings.append(f"Quarter {q_idx + 1}: negative inventory would occur.")
            inventory = 0

        ending_inventory.append(inventory)
        production.append(produced)
        regular_units.append(reg_units)
        overtime_units.append(ot_units)

    pseudo = {
        "regular_hours": regular_hours,
        "overtime_hours": overtime_hours,
        "ending_inventory": ending_inventory,
        "initial_inventory": initial_inventory,
        "production": production,
    }
    cost_breakdown = aggregate_cost_breakdown(pseudo, cfg)
    feasibility_summary = {
        "aggregate_feasible": inventory_ok and overtime_ok and divisibility_ok and nonnegative_ok,
        "inventory_constraints_satisfied": inventory_ok,
        "overtime_constraints_satisfied": overtime_ok,
        "divisibility_rules_satisfied": divisibility_ok,
        "nonnegativity_satisfied": nonnegative_ok,
    }

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
        feasible=feasibility_summary["aggregate_feasible"],
        warnings=warnings,
        cost_breakdown=cost_breakdown,
        feasibility_summary=feasibility_summary,
    )


def _best_initial_inventory_for_plan(
    strategy_name: str,
    demands: List[int],
    regular_hours: List[int],
    cfg: Dict,
) -> AggregatePlan:
    """Try a bounded initial inventory candidate set and keep lowest-cost feasible option."""
    best: Optional[AggregatePlan] = None
    raw_candidates = [0, 5, 10, 15, 20]
    max_initial = cfg["max_initial_finished_goods"]
    init_candidates = sorted({min(c, max_initial) for c in raw_candidates if c <= max_initial})
    if max_initial not in init_candidates:
        init_candidates.append(max_initial)

    for init_inv in init_candidates:
        plan = _evaluate_candidate_plan(
            strategy_name,
            demands,
            regular_hours,
            [0, 0, 0],
            init_inv,
            cfg,
        )
        if not plan.feasible:
            continue
        if best is None or plan.cost_breakdown["total_cost"] < best.cost_breakdown["total_cost"]:
            best = plan

    if best is None:
        return _evaluate_candidate_plan(
            strategy_name,
            demands,
            regular_hours,
            [0, 0, 0],
            cfg["max_initial_finished_goods"],
            cfg,
        )
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
        best = _best_initial_inventory_for_plan("level", demands, [max_candidate] * 3, cfg)
    return best


def build_hybrid_strategy(inputs: Dict, chase: AggregatePlan, level: AggregatePlan) -> AggregatePlan:
    """Search for the lowest-cost feasible hybrid plan over bounded candidate ranges."""
    cfg = inputs["aggregate"]
    demands = [cfg["forecast_quarterly_demand"][f"Q{i}"] for i in range(1, 4)]
    reg_multiple = cfg["regular_hours_must_be_divisible_by"]
    max_initial = cfg["max_initial_finished_goods"]
    material_cost = cfg["average_material_cost_per_unit"]
    reg_rate = cfg["regular_labor_cost_per_hour"]
    ot_rate = cfg["overtime_labor_cost_per_hour"]
    train_rate = cfg["training_cost_per_hour_change"]
    reloc_rate = cfg["relocation_cost_per_hour_change"]
    hold_rate = cfg["holding_cost_per_unit_quarter"]

    # Bounded candidate ranges around the observed demand needs. We search all
    # multiples of 3 in these ranges and all feasible overtime values implied by
    # the packet's 50% overtime cap.
    regular_ranges = [
        range(300, 541, reg_multiple),
        range(480, 991, reg_multiple),
        range(480, 811, reg_multiple),
    ]
    remaining_demands = [sum(demands[idx + 1 :]) for idx in range(3)]

    states: Dict[tuple[int, int], Dict] = {}
    for init_inv in range(0, max_initial + 1):
        states[(cfg["initial_regular_hours_q1"], init_inv)] = {
            "cost": init_inv * cfg["initial_inventory_acquisition_cost_per_unit"],
            "starting_inventory": init_inv,
            "regular_hours": [],
            "overtime_hours": [],
            "production": [],
            "ending_inventory": [],
        }

    for q_idx, demand in enumerate(demands):
        next_states: Dict[tuple[int, int], Dict] = {}
        for (prev_regular, inventory_in), state in states.items():
            for reg_hours in regular_ranges[q_idx]:
                ot_cap = reg_hours // 2
                min_ot = max(0, 3 * max(0, demand - inventory_in) - reg_hours)
                min_ot = round_up_to_multiple(min_ot, reg_multiple)

                max_useful_inventory = remaining_demands[q_idx]
                max_ot_from_inventory = max(0, 3 * (demand + max_useful_inventory - inventory_in) - reg_hours)
                max_ot = min(ot_cap, max_ot_from_inventory)
                max_ot -= max_ot % reg_multiple

                if min_ot > max_ot:
                    continue

                for ot_hours in range(min_ot, max_ot + 1, reg_multiple):
                    produced = (reg_hours + ot_hours) // 3
                    inventory_out = inventory_in + produced - demand
                    if inventory_out < 0:
                        continue

                    delta = reg_hours - prev_regular
                    training_cost = max(0, delta) * train_rate
                    relocation_cost = max(0, -delta) * reloc_rate
                    total_cost = (
                        state["cost"]
                        + (produced * material_cost)
                        + (reg_hours * reg_rate)
                        + (ot_hours * ot_rate)
                        + training_cost
                        + relocation_cost
                        + (inventory_out * hold_rate)
                    )

                    key = (reg_hours, inventory_out)
                    existing = next_states.get(key)
                    if existing is None or total_cost < existing["cost"]:
                        next_states[key] = {
                            "cost": total_cost,
                            "starting_inventory": state["starting_inventory"],
                            "regular_hours": state["regular_hours"] + [reg_hours],
                            "overtime_hours": state["overtime_hours"] + [ot_hours],
                            "production": state["production"] + [produced],
                            "ending_inventory": state["ending_inventory"] + [inventory_out],
                        }
        states = next_states

    best: Optional[AggregatePlan] = None
    for (_, _), state in states.items():
        candidate = _evaluate_candidate_plan(
            "hybrid",
            demands,
            state["regular_hours"],
            state["overtime_hours"],
            state["starting_inventory"],
            cfg,
        )
        if not candidate.feasible:
            continue
        if best is None or candidate.cost_breakdown["total_cost"] < best.cost_breakdown["total_cost"]:
            best = candidate

    if best is None:
        return _evaluate_candidate_plan(
            "hybrid",
            demands,
            [chase.regular_hours[0], level.regular_hours[1], level.regular_hours[2]],
            [0, 0, 0],
            0,
            cfg,
        )
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
        return min(plans.values(), key=lambda p: p.cost_breakdown["total_cost"])
    return min(feasible_plans, key=lambda p: p.cost_breakdown["total_cost"])
