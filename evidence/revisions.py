import sqlite3

from evidence.observations import EvidenceChange, apply_changes, validate_changes
from evidence.revision_store import RevisionSnapshot, insert_revision, load_revision
from evidence.terminals import require_identifier
from evidence.waiver_policy import load_waiver_policy


def read_revision(db: sqlite3.Connection, trial_id: str, station_id: str,
                  revision: int) -> RevisionSnapshot:
    require_identifier(trial_id, 'trial identifier')
    require_identifier(station_id, 'station identifier')
    if type(revision) is not int or not 0 <= revision < 2**63:
        raise ValueError('invalid revision number')
    snapshot = load_revision(db, trial_id, station_id, revision)
    if snapshot is None:
        raise KeyError((trial_id, station_id, revision))
    return snapshot


def revise_evidence(db: sqlite3.Connection, trial_id: str, station_id: str,
                    base_revision: int,
                    changes: list[EvidenceChange] | tuple[EvidenceChange, ...]) -> RevisionSnapshot:
    base = read_revision(db, trial_id, station_id, base_revision)
    policy = load_waiver_policy(db, trial_id)
    declared_groups = frozenset(policy.groups) if policy is not None else frozenset()
    validate_changes(base.catalog, station_id, changes, declared_groups)
    observations = apply_changes(base.observations, changes)
    return insert_revision(db, base, observations)
