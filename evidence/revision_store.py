from dataclasses import asdict, dataclass
from decimal import Decimal
import json
import sqlite3

from evidence.observations import Observation
from evidence.terminals import EndpointRef, PublicCatalog
from ledger_transaction import initialize_tables, write_transaction

_SCHEMA = (
    '''CREATE TABLE IF NOT EXISTS trials (
        trial_id TEXT PRIMARY KEY,
        first_station TEXT NOT NULL,
        second_station TEXT NOT NULL,
        terminals TEXT NOT NULL
    )''',
    '''CREATE TABLE IF NOT EXISTS station_revisions (
        trial_id TEXT NOT NULL REFERENCES trials(trial_id),
        station_id TEXT NOT NULL,
        revision INTEGER NOT NULL CHECK (revision >= 0),
        parent_revision INTEGER,
        observations TEXT NOT NULL,
        PRIMARY KEY (trial_id, station_id, revision),
        FOREIGN KEY (trial_id, station_id, parent_revision)
            REFERENCES station_revisions(trial_id, station_id, revision)
    )''',
)


@dataclass(frozen=True)
class RevisionSnapshot:
    catalog: PublicCatalog
    station_id: str
    revision: int
    parent_revision: int | None
    observations: tuple[Observation, ...]


def initialize_evidence_store(db: sqlite3.Connection) -> None:
    initialize_tables(db, _SCHEMA)


def load_trial_registration(db: sqlite3.Connection, trial_id: str) -> PublicCatalog | None:
    row = db.execute(
        'SELECT first_station, second_station, terminals FROM trials WHERE trial_id = ?',
        (trial_id,),
    ).fetchone()
    if row is None:
        return None
    first, second, terminals = row
    return PublicCatalog(trial_id, (first, second), tuple(json.loads(terminals)))


def insert_trial_with_initial_revisions(db: sqlite3.Connection,
                                        catalog: PublicCatalog) -> PublicCatalog:
    with write_transaction(db):
        registered = load_trial_registration(db, catalog.trial_id)
        if registered is not None:
            if registered != catalog:
                raise ValueError('trial number already has a different registration')
            return registered
        db.execute(
            'INSERT INTO trials (trial_id, first_station, second_station, terminals) VALUES (?, ?, ?, ?)',
            (catalog.trial_id, *catalog.stations, json.dumps(catalog.terminals)),
        )
        db.executemany(
            '''INSERT INTO station_revisions
               (trial_id, station_id, revision, parent_revision, observations)
               VALUES (?, ?, 0, NULL, '[]')''',
            ((catalog.trial_id, station_id) for station_id in catalog.stations),
        )
    return catalog


def _encode_observations(rows: tuple[Observation, ...]) -> str:
    records = []
    for observation in rows:
        fields = asdict(observation)
        if observation.weight is not None:
            fields['weight'] = str(Decimal(observation.weight))
        records.append(fields)
    return json.dumps(records, sort_keys=True, separators=(',', ':'))


def _decode_observations(encoded: str) -> tuple[Observation, ...]:
    observations = []
    for record in json.loads(encoded):
        weight = record['weight']
        observations.append(Observation(
            record['record_id'], EndpointRef(**record['left']), EndpointRef(**record['right']),
            record['relation'], record['kind'], None if weight is None else int(Decimal(weight)),
        ))
    return tuple(observations)


def load_revision(db: sqlite3.Connection, trial_id: str, station_id: str,
                  revision: int) -> RevisionSnapshot | None:
    catalog = load_trial_registration(db, trial_id)
    if catalog is None or station_id not in catalog.stations:
        return None
    row = db.execute(
        '''SELECT parent_revision, observations FROM station_revisions
           WHERE trial_id = ? AND station_id = ? AND revision = ?''',
        (trial_id, station_id, revision),
    ).fetchone()
    if row is None:
        return None
    parent, observations = row
    return RevisionSnapshot(catalog, station_id, revision, parent, _decode_observations(observations))


def insert_revision(db: sqlite3.Connection, base: RevisionSnapshot,
                    observations: tuple[Observation, ...]) -> RevisionSnapshot:
    trial_id = base.catalog.trial_id
    encoded = _encode_observations(observations)
    with write_transaction(db):
        latest, = db.execute(
            'SELECT MAX(revision) FROM station_revisions WHERE trial_id = ? AND station_id = ?',
            (trial_id, base.station_id),
        ).fetchone()
        if latest is None:
            raise KeyError('unknown station revision')
        revision = latest + 1
        db.execute(
            '''INSERT INTO station_revisions
               (trial_id, station_id, revision, parent_revision, observations)
               VALUES (?, ?, ?, ?, ?)''',
            (trial_id, base.station_id, revision, base.revision, encoded),
        )
    return RevisionSnapshot(base.catalog, base.station_id, revision, base.revision, observations)
