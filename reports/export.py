import json
import sqlite3

from reports.document import ReportSnapshot, snapshot_fields
from reports.register import load_report, record_export


def render_report(report_id: int, report: ReportSnapshot) -> str:
    fields = snapshot_fields(report)
    fields['report_id'] = report_id
    return json.dumps(fields, sort_keys=True, separators=(',', ':'))


def export_report(db: sqlite3.Connection, report_id: int) -> str | None:
    report = load_report(db, report_id)
    if report is None:
        return None
    rendered = render_report(report_id, report)
    record_export(db, report_id)
    return rendered
