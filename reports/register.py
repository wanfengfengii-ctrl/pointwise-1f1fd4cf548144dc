from dataclasses import dataclass
import json
import sqlite3

from ledger_transaction import initialize_tables, write_transaction
from reports.document import ReportSnapshot, snapshot_fields, snapshot_from_fields

_SCHEMA = (
    '''CREATE TABLE IF NOT EXISTS formal_reports (
        report_id INTEGER PRIMARY KEY,
        snapshot TEXT NOT NULL
    )''',
    '''CREATE TABLE IF NOT EXISTS publish_receipts (
        report_id INTEGER PRIMARY KEY REFERENCES formal_reports(report_id),
        trial_id TEXT NOT NULL
    )''',
    '''CREATE TABLE IF NOT EXISTS report_exports (
        export_number INTEGER PRIMARY KEY,
        report_id INTEGER NOT NULL REFERENCES formal_reports(report_id)
    )''',
)


@dataclass(frozen=True)
class PublishReceipt:
    report_id: int
    trial_id: str


def initialize_report_store(db: sqlite3.Connection) -> None:
    initialize_tables(db, _SCHEMA)


def _require_report_id(report_id: int) -> None:
    if type(report_id) is not int or not 0 < report_id < 2**63:
        raise ValueError('invalid report number')


def commit_report(db: sqlite3.Connection, report: ReportSnapshot) -> PublishReceipt:
    archived = json.dumps(snapshot_fields(report), sort_keys=True, separators=(',', ':'))
    with write_transaction(db):
        cursor = db.execute('INSERT INTO formal_reports (snapshot) VALUES (?)', (archived,))
        receipt = PublishReceipt(cursor.lastrowid, report.trial_id)
        db.execute(
            'INSERT INTO publish_receipts (report_id, trial_id) VALUES (?, ?)',
            (receipt.report_id, receipt.trial_id),
        )
    return receipt


def load_report(db: sqlite3.Connection, report_id: int) -> ReportSnapshot | None:
    _require_report_id(report_id)
    row = db.execute('SELECT snapshot FROM formal_reports WHERE report_id = ?', (report_id,)).fetchone()
    return None if row is None else snapshot_from_fields(json.loads(row[0]))


def load_publish_receipt(db: sqlite3.Connection, report_id: int) -> PublishReceipt | None:
    _require_report_id(report_id)
    row = db.execute(
        'SELECT trial_id FROM publish_receipts WHERE report_id = ?', (report_id,),
    ).fetchone()
    return None if row is None else PublishReceipt(report_id, row[0])


def record_export(db: sqlite3.Connection, report_id: int) -> int:
    _require_report_id(report_id)
    with write_transaction(db):
        cursor = db.execute('INSERT INTO report_exports (report_id) VALUES (?)', (report_id,))
        export_number = cursor.lastrowid
    return export_number
