import sqlite3

from evidence.revision_store import insert_trial_with_initial_revisions
from evidence.terminals import PublicCatalog, build_catalog


def open_trial(db: sqlite3.Connection, trial_id: str, stations: list[str] | tuple[str, ...],
               terminals: list[str] | tuple[str, ...]) -> PublicCatalog:
    catalog = build_catalog(trial_id, stations, terminals)
    return insert_trial_with_initial_revisions(db, catalog)
