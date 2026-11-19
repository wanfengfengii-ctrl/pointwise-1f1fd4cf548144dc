import json
import sqlite3

from evidence.observations import Observation
from evidence.trials import register_waiver_policy
from reports.read import read_report
from reports.register import load_publish_receipt
from review.request import sign_report, sign_waiver_report
from station.issue import issue_waiver_package
from tests.fixtures import (
    SAME_PAIRS, ShiftFixture, install_commit_block,
    linked_rows, public, remove_commit_block, row_count, soft,
)


def grouped(record_id, left, right, relation='different', weight=1, group='G'):
    return Observation(record_id, left, right, relation, 'soft', weight, group)


class WaiverReportLifecycleTests(ShiftFixture):
    def _policies(self):
        for station in ('A', 'B'):
            register_waiver_policy(self.sources[station], 'T', ['G'], [[], ['G']])

    def _waiver(self, station, rows):
        revision = self.record(station, rows).revision if rows else 0
        return issue_waiver_package(self.sources[station], 'T', station, revision)

    def test_export_carries_policy_and_keeps_v1_export_unchanged(self):
        self._policies()
        v2_a = self._waiver('A', [grouped('fee-A', public('X'), public('Y'), 'different', 3)])
        v2_b = self._waiver('B', [soft('ordinary-B', public('X'), public('Y'), 'different', 1)])
        v1_a = self.issue('A', linked_rows())
        v1_b = self.issue('B', [soft('oppose', public('X'), public('Y'))])
        a_id = self.receive(v2_a)[0]
        b_id = self.receive(v2_b)[0]
        old_a, old_b = self.receive(v1_a, v1_b)
        self.close_sources()
        report, receipt = sign_waiver_report(self.center, a_id, b_id, ['X', 'Y'], ['G'])
        exported = json.loads(read_report(self.center, receipt.report_id, 'export'))
        self.assertEqual(exported, {
            'report_id': receipt.report_id,
            'trial_id': 'T',
            'terminals': ['X', 'Y'],
            'minimum_cost': str(report.minimum_cost),
            'pairs': [list(pair) for pair in report.pairs],
            'sources': [
                {'package_id': a_id, 'trial_id': 'T', 'station_id': 'A', 'revision': 1},
                {'package_id': b_id, 'trial_id': 'T', 'station_id': 'B', 'revision': 1},
            ],
            'policy': {'groups': ['G'], 'approved_combinations': [[], ['G']]},
            'waived_groups': ['G'],
        })
        # A V1 report on the same center keeps the original five business fields.
        v1_report, v1_receipt = sign_report(self.center, old_a, old_b, ['X', 'Y'])
        v1_export = json.loads(read_report(self.center, v1_receipt.report_id, 'export'))
        self.assertEqual(set(v1_export), {'report_id', 'trial_id', 'terminals',
                                          'minimum_cost', 'pairs', 'sources'})
        self.assertNotIn('policy', v1_export)
        self.assertEqual((v1_report.minimum_cost, v1_report.pairs), (1, SAME_PAIRS))

    def test_reopen_and_reprint_under_original_number_keeps_basis_and_provenance(self):
        self._policies()
        first = self._waiver('A', [
            soft('ordinary-A', public('X'), public('Y'), 'same', 2),
            grouped('fee-A', public('X'), public('Y'), 'different', 3),
        ])
        right = self._waiver('B', [soft('ordinary-B', public('X'), public('Y'), 'different', 1)])
        a_id, b_id = self.receive(first, right)
        self.close_sources()
        original, original_receipt = sign_waiver_report(
            self.center, a_id, b_id, ['X', 'Y'], ['G'])
        original_number = original_receipt.report_id
        self.reopen_center()
        reprinted = json.loads(read_report(self.center, original_number, 'export'))
        self.assertEqual((reprinted['minimum_cost'], reprinted['waived_groups']), ('1', ['G']))
        self.assertEqual(reprinted['pairs'], [list(pair) for pair in SAME_PAIRS])
        self.assertEqual([source['package_id'] for source in reprinted['sources']], [a_id, b_id])
        self.assertEqual(read_report(self.center, original_number), original)
        self.assertEqual(load_publish_receipt(self.center, original_number), original_receipt)

    def test_publish_commit_failure_rolls_back_and_request_retries(self):
        self._policies()
        a = self._waiver('A', [grouped('fee', public('X'), public('Y'))])
        b = self._waiver('B', [])
        a_id, b_id = self.receive(a, b)
        self.close_sources()
        install_commit_block(self.center, 'publish_receipts')
        with self.assertRaises(sqlite3.IntegrityError):
            sign_waiver_report(self.center, a_id, b_id, ['X', 'Y'], ['G'])
        self.assertFalse(self.center.in_transaction)
        self.reopen_center()
        self.assert_report_counts(0, 0)
        self.assertEqual(row_count(self.center, 'fixture_pending'), 0)
        from intake.registry import get_accepted_package
        self.assertIsNotNone(get_accepted_package(self.center, a_id))
        remove_commit_block(self.center)
        report, receipt = sign_waiver_report(self.center, a_id, b_id, ['X', 'Y'], ['G'])
        self.reopen_center()
        self.assert_report_counts(1, 1)
        self.assertEqual(read_report(self.center, receipt.report_id), report)

    def test_missing_report_keeps_v1_missing_semantics(self):
        self.assertIsNone(read_report(self.center, 4242))
        self.assertIsNone(read_report(self.center, 4242, 'export'))
        self.assertIsNone(load_publish_receipt(self.center, 4242))
