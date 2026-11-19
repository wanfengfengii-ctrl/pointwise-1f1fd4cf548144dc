import json
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
import unittest

from evidence.observations import EvidenceChange, Observation
from evidence.revision_store import initialize_evidence_store
from evidence.revisions import revise_evidence
from evidence.terminals import EndpointRef
from evidence.trials import open_trial
from intake.registry import accept_package
from intake.store import initialize_intake_store
from reports.register import initialize_report_store
from station.issue import initialize_issue_store, issue_package


SAME_PAIRS = ((0, 0), (1, 1))
DIFFERENT_PAIRS = ((0, 1), (1, 0))
ALL_PAIRS = ((0, 0), (0, 1), (1, 0), (1, 1))


def public(name):
    return EndpointRef('public', name)


def local(name, station='A'):
    return EndpointRef('local', name, station)


def hard(record_id, left, right, relation='same'):
    return Observation(record_id, left, right, relation, 'hard')


def soft(record_id, left, right, relation='different', weight=1):
    return Observation(record_id, left, right, relation, 'soft', weight)


def additions(rows):
    return [EvidenceChange('add', row.record_id, row) for row in rows]


def linked_rows(relation='same'):
    return (hard('wire-x', public('X'), local('u')), hard('wire-y', local('u'), public('Y'), relation))


def external_fields(package_id, station, costs, *, trial='T', stations=('A', 'B'),
                    terminals=('X', 'Y'), revision=0):
    # The caller supplies hand-calculated costs in the supplied coordinate order.
    return {
        'version': 1,
        'package_id': package_id,
        'source': {'trial_id': trial, 'station_id': station, 'revision': revision},
        'catalog': {'trial_id': trial, 'stations': list(stations), 'terminals': list(terminals)},
        'conditions': {'encoding': 'lex-costs', 'costs': list(costs)},
    }


def install_commit_block(db, receipt_table):
    if receipt_table not in ('issue_receipts', 'publish_receipts'):
        raise ValueError('unsupported receipt table for commit fixture')
    db.executescript(f'''
        CREATE TABLE fixture_parent(id INTEGER PRIMARY KEY);
        CREATE TABLE fixture_pending(parent_id INTEGER NOT NULL REFERENCES fixture_parent(id)
            DEFERRABLE INITIALLY DEFERRED);
        CREATE TRIGGER fixture_block_commit AFTER INSERT ON {receipt_table}
        BEGIN
            INSERT INTO fixture_pending(parent_id) VALUES (1);
        END;
    ''')


def remove_commit_block(db):
    db.execute('DROP TRIGGER fixture_block_commit')


def row_count(db, table):
    return db.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0]


class ShiftFixture(unittest.TestCase):
    def setUp(self):
        folder = TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.folder = Path(folder.name)
        self.sources = {station: self.connect_station(station) for station in ('A', 'B')}
        for db in self.sources.values():
            open_trial(db, 'T', ('A', 'B'), ('X', 'Y'))
        self.center = self.connect_center()

    def connect_station(self, station):
        db = sqlite3.connect(self.folder / f'station-{station}.db')
        self.addCleanup(db.close)
        initialize_evidence_store(db)
        initialize_issue_store(db)
        return db

    def connect_center(self):
        db = sqlite3.connect(self.folder / 'center.db')
        self.addCleanup(db.close)
        initialize_intake_store(db)
        initialize_report_store(db)
        return db

    def close_sources(self):
        for db in self.sources.values():
            db.close()

    def reopen_center(self):
        self.center.close()
        self.center = self.connect_center()

    def record(self, station, rows, trial='T', base_revision=0):
        return revise_evidence(self.sources[station], trial, station, base_revision, additions(rows))

    def issue(self, station, rows=(), trial='T'):
        revision = self.record(station, rows, trial).revision if rows else 0
        return issue_package(self.sources[station], trial, station, revision)

    def receive(self, *issued):
        return tuple(accept_package(self.center, wire).package_id for wire, _ in issued)

    def receive_external(self, fields):
        return accept_package(self.center, json.dumps(fields)).package_id

    def assert_report_counts(self, reports, receipts):
        self.assertEqual(row_count(self.center, 'formal_reports'), reports)
        self.assertEqual(row_count(self.center, 'publish_receipts'), receipts)
