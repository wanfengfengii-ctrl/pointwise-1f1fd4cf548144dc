from dataclasses import dataclass
from itertools import product

from evidence.revision_store import RevisionSnapshot
from evidence.waiver_policy import WaiverPolicy
from station.assignment_cost import compile_observations, score_waiver_assignment

WAIVER_CONDITIONS_ENCODING = 'waiver-lex-costs'


@dataclass(frozen=True)
class WaiverConditionTable:
    """One approved combination's complete public-state cost table."""
    combination: tuple[str, ...]
    costs: tuple[int | None, ...]


@dataclass(frozen=True)
class WaiverAnalysis:
    terminals: tuple[str, ...]
    policy: WaiverPolicy
    tables: tuple[WaiverConditionTable, ...]

    def costs_for(self, combination: tuple[str, ...]) -> tuple[int | None, ...]:
        for table in self.tables:
            if table.combination == combination:
                return table.costs
        raise KeyError(combination)


def analyze_waiver_revision(snapshot: RevisionSnapshot, policy: WaiverPolicy) -> WaiverAnalysis:
    """Recompute the minimum station cost for every approved combination and state.

    Hard evidence keeps its feasibility semantics in every combination. Soft
    evidence inside a selected group contributes nothing when violated; all
    other violated soft evidence still adds its weight. The station may choose
    any private-contact interpretation independently per public state.
    """
    terminals = snapshot.catalog.terminals
    compiled, local_count = compile_observations(snapshot.catalog, snapshot.station_id, snapshot.observations)
    local_states = tuple(product((0, 1), repeat=local_count))
    tables = []
    for combination in policy.approved_combinations:
        waived = frozenset(combination)
        costs = []
        for public_state in product((0, 1), repeat=len(terminals)):
            best = None
            for local_state in local_states:
                cost = score_waiver_assignment(compiled, public_state + local_state, waived)
                if cost is not None and (best is None or cost < best):
                    best = cost
            costs.append(best)
        tables.append(WaiverConditionTable(combination, tuple(costs)))
    return WaiverAnalysis(terminals, policy, tuple(tables))


def feasible_mask(analysis: WaiverAnalysis) -> tuple[bool, ...]:
    """Hard feasibility must be identical across every approved combination."""
    masks = [tuple(cost is not None for cost in table.costs) for table in analysis.tables]
    reference = masks[0]
    for mask in masks[1:]:
        if mask != reference:
            raise ValueError('hard feasibility must not depend on the waiver combination')
    return reference
