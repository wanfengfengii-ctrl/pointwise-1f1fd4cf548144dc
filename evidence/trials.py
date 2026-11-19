import sqlite3

from evidence.revision_store import insert_trial_with_initial_revisions
from evidence.terminals import PublicCatalog, build_catalog
from evidence.waiver_policy import register_waiver_policy as _register_waiver_policy


def open_trial(db: sqlite3.Connection, trial_id: str, stations: list[str] | tuple[str, ...],
               terminals: list[str] | tuple[str, ...]) -> PublicCatalog:
    catalog = build_catalog(trial_id, stations, terminals)
    return insert_trial_with_initial_revisions(db, catalog)


def register_waiver_policy(db: sqlite3.Connection, trial_id: str,
                           groups: list[str] | tuple[str, ...],
                           approved_combinations: list | tuple) -> dict:
    return _register_waiver_policy(db, trial_id, groups, approved_combinations)
