from dataclasses import dataclass
import sqlite3

from intake.registry import get_accepted_package
from intake.validation import ValidatedPackage


@dataclass(frozen=True)
class ReviewSelection:
    trial_id: str
    left: ValidatedPackage
    right: ValidatedPackage


def select_packages(db: sqlite3.Connection, left_id: str, right_id: str) -> ReviewSelection:
    left = get_accepted_package(db, left_id)
    if left is None:
        raise KeyError(left_id)
    right = get_accepted_package(db, right_id)
    if right is None:
        raise KeyError(right_id)
    if left.catalog.trial_id != right.catalog.trial_id:
        raise ValueError('packages belong to different trials')
    if left.station_id == right.station_id:
        raise ValueError('review requires packages from two different stations')
    if set(left.catalog.stations) != set(right.catalog.stations):
        raise ValueError('packages disagree on the registered stations')
    return ReviewSelection(left.catalog.trial_id, left, right)
