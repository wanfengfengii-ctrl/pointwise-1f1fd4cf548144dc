from dataclasses import dataclass
import json
import sqlite3

from evidence.terminals import require_identifier
from ledger_transaction import initialize_tables, write_transaction

_SCHEMA = (
    '''CREATE TABLE IF NOT EXISTS waiver_policies (
        trial_id TEXT PRIMARY KEY REFERENCES trials(trial_id),
        groups TEXT NOT NULL,
        approved_combinations TEXT NOT NULL
    )''',
)


@dataclass(frozen=True)
class WaiverPolicy:
    groups: tuple[str, ...]
    approved_combinations: tuple[tuple[str, ...], ...]

    def as_registration(self) -> dict:
        return {'groups': self.groups, 'approved_combinations': self.approved_combinations}


def initialize_waiver_policy_tables(db: sqlite3.Connection) -> None:
    initialize_tables(db, _SCHEMA)


def normalize_policy(groups: list[str] | tuple[str, ...],
                     approved_combinations: list | tuple) -> WaiverPolicy:
    """Validate and canonically order a waiver policy registration."""
    if not isinstance(groups, (list, tuple)):
        raise ValueError('waiver groups must be a list or tuple')
    normalized_groups = []
    seen_groups = set()
    for group in groups:
        name = require_identifier(group, 'fee group')
        if name in seen_groups:
            raise ValueError(f'duplicate waiver group: {name}')
        seen_groups.add(name)
        normalized_groups.append(name)
    if not isinstance(approved_combinations, (list, tuple)):
        raise ValueError('approved combinations must be a list or tuple')
    declared = frozenset(normalized_groups)
    combinations = []
    seen_combinations = set()
    for combination in approved_combinations:
        if not isinstance(combination, (list, tuple)):
            raise ValueError('each approved combination must be a list or tuple of group names')
        members = []
        seen_members = set()
        for group in combination:
            name = require_identifier(group, 'fee group')
            if name not in declared:
                raise ValueError(f'approved combination uses an undeclared group: {name}')
            if name in seen_members:
                raise ValueError(f'duplicate group inside an approved combination: {name}')
            seen_members.add(name)
            members.append(name)
        key = tuple(sorted(members))
        if key in seen_combinations:
            raise ValueError('duplicate approved combination')
        seen_combinations.add(key)
        combinations.append(key)
    if () not in seen_combinations:
        combinations.append(())
    ordered_groups = tuple(sorted(normalized_groups))
    ordered_combinations = tuple(sorted(combinations))
    return WaiverPolicy(ordered_groups, ordered_combinations)


def _encode_policy(policy: WaiverPolicy) -> tuple[str, str]:
    return (
        json.dumps(list(policy.groups), sort_keys=True, separators=(',', ':')),
        json.dumps([list(combination) for combination in policy.approved_combinations],
                   sort_keys=True, separators=(',', ':')),
    )


def _decode_policy(groups_text: str, combinations_text: str) -> WaiverPolicy:
    return WaiverPolicy(
        tuple(json.loads(groups_text)),
        tuple(tuple(combination) for combination in json.loads(combinations_text)),
    )


def load_waiver_policy(db: sqlite3.Connection, trial_id: str) -> WaiverPolicy | None:
    row = db.execute(
        'SELECT groups, approved_combinations FROM waiver_policies WHERE trial_id = ?',
        (trial_id,),
    ).fetchone()
    if row is None:
        return None
    return _decode_policy(row[0], row[1])


def register_waiver_policy(db: sqlite3.Connection, trial_id: str,
                           groups: list[str] | tuple[str, ...],
                           approved_combinations: list | tuple) -> dict:
    require_identifier(trial_id, 'trial identifier')
    policy = normalize_policy(groups, approved_combinations)
    groups_text, combinations_text = _encode_policy(policy)
    with write_transaction(db):
        from evidence.revision_store import load_trial_registration
        if load_trial_registration(db, trial_id) is None:
            raise KeyError(trial_id)
        existing = load_waiver_policy(db, trial_id)
        if existing is not None:
            if existing != policy:
                raise ValueError('waiver policy content is fixed after first registration')
            return existing.as_registration()
        db.execute(
            'INSERT INTO waiver_policies (trial_id, groups, approved_combinations) VALUES (?, ?, ?)',
            (trial_id, groups_text, combinations_text),
        )
    return policy.as_registration()
