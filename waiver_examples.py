from contextlib import closing
import json
import sqlite3

from evidence.revision_store import initialize_evidence_store
from evidence.revisions import revise_evidence
from evidence.trials import open_trial
from intake.registry import accept_package, get_accepted_package
from intake.store import initialize_intake_store
from reports.register import initialize_report_store
from review.request import sign_report
from station.issue import initialize_issue_store, issue_package
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


def main():
    results = {}
    for name, case in CASES.items():
        wires, tables, result = probe_v1(case)
        if (tables, result) != (case["v1_tables"], case["expected"]["ordinary"]):
            raise AssertionError((name, tables, result))
        results[name] = wires
        print(json.dumps({"case": name, "v1_tables": tables, "v1_result": result,
                          "expected_v2": case["expected"]}, sort_keys=True))
    if results["grouped"] != results["ungrouped"]:
        raise AssertionError("the two V1 handoffs must have identical bytes")


if __name__ == "__main__":
    main()
