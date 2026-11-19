import sqlite3

from reports.document import ReportSnapshot
from reports.publish import publish_report
from reports.register import PublishReceipt
from review.alignment import align_packages
from review.conclusions import build_conclusion
from review.joint_cost import find_joint_minimum
from review.selection import select_packages


class NoCommonExplanation(ValueError):
    """The two packages have no common hard-feasible public state."""


def sign_report(db: sqlite3.Connection, left_id: str, right_id: str,
                terminals: tuple[str, ...] | list[str]) -> tuple[ReportSnapshot, PublishReceipt]:
    selection = select_packages(db, left_id, right_id)
    aligned = align_packages(selection, terminals)
    minimum = find_joint_minimum(aligned)
    if minimum is None:
        raise NoCommonExplanation('the two packages have no common hard-feasible state')
    return publish_report(db, build_conclusion(aligned, minimum))
