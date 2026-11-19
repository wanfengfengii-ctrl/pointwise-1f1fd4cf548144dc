import sqlite3

from reports.document import ReportSnapshot, ReportSource, build_report_snapshot
from reports.register import PublishReceipt, commit_report
from review.conclusions import ReviewConclusion


def publish_report(db: sqlite3.Connection, conclusion: ReviewConclusion) -> tuple[ReportSnapshot, PublishReceipt]:
    selected = conclusion.selection
    left = ReportSource(selected.left.package_id, selected.trial_id, selected.left.station_id, selected.left.revision)
    right = ReportSource(selected.right.package_id, selected.trial_id, selected.right.station_id, selected.right.revision)
    snapshot = build_report_snapshot(
        selected.trial_id, conclusion.terminals, conclusion.minimum_cost, conclusion.pairs, (left, right),
    )
    receipt = commit_report(db, snapshot)
    return snapshot, receipt
