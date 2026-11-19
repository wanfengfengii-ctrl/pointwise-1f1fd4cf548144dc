from contextlib import closing
import json
import sqlite3

from evidence.observations import Observation
from evidence.revision_store import initialize_evidence_store
from evidence.revisions import revise_evidence
from evidence.trials import open_trial, register_waiver_policy
from intake.registry import accept_package, get_accepted_package
from intake.store import initialize_intake_store
from reports.read import read_report
from reports.register import initialize_report_store
from review.request import sign_report, sign_waiver_report
from station.issue import initialize_issue_store, issue_package, issue_waiver_package
from tests.fixtures import ALL_PAIRS, DIFFERENT_PAIRS, SAME_PAIRS, additions, local, public, soft

TRIAL = "bench-waiver"
STATIONS = ("A", "B")
TERMINALS = ("X", "Y")
GROUPS = ("G",)
APPROVED = ((), ("G",))

x, y, u = public("X"), public("Y"), local("u")
ordinary = soft("ordinary-A", x, y, "same", 2)
fee = soft("fee-A", x, y, "different", 3)
right = soft("ordinary-B", x, y, "different", 1)

CASES = {
    "grouped": {
        "rows": {"A": ((ordinary, None), (fee, "G")), "B": ((right, None),)},
        "v1_tables": ((3, 2, 2, 3), (1, 0, 0, 1)),
        "expected": {"ordinary": (2, DIFFERENT_PAIRS), "waive_G": (1, SAME_PAIRS)},
    },
    "ungrouped": {
        "rows": {"A": ((ordinary, None), (fee, None)), "B": ((right, None),)},
        "v1_tables": ((3, 2, 2, 3), (1, 0, 0, 1)),
        "expected": {"ordinary": (2, DIFFERENT_PAIRS), "waive_G": (2, DIFFERENT_PAIRS)},
    },
    "private-choice": {
        "rows": {
            "A": ((soft("ordinary-private", x, u, "same", 2), None),
                  (soft("fee-private", x, u, "different", 3), "G")),
            "B": (),
        },
        "v1_tables": ((2, 2, 2, 2), (0, 0, 0, 0)),
        "expected": {"ordinary": (2, ALL_PAIRS), "waive_G": (0, ALL_PAIRS)},
    },
}


def _grouped_observation(row, group):
    if group is None:
        return row
    return Observation(row.record_id, row.left, row.right, row.relation, row.kind, row.weight, group)


def probe_v1(case):
    wires = []
    for station in STATIONS:
        with closing(sqlite3.connect(":memory:")) as source:
            initialize_evidence_store(source)
            initialize_issue_store(source)
            open_trial(source, TRIAL, STATIONS, TERMINALS)
            rows = [row for row, group in case["rows"][station]]
            revision = revise_evidence(source, TRIAL, station, 0, additions(rows)).revision if rows else 0
            wire, _ = issue_package(source, TRIAL, station, revision)
            wires.append(wire)
    with closing(sqlite3.connect(":memory:")) as center:
        initialize_intake_store(center)
        initialize_report_store(center)
        ids = tuple(accept_package(center, wire).package_id for wire in wires)
        tables = tuple(get_accepted_package(center, package_id).costs for package_id in ids)
        report, _ = sign_report(center, *ids, TERMINALS)
    return tuple(wires), tables, (report.minimum_cost, report.pairs)


def _open_waiver_source(case, station):
    db = sqlite3.connect(":memory:")
    initialize_evidence_store(db)
    initialize_issue_store(db)
    open_trial(db, TRIAL, STATIONS, TERMINALS)
    register_waiver_policy(db, TRIAL, list(GROUPS), [list(combo) for combo in APPROVED])
    rows = [_grouped_observation(row, group) for row, group in case["rows"][station]]
    revision = revise_evidence(db, TRIAL, station, 0, additions(rows)).revision if rows else 0
    wire, receipt = issue_waiver_package(db, TRIAL, station, revision)
    return db, wire, receipt


def probe_v2(case):
    sources = {station: _open_waiver_source(case, station) for station in STATIONS}
    center = sqlite3.connect(":memory:")
    initialize_intake_store(center)
    initialize_report_store(center)
    ids = tuple(accept_package(center, sources[station][1]).package_id for station in STATIONS)
    ordinary_report, ordinary_receipt = sign_waiver_report(center, *ids, TERMINALS, [])
    waived_report, waived_receipt = sign_waiver_report(center, *ids, TERMINALS, ["G"])
    ordinary = (ordinary_report.minimum_cost, ordinary_report.pairs)
    waived = (waived_report.minimum_cost, waived_report.pairs)
    reprinted = json.loads(read_report(center, waived_receipt.report_id, "export"))
    for db, _, _ in sources.values():
        db.close()
    center.close()
    return ordinary, waived, reprinted


def main():
    results = {}
    for name, case in CASES.items():
        wires, tables, result = probe_v1(case)
        if (tables, result) != (case["v1_tables"], case["expected"]["ordinary"]):
            raise AssertionError((name, tables, result))
        results[name] = wires
        ordinary, waived, reprinted = probe_v2(case)
        if ordinary != case["expected"]["ordinary"]:
            raise AssertionError((name, "v2 ordinary", ordinary, case["expected"]["ordinary"]))
        if waived != case["expected"]["waive_G"]:
            raise AssertionError((name, "v2 waive_G", waived, case["expected"]["waive_G"]))
        if reprinted["policy"] != {"groups": ["G"], "approved_combinations": [[], ["G"]]}:
            raise AssertionError((name, "reprinted policy", reprinted.get("policy")))
        if reprinted["waived_groups"] != ["G"]:
            raise AssertionError((name, "reprinted groups", reprinted.get("waived_groups")))
        print(json.dumps({"case": name, "v1_tables": tables, "v1_result": result,
                          "v2_ordinary": ordinary, "v2_waive_G": waived,
                          "expected_v2": case["expected"]}, sort_keys=True))
    if results["grouped"] != results["ungrouped"]:
        raise AssertionError("the two V1 handoffs must have identical bytes")


if __name__ == "__main__":
    main()
