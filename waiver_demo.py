"""Night-shift waiver demonstration: disconnected issuance, correction and reprint.

This scenario mirrors the handoff in WAIVERS.md. Both station libraries are
closed before the center signs anything, so every center decision uses only
the two frozen V2 packages. A later fee-basis correction produces a new
package and a new report, while the original formal number still reprints the
original G-waiver basis and the original two-package provenance.
"""
import json
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory

from evidence.observations import EvidenceChange, Observation
from evidence.revision_store import initialize_evidence_store
from evidence.revisions import revise_evidence
from evidence.trials import open_trial, register_waiver_policy
from intake.registry import accept_package
from intake.store import initialize_intake_store
from reports.read import read_report
from reports.register import initialize_report_store
from review.request import sign_waiver_report
from station.issue import initialize_issue_store, issue_waiver_package
from tests.fixtures import DIFFERENT_PAIRS, SAME_PAIRS, public, soft

TRIAL = 'bench-waiver'
STATIONS = ('A', 'B')
TERMINALS = ('X', 'Y')


def _grouped_fee():
    return Observation('fee-A', public('X'), public('Y'), 'different', 'soft', 3, 'G')


def _open_station(path: Path, station: str):
    db = sqlite3.connect(path)
    initialize_evidence_store(db)
    initialize_issue_store(db)
    open_trial(db, TRIAL, STATIONS, TERMINALS)
    register_waiver_policy(db, TRIAL, ['G'], [[], ['G']])
    return db


def _issue_first(path: Path, station: str, rows):
    db = _open_station(path, station)
    changes = [EvidenceChange('add', row.record_id, row) for row in rows]
    revision = revise_evidence(db, TRIAL, station, 0, changes).revision
    wire, receipt = issue_waiver_package(db, TRIAL, station, revision)
    db.close()  # the station library is sealed before the center works
    return wire, receipt


def run_waiver_demo(folder: Path) -> None:
    paths = {station: folder / f'waiver-{station}.db' for station in STATIONS}
    ordinary = soft('ordinary-A', public('X'), public('Y'), 'same', 2)
    right = soft('ordinary-B', public('X'), public('Y'), 'different', 1)
    wire_a, receipt_a = _issue_first(paths['A'], 'A', [ordinary, _grouped_fee()])
    wire_b, receipt_b = _issue_first(paths['B'], 'B', [right])

    center_path = folder / 'waiver-center.db'
    with sqlite3.connect(center_path) as center:
        initialize_intake_store(center)
        initialize_report_store(center)
        a_id = accept_package(center, wire_a).package_id
        b_id = accept_package(center, wire_b).package_id
        ordinary_report, ordinary_receipt = sign_waiver_report(
            center, a_id, b_id, TERMINALS, [])
        waived_report, waived_receipt = sign_waiver_report(
            center, a_id, b_id, TERMINALS, ['G'])

    if (ordinary_report.minimum_cost, ordinary_report.pairs) != (2, DIFFERENT_PAIRS):
        raise AssertionError('empty-combination accounting mismatch')
    if (waived_report.minimum_cost, waived_report.pairs) != (1, SAME_PAIRS):
        raise AssertionError('G-waiver accounting mismatch')
    original_number = waived_receipt.report_id

    # Day correction: fee-A returns to ordinary billing, then a new V2 package.
    reopened = _open_station(paths['A'], 'A')
    try:
        plain = soft('fee-A', public('X'), public('Y'), 'different', 3)
        corrected = revise_evidence(
            reopened, TRIAL, 'A', receipt_a.revision,
            [EvidenceChange('replace', 'fee-A', plain)],
        )
        new_wire, new_receipt = issue_waiver_package(reopened, TRIAL, 'A', corrected.revision)
    finally:
        reopened.close()

    with sqlite3.connect(center_path) as center:
        initialize_intake_store(center)
        initialize_report_store(center)
        new_a = accept_package(center, new_wire).package_id
        corrected_report, corrected_receipt = sign_waiver_report(
            center, new_a, b_id, TERMINALS, ['G'])
        if (corrected_report.minimum_cost, corrected_report.pairs) != (2, DIFFERENT_PAIRS):
            raise AssertionError('corrected waiver accounting mismatch')
        # Reopen semantics: the sealed original number still reprints its G basis.
        reprinted = json.loads(read_report(center, original_number, 'export'))

    if reprinted['minimum_cost'] != '1' or reprinted['waived_groups'] != ['G']:
        raise AssertionError('original report basis was not preserved')
    if [source['package_id'] for source in reprinted['sources']] != [a_id, b_id]:
        raise AssertionError('original two-package provenance was not preserved')

    scenario = {
        'case_id': 'waiver-night',
        'policy': {'groups': ['G'], 'approved_combinations': [[], ['G']]},
        'sources_sealed_before_signing': True,
        'empty_combination': {'minimum_cost': ordinary_report.minimum_cost,
                              'pairs': [list(pair) for pair in ordinary_report.pairs]},
        'waive_G_original': {'report_id': original_number,
                             'minimum_cost': waived_report.minimum_cost,
                             'pairs': [list(pair) for pair in waived_report.pairs],
                             'sources': [a_id, b_id]},
        'correction_fee_A_ungrouped': {'new_report_id': corrected_receipt.report_id,
                                       'minimum_cost': corrected_report.minimum_cost,
                                       'pairs': [list(pair) for pair in corrected_report.pairs],
                                       'new_package_id': new_receipt.package_id},
        'reprint_original_number': reprinted,
        'oracle': 'Waiving G removes only the fee-A violation charge; hard feasibility is untouched.',
    }
    print('POINTWISE_WAIVER_SCENARIO ' + json.dumps(scenario, sort_keys=True))


def main():
    with TemporaryDirectory() as directory:
        run_waiver_demo(Path(directory))


if __name__ == '__main__':
    main()
