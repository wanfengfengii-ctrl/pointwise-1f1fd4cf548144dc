import sqlite3

from reports.document import ReportSnapshot
from reports.export import export_report
from reports.register import load_report


def read_report(db: sqlite3.Connection, report_id: int,
                mode: str = 'read') -> ReportSnapshot | str | None:
    if mode == 'read':
        return load_report(db, report_id)
    if mode == 'export':
        return export_report(db, report_id)
    raise ValueError('report mode must be read or export')
