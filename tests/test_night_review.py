from decimal import Decimal
import json

from evidence.trials import open_trial
from intake.registry import get_accepted_package
from reports.read import read_report
from reports.register import load_publish_receipt
from review.request import NoCommonExplanation, sign_report
from station.audit import audit_revision
from tests.fixtures import (
    ALL_PAIRS, DIFFERENT_PAIRS, SAME_PAIRS, ShiftFixture, external_fields,
    hard, linked_rows, local, public, soft,
)


class NightReviewTests(ShiftFixture):
    def test_joint_ledger_offline(self):
        a = self.issue('A', linked_rows())
        b = self.issue('B', [soft('prefer-different', public('X'), public('Y'))])
        ids = self.receive(a, b)
        self.close_sources()
        report, receipt = sign_report(self.center, *ids, ('X', 'Y'))
        self.assertEqual(
            (report.minimum_cost, report.pairs), (1, SAME_PAIRS),
            'WIRING_JOINT_LEDGER: expected cost 1 with the same-state pairs only',
        )
        self.assertEqual(tuple(source.package_id for source in report.sources), ids)
        self.assertEqual(tuple((source.station_id, source.revision) for source in report.sources), (('A', 1), ('B', 1)))
        self.assertEqual(read_report(self.center, receipt.report_id), report)
        self.assertEqual(load_publish_receipt(self.center, receipt.report_id), receipt)

    def test_same_and_different_private_paths_remain_distinguishable(self):
        same = self.issue('A', linked_rows('same'))
        different = self.issue('A', linked_rows('different'))
        soft_b = self.issue('B', [soft('prefer-different', public('X'), public('Y'))])
        same_id, different_id, right = self.receive(same, different, soft_b)
        self.close_sources()
        before, _ = sign_report(self.center, same_id, right, ('X', 'Y'))
        after, _ = sign_report(self.center, different_id, right, ('X', 'Y'))
        self.assertEqual((before.minimum_cost, before.pairs), (1, SAME_PAIRS))
        self.assertEqual((after.minimum_cost, after.pairs), (0, DIFFERENT_PAIRS))

    def test_independent_legal_packages_use_common_state(self):
        a = self.receive_external(external_fields('legal-A', 'A', ('0', None, None, '0'), revision=12))
        b = self.receive_external(external_fields('legal-B', 'B', ('1', '0', '0', '1'), revision=9))
        self.close_sources()
        report, receipt = sign_report(self.center, a, b, ('X', 'Y'))
        self.assertEqual((report.minimum_cost, report.pairs), (1, SAME_PAIRS))
        self.assertEqual(tuple((item.package_id, item.revision) for item in report.sources), (('legal-A', 12), ('legal-B', 9)))
        self.assertEqual(load_publish_receipt(self.center, receipt.report_id), receipt)

    def test_reordered_catalog_is_aligned_by_terminal_identity(self):
        left = external_fields('aligned-A', 'A', ('0', '0', None, None, None, None, '0', '0'),
                               terminals=('X', 'Y', 'Z'))
        right = external_fields('aligned-B', 'B', (None, None, '0', '0', '0', '0', None, None),
                                terminals=('Z', 'X', 'Y'))
        # A requires X=Y. B requires Z!=X in its own coordinates.
        a, b = self.receive_external(left), self.receive_external(right)
        self.close_sources()
        report, _ = sign_report(self.center, a, b, ('Z', 'X'))
        self.assertEqual((report.terminals, report.minimum_cost, report.pairs), (('Z', 'X'), 0, DIFFERENT_PAIRS))
        swapped, _ = sign_report(self.center, b, a, ('Z', 'X'))
        self.assertEqual((swapped.terminals, swapped.minimum_cost, swapped.pairs), (report.terminals, 0, DIFFERENT_PAIRS))
        self.assertEqual(tuple(source.package_id for source in swapped.sources), (b, a))

    def test_parallel_soft_observations_are_charged_individually(self):
        a = self.issue('A', linked_rows())
        b = self.issue('B', [
            soft('independent-2', public('X'), public('Y'), weight=2),
            soft('independent-3', public('X'), public('Y'), weight=3),
        ])
        ids = self.receive(a, b)
        self.close_sources()
        report, _ = sign_report(self.center, *ids, ('X', 'Y'))
        self.assertEqual((report.minimum_cost, report.pairs), (5, SAME_PAIRS))

    def test_conditioned_costs_keep_distinct_losing_and_winning_states(self):
        rows = [
            hard('pin', public('X'), local('u')),
            soft('prefer-same', local('u'), public('Y'), 'same', 2),
            soft('prefer-different', local('u'), public('Y'), 'different', 3),
        ]
        a = self.issue('A', rows)
        audit = audit_revision(self.sources['A'], 'T', 'A', a[1].revision)
        probes = ((0, 0), (0, 1), (1, 0), (1, 1))
        self.assertEqual(tuple(audit.analysis.cost_for(state) for state in probes), (3, 2, 2, 3))
        b = self.issue('B', [hard('same', public('X'), public('Y'))])
        a_id, b_id, empty_b = self.receive(a, b, self.issue('B'))
        self.close_sources()
        self.assertEqual(get_accepted_package(self.center, a_id).costs, (3, 2, 2, 3))
        forced, _ = sign_report(self.center, a_id, b_id, ('X', 'Y'))
        free, _ = sign_report(self.center, a_id, empty_b, ('X', 'Y'))
        self.assertEqual((forced.minimum_cost, forced.pairs), (3, SAME_PAIRS))
        self.assertEqual((free.minimum_cost, free.pairs), (2, DIFFERENT_PAIRS))

    def test_ordered_and_repeated_request_endpoints(self):
        ids = self.receive(self.issue('A', linked_rows()), self.issue('B'))
        self.close_sources()
        reverse, reverse_receipt = sign_report(self.center, *ids, ('Y', 'X'))
        repeated, receipt = sign_report(self.center, *ids, ('X', 'X'))
        self.assertEqual((reverse.terminals, reverse.pairs), (('Y', 'X'), SAME_PAIRS))
        self.assertEqual(read_report(self.center, reverse_receipt.report_id).terminals, ('Y', 'X'))
        self.assertEqual((repeated.terminals, repeated.pairs), (('X', 'X'), SAME_PAIRS))
        self.assertEqual(read_report(self.center, receipt.report_id), repeated)

    def test_single_public_terminal(self):
        for db in self.sources.values():
            open_trial(db, 'single', ('A', 'B'), ('X',))
        a = self.issue('A', [hard('link', public('X'), local('u'))], trial='single')
        b = self.issue('B', [soft('self', public('X'), public('X'), weight=4)], trial='single')
        ids = self.receive(a, b)
        self.close_sources()
        report, _ = sign_report(self.center, *ids, ('X', 'X'))
        self.assertEqual((report.minimum_cost, report.pairs), (4, SAME_PAIRS))

    def test_support_limits(self):
        terminals = tuple(f'P{i}' for i in range(6))
        for db in self.sources.values():
            open_trial(db, 'limits', ('A', 'B'), terminals)
        rows = []
        for index, name in enumerate(terminals):
            private = local(f'local-{index}')
            rows.append(hard(f'h{index}', public(name), private))
            for copy in range(3):
                rows.append(soft(f's{index}-{copy}', public(name), private))
        a_id, b_id = self.receive(self.issue('A', rows, 'limits'), self.issue('B', trial='limits'))
        self.close_sources()
        report, _ = sign_report(self.center, a_id, b_id, ('P0', 'P5'))
        self.assertEqual((report.minimum_cost, report.pairs), (18, ALL_PAIRS))

    def test_hard_conflict_keeps_packages_without_a_report(self):
        a = self.issue('A', linked_rows())
        b = self.issue('B', [hard('different', public('X'), public('Y'), 'different')])
        a_id, b_id = self.receive(a, b)
        self.close_sources()
        with self.assertRaises(NoCommonExplanation):
            sign_report(self.center, a_id, b_id, ('X', 'Y'))
        self.assert_report_counts(0, 0)
        self.assertEqual(get_accepted_package(self.center, a_id).costs, (0, None, None, 0))
        self.assertEqual(get_accepted_package(self.center, b_id).costs, (None, 0, 0, None))

    def test_locally_infeasible_package_rejects_report(self):
        a = self.issue('A', [hard('impossible', public('X'), public('X'), 'different')])
        ids = self.receive(a, self.issue('B'))
        self.close_sources()
        self.assertEqual(get_accepted_package(self.center, ids[0]).costs, (None,) * 4)
        with self.assertRaises(NoCommonExplanation):
            sign_report(self.center, *ids, ('X', 'Y'))
        self.assert_report_counts(0, 0)

    def test_cross_trial_packages_are_rejected(self):
        open_trial(self.sources['B'], 'other', ('A', 'B'), ('X', 'Y'))
        ids = self.receive(self.issue('A'), self.issue('B', trial='other'))
        self.close_sources()
        with self.assertRaisesRegex(ValueError, 'different trials'):
            sign_report(self.center, *ids, ('X', 'Y'))
        self.assert_report_counts(0, 0)

    def test_invalid_selection_leaves_no_report(self):
        a, b, second_a = self.receive(self.issue('A'), self.issue('B'), self.issue('A'))
        bad_catalog = self.receive_external(external_fields('extra', 'B', ('0', '0', '0', '0'), terminals=('X', 'Z')))
        bad_stations = self.receive_external(external_fields('wrong-stations', 'C', ('0', '0', '0', '0'), stations=('A', 'C')))
        self.close_sources()
        for left, right, terminals, error in (
            (a, 'missing', ('X', 'Y'), KeyError),
            (a, a, ('X', 'Y'), ValueError),
            (a, second_a, ('X', 'Y'), ValueError),
            (a, bad_catalog, ('X', 'Y'), ValueError),
            (a, bad_stations, ('X', 'Y'), ValueError),
            (a, b, ('X', 'absent'), ValueError),
            (a, b, ('X',), ValueError),
        ):
            with self.subTest(left=left, right=right, terminals=terminals):
                with self.assertRaises(error):
                    sign_report(self.center, left, right, terminals)
                self.assert_report_counts(0, 0)

    def test_cost_stays_exact_beyond_sqlite_and_decimal_string_limits(self):
        cost = 10**4400 + 7
        a = self.issue('A', linked_rows())
        b = self.issue('B', [soft('large', public('X'), public('Y'), weight=cost)])
        ids = self.receive(a, b)
        self.close_sources()
        report, receipt = sign_report(self.center, *ids, ('X', 'Y'))
        self.assertTrue(report.minimum_cost == cost)
        self.assertEqual(report.pairs, SAME_PAIRS)
        self.reopen_center()
        record = json.loads(read_report(self.center, receipt.report_id, 'export'))
        self.assertTrue(int(Decimal(record['minimum_cost'])) == cost)
