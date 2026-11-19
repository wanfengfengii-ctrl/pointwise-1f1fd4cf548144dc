from dataclasses import dataclass
import hashlib
import sqlite3

from ledger_transaction import initialize_tables, write_transaction

_SCHEMA = (
    '''CREATE TABLE IF NOT EXISTS accepted_packages (
        acceptance_number INTEGER PRIMARY KEY,
        package_id TEXT NOT NULL UNIQUE,
        content_digest TEXT NOT NULL,
        wire TEXT NOT NULL
    )''',
)


@dataclass(frozen=True)
class AcceptedPackage:
    acceptance_number: int
    package_id: str
    content_digest: str
    wire: str


def initialize_intake_store(db: sqlite3.Connection) -> None:
    initialize_tables(db, _SCHEMA)


def load_accepted_package(db: sqlite3.Connection, package_id: str) -> AcceptedPackage | None:
    row = db.execute(
        '''SELECT acceptance_number, package_id, content_digest, wire
           FROM accepted_packages WHERE package_id = ?''',
        (package_id,),
    ).fetchone()
    return None if row is None else AcceptedPackage(*row)


def record_acceptance(db: sqlite3.Connection, package_id: str, wire: str) -> AcceptedPackage:
    digest = hashlib.sha256(wire.encode('utf-8')).hexdigest()
    with write_transaction(db):
        existing = load_accepted_package(db, package_id)
        if existing is not None:
            if existing.content_digest != digest or existing.wire != wire:
                raise ValueError('package identifier already refers to different content')
            return existing
        cursor = db.execute(
            'INSERT INTO accepted_packages (package_id, content_digest, wire) VALUES (?, ?, ?)',
            (package_id, digest, wire),
        )
        accepted = AcceptedPackage(cursor.lastrowid, package_id, digest, wire)
    return accepted
