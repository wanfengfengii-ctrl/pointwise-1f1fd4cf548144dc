from dataclasses import dataclass

from evidence.observations import Observation
from evidence.terminals import EndpointRef, PublicCatalog


@dataclass(frozen=True)
class CompiledObservation:
    left_index: int
    right_index: int
    equal: bool
    weight: int | None
    fee_group: str | None = None

    def satisfied(self, assignment: tuple[int, ...]) -> bool:
        return (assignment[self.left_index] == assignment[self.right_index]) == self.equal


def compile_observations(catalog: PublicCatalog, station_id: str,
                         observations: tuple[Observation, ...]) -> tuple[tuple[CompiledObservation, ...], int]:
    public = tuple(EndpointRef('public', name) for name in catalog.terminals)
    local = sorted({
        endpoint.name
        for row in observations
        for endpoint in (row.left, row.right)
        if endpoint.scope == 'local'
    })
    endpoints = public + tuple(EndpointRef('local', name, station_id) for name in local)
    index = {endpoint: position for position, endpoint in enumerate(endpoints)}
    compiled = tuple(
        CompiledObservation(index[row.left], index[row.right], row.relation == 'same',
                            row.weight, row.fee_group)
        for row in observations
    )
    return compiled, len(local)


def score_assignment(observations: tuple[CompiledObservation, ...],
                     assignment: tuple[int, ...]) -> int | None:
    if any(row.weight is None and not row.satisfied(assignment) for row in observations):
        return None
    return sum(
        row.weight for row in observations
        if row.weight is not None and not row.satisfied(assignment)
    )


def score_waiver_assignment(observations: tuple[CompiledObservation, ...],
                            assignment: tuple[int, ...],
                            waived_groups: frozenset[str]) -> int | None:
    """Score like ``score_assignment`` but drop violation fees inside waived groups."""
    if any(row.weight is None and not row.satisfied(assignment) for row in observations):
        return None
    return sum(
        row.weight for row in observations
        if row.weight is not None and not row.satisfied(assignment)
        and (row.fee_group is None or row.fee_group not in waived_groups)
    )
