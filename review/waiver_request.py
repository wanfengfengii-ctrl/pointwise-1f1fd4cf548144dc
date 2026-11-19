from dataclasses import dataclass
import sqlite3

from intake.registry import get_accepted_package
from intake.validation import ValidatedWaiverPackage
from reports.publish import publish_waiver_report
from reports.document import ReportSource
from review.alignment import align_packages
from review.conclusions import build_conclusion
from review.joint_cost import find_joint_minimum
from review.request import NoCommonExplanation
from review.selection import ReviewSelection
from evidence.terminals import require_identifier


@dataclass(frozen=True)
class _CostView:
    """Adapt one approved combination's cost table to the V1 package shape."""
    package_id: str
    catalog: object
    station_id: str
    revision: int
    costs: tuple[int | None, ...]


@dataclass(frozen=True)
class WaiverReviewSelection:
    trial_id: str
    left: ValidatedWaiverPackage
    right: ValidatedWaiverPackage
    combination: tuple[str, ...]


def _normalize_requested_groups(waived_groups, policy) -> tuple[str, ...]:
    if not isinstance(waived_groups, (list, tuple)):
        raise ValueError('waived groups must be a list or tuple')
    members = []
    seen = set()
    for group in waived_groups:
        name = require_identifier(group, 'waived group')
        if name in seen:
            raise ValueError('waived groups must be distinct')
        seen.add(name)
        members.append(name)
    combination = tuple(sorted(members))
    if combination not in policy.approved_combinations:
        raise ValueError('the requested waiver combination is not approved')
    return combination


def select_waiver_packages(db: sqlite3.Connection, left_id: str, right_id: str,
                           waived_groups: list[str] | tuple[str, ...]) -> WaiverReviewSelection:
    left = get_accepted_package(db, left_id)
    if left is None:
        raise KeyError(left_id)
    right = get_accepted_package(db, right_id)
    if right is None:
        raise KeyError(right_id)
    if not isinstance(left, ValidatedWaiverPackage) or not isinstance(right, ValidatedWaiverPackage):
        raise ValueError('sign_waiver_report accepts V2 packages only')
    if left.catalog.trial_id != right.catalog.trial_id:
        raise ValueError('packages belong to different trials')
    if left.station_id == right.station_id:
        raise ValueError('review requires packages from two different stations')
    if set(left.catalog.stations) != set(right.catalog.stations):
        raise ValueError('packages disagree on the registered stations')
    if left.catalog.terminals != right.catalog.terminals and set(left.catalog.terminals) != set(right.catalog.terminals):
        raise ValueError('packages disagree on the public terminals')
    if left.policy != right.policy:
        raise ValueError('the two packages do not share the same waiver policy')
    combination = _normalize_requested_groups(waived_groups, left.policy)
    return WaiverReviewSelection(left.catalog.trial_id, left, right, combination)


def sign_waiver_report(db: sqlite3.Connection, left_id: str, right_id: str,
                       terminals: tuple[str, ...] | list[str],
                       waived_groups: list[str] | tuple[str, ...]):
    selection = select_waiver_packages(db, left_id, right_id, waived_groups)
    combination = selection.combination
    left_view = _CostView(
        selection.left.package_id, selection.left.catalog, selection.left.station_id,
        selection.left.revision, selection.left.costs_for(combination),
    )
    right_view = _CostView(
        selection.right.package_id, selection.right.catalog, selection.right.station_id,
        selection.right.revision, selection.right.costs_for(combination),
    )
    v1_selection = ReviewSelection(selection.trial_id, left_view, right_view)
    aligned = align_packages(v1_selection, terminals)
    minimum = find_joint_minimum(aligned)
    if minimum is None:
        raise NoCommonExplanation('the two packages have no common hard-feasible state')
    conclusion = build_conclusion(aligned, minimum)
    sources = (
        ReportSource(left_view.package_id, selection.trial_id, left_view.station_id, left_view.revision),
        ReportSource(right_view.package_id, selection.trial_id, right_view.station_id, right_view.revision),
    )
    return publish_waiver_report(db, conclusion, selection.left.policy, combination, sources)
