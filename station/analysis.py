from dataclasses import dataclass
from itertools import product

from evidence.revision_store import RevisionSnapshot
from evidence.terminals import public_state_index
from station.assignment_cost import compile_observations, score_assignment


@dataclass(frozen=True)
class ConditionedAnalysis:
    terminals: tuple[str, ...]
    costs: tuple[int | None, ...]

    def cost_for(self, public_state: tuple[int, ...] | list[int]) -> int | None:
        if not isinstance(public_state, (tuple, list)) or len(public_state) != len(self.terminals):
            raise ValueError('a complete public state is required')
        return self.costs[public_state_index(public_state)]


def analyze_revision(snapshot: RevisionSnapshot) -> ConditionedAnalysis:
    terminals = snapshot.catalog.terminals
    compiled, local_count = compile_observations(snapshot.catalog, snapshot.station_id, snapshot.observations)
    local_states = tuple(product((0, 1), repeat=local_count))
    costs = []
    for public_state in product((0, 1), repeat=len(terminals)):
        best = None
        for local_state in local_states:
            cost = score_assignment(compiled, public_state + local_state)
            if cost is not None and (best is None or cost < best):
                best = cost
        costs.append(best)
    return ConditionedAnalysis(terminals, tuple(costs))
