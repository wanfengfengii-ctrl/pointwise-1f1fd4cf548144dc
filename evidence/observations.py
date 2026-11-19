from dataclasses import dataclass

from evidence.terminals import (
    EndpointRef,
    MAX_LOCAL_CONTACTS,
    PublicCatalog,
    require_identifier,
    resolve_endpoint,
)

MAX_OBSERVATIONS = 24


@dataclass(frozen=True)
class Observation:
    record_id: str
    left: EndpointRef
    right: EndpointRef
    relation: str
    kind: str
    weight: int | None = None


@dataclass(frozen=True)
class EvidenceChange:
    operation: str
    record_id: str
    observation: Observation | None = None


def _validate_observation(catalog: PublicCatalog, station_id: str,
                          row: Observation) -> None:
    resolve_endpoint(catalog, station_id, row.left)
    resolve_endpoint(catalog, station_id, row.right)
    if row.relation not in ('same', 'different'):
        raise ValueError('relation must be same or different')
    if row.kind == 'hard' and row.weight is None:
        return
    if row.kind == 'soft' and type(row.weight) is int and row.weight > 0:
        return
    raise ValueError('hard evidence has no weight and soft evidence needs a positive integer weight')


def validate_changes(catalog: PublicCatalog, station_id: str,
                     changes: list[EvidenceChange] | tuple[EvidenceChange, ...]) -> None:
    if not isinstance(changes, (list, tuple)) or not changes:
        raise ValueError('a nonempty evidence batch is required')
    seen = set()
    for change in changes:
        if not isinstance(change, EvidenceChange):
            raise ValueError('an evidence change is required')
        record_id = require_identifier(change.record_id, 'record identifier')
        if record_id in seen:
            raise ValueError(f'multiple changes for record {record_id}')
        seen.add(record_id)
        if change.operation == 'remove' and change.observation is None:
            continue
        if change.operation not in ('add', 'replace'):
            raise ValueError('invalid evidence operation')
        row = change.observation
        if not isinstance(row, Observation) or row.record_id != record_id:
            raise ValueError('change and observation must have the same record identifier')
        _validate_observation(catalog, station_id, row)


def apply_changes(base: tuple[Observation, ...],
                  changes: list[EvidenceChange] | tuple[EvidenceChange, ...]) -> tuple[Observation, ...]:
    """Apply a structurally validated batch to a copy of the base snapshot."""
    rows = {row.record_id: row for row in base}
    for change in changes:
        record_id = change.record_id
        exists = record_id in rows
        if change.operation == 'add' and exists:
            raise ValueError(f'record already exists: {record_id}')
        if change.operation in ('replace', 'remove') and not exists:
            raise ValueError(f'unknown correction target: {record_id}')
        if change.operation == 'remove':
            del rows[record_id]
        else:
            rows[record_id] = change.observation
    if len(rows) > MAX_OBSERVATIONS:
        raise ValueError('a station revision supports at most 24 observations')
    local_contacts = {
        endpoint.name
        for row in rows.values()
        for endpoint in (row.left, row.right)
        if endpoint.scope == 'local'
    }
    if len(local_contacts) > MAX_LOCAL_CONTACTS:
        raise ValueError('a station revision supports at most six local contacts')
    return tuple(rows[key] for key in sorted(rows))
