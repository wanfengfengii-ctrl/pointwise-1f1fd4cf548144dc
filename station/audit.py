from dataclasses import dataclass
import sqlite3

from evidence.revisions import read_revision
from evidence.terminals import PublicCatalog
from station.analysis import ConditionedAnalysis, analyze_revision


@dataclass(frozen=True)
class AuditedRevision:
    catalog: PublicCatalog
    station_id: str
    revision: int
    analysis: ConditionedAnalysis


def audit_revision(db: sqlite3.Connection, trial_id: str, station_id: str,
                   revision: int) -> AuditedRevision:
    snapshot = read_revision(db, trial_id, station_id, revision)
    return AuditedRevision(snapshot.catalog, station_id, revision, analyze_revision(snapshot))
