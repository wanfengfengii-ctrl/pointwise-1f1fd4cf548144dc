from collections.abc import Iterator, Sequence
from contextlib import contextmanager
import sqlite3


def _require_idle(db: sqlite3.Connection) -> None:
    if db.in_transaction:
        raise sqlite3.ProgrammingError('ledger writes require an idle connection')


@contextmanager
def write_transaction(db: sqlite3.Connection) -> Iterator[None]:
    _require_idle(db)
    db.execute('BEGIN IMMEDIATE')
    with db:
        yield


def initialize_tables(db: sqlite3.Connection, statements: Sequence[str]) -> None:
    _require_idle(db)
    db.execute('PRAGMA foreign_keys = ON')
    with write_transaction(db):
        for statement in statements:
            db.execute(statement)
