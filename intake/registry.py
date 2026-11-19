import sqlite3

from evidence.terminals import require_identifier
from intake.codec import canonical_content, decode_package
from intake.store import AcceptedPackage, load_accepted_package, record_acceptance
from intake.validation import ValidatedPackage, validate_package


def accept_package(db: sqlite3.Connection, wire: str | bytes) -> AcceptedPackage:
    decoded = decode_package(wire)
    validated = validate_package(decoded)
    return record_acceptance(db, validated.package_id, canonical_content(decoded))


def get_accepted_package(db: sqlite3.Connection, package_id: str) -> ValidatedPackage | None:
    require_identifier(package_id, 'package identifier')
    accepted = load_accepted_package(db, package_id)
    if accepted is None:
        return None
    return validate_package(decode_package(accepted.wire))
