from dataclasses import dataclass
import sqlite3

from evidence.terminals import require_identifier
from ledger_transaction import initialize_tables, write_transaction
from station.audit import audit_revision
from station.package import encode_package, freeze_package

_SCHEMA = (
    '''CREATE TABLE IF NOT EXISTS issued_packages (
        issue_number INTEGER PRIMARY KEY,
        package_id TEXT NOT NULL UNIQUE,
        wire TEXT NOT NULL
    )''',
    '''CREATE TABLE IF NOT EXISTS issue_receipts (
        package_id TEXT PRIMARY KEY REFERENCES issued_packages(package_id),
        trial_id TEXT NOT NULL,
        station_id TEXT NOT NULL,
        revision INTEGER NOT NULL,
        FOREIGN KEY (trial_id, station_id, revision)
            REFERENCES station_revisions(trial_id, station_id, revision)
    )''',
)


@dataclass(frozen=True)
class IssueReceipt:
    package_id: str
    trial_id: str
    station_id: str
    revision: int


def initialize_issue_store(db: sqlite3.Connection) -> None:
    initialize_tables(db, _SCHEMA)


def issue_package(db: sqlite3.Connection, trial_id: str, station_id: str,
                  revision: int) -> tuple[str, IssueReceipt]:
    audited = audit_revision(db, trial_id, station_id, revision)
    with write_transaction(db):
        issue_number, = db.execute('SELECT COALESCE(MAX(issue_number), 0) + 1 FROM issued_packages').fetchone()
        package = freeze_package(audited, issue_number)
        wire = encode_package(package)
        source = package.source
        receipt = IssueReceipt(package.package_id, source.trial_id, source.station_id, source.revision)
        db.execute(
            'INSERT INTO issued_packages (issue_number, package_id, wire) VALUES (?, ?, ?)',
            (issue_number, receipt.package_id, wire),
        )
        db.execute(
            'INSERT INTO issue_receipts (package_id, trial_id, station_id, revision) VALUES (?, ?, ?, ?)',
            (receipt.package_id, receipt.trial_id, receipt.station_id, receipt.revision),
        )
    return wire, receipt


def read_issued_package(db: sqlite3.Connection, package_id: str) -> tuple[str, IssueReceipt] | None:
    require_identifier(package_id, 'package identifier')
    row = db.execute(
        '''SELECT p.wire, r.trial_id, r.station_id, r.revision
           FROM issued_packages AS p JOIN issue_receipts AS r USING (package_id)
           WHERE p.package_id = ?''',
        (package_id,),
    ).fetchone()
    if row is None:
        return None
    wire, trial_id, station_id, revision = row
    return wire, IssueReceipt(package_id, trial_id, station_id, revision)
