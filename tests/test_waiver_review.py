import json

from evidence.observations import EvidenceChange, Observation
from evidence.revisions import revise_evidence
from evidence.trials import register_waiver_policy
from intake.registry import accept_package, get_accepted_package
from reports.read import read_report
from reports.register import load_publish_receipt
from review.request import NoCommonExplanation, sign_report, sign_waiver_report
from station.issue import issue_waiver_package
from tests.fixtures import (
    ALL_PAIRS, DIFFERENT_PAIRS, SAME_PAIRS, ShiftFixture, hard, local, public, soft,
)


def grouped(record_id, left, right, relation='different', weight=1, group='G'):
    return Observation(record_id, left, right, relation, 'soft', weight, group)


def revise(db, observation, base_revision):
    return revise_evidence(db, 'T', 'A', base_revision,
                           [EvidenceChange('replace', observation.record_id, observation)])


class WaiverReviewTests(ShiftFixture):
    def _policies(self, trial='T'):
        for station in ('A', 'B'):
            register_waiver_policy(self.sources[station], trial, ['G'], [[], ['G']])

    def _issue_waiver(self, station, rows, trial='T'):
        revision = self.record(station, rows, trial).revision if rows else 0
        return issue_waiver_package(self.sources[station], trial, station, revision)

    def _accept(self, wire):
        return accept_package(self.center, wire if isinstance(wire, str) else json.dumps(wire)).package_id

    def test_grouped_waiver_matches_hand_calculated_costs_and_pairs(self):
        self._policies()
        a = self._issue_waiver('A', [
            soft('ordinary-A', public('X'), public('Y'), 'same', 2),
            grouped('fee-A', public('X'), public('Y'), 'different', 3),
        ])
        b = self._issue_waiver('B', [soft('ordinary-B', public('X'), public('Y'), 'different', 1)])
        a_id = self._accept(a[0])
        b_id = self._accept(b[0])
        self.close_sources()
        ordinary, ordinary_receipt = sign_waiver_report(self.center, a_id, b_id, ['X', 'Y'], [])
        waived, waived_receipt = sign_waiver_report(self.center, a_id, b_id, ['X', 'Y'], ['G'])
        self.assertEqual((ordinary.minimum_cost, ordinary.pairs), (2, DIFFERENT_PAIRS))
        self.assertEqual((waived.minimum_cost, waived.pairs), (1, SAME_PAIRS))
        self.assertEqual(ordinary.waived_groups, ())
        self.assertEqual(waived.waived_groups, ('G',))
        self.assertEqual(waived.policy, {'groups': ('G',), 'approved_combinations': ((), ('G',))})
        self.assertEqual(tuple(source.package_id for source in waived.sources), (a_id, b_id))
        self.assertEqual(read_report(self.center, waived_receipt.report_id), waived)
        self.assertEqual(load_publish_receipt(self.center, waived_receipt.report_id), waived_receipt)

    def test_ungrouped_correction_keeps_ordinary_cost_under_the_waiver(self):
        self._policies()
        first = self._issue_waiver('A', [
            soft('ordinary-A', public('X'), public('Y'), 'same', 2),
            grouped('fee-A', public('X'), public('Y'), 'different', 3),
        ])
        b = self._issue_waiver('B', [soft('ordinary-B', public('X'), public('Y'), 'different', 1)])
        a_id = self._accept(first[0])
        b_id = self._accept(b[0])
        with self.connect_station('A') as reopened:
            register_waiver_policy(reopened, 'T', ['G'], [[], ['G']])
            plain = soft('fee-A', public('X'), public('Y'), 'different', 3)
            corrected = revise(reopened, plain, first[1].revision)
            new_wire, new_receipt = issue_waiver_package(reopened, 'T', 'A', corrected.revision)
        new_id = self._accept(new_wire)
        self.close_sources()
        report, _ = sign_waiver_report(self.center, new_id, b_id, ['X', 'Y'], ['G'])
        self.assertEqual((report.minimum_cost, report.pairs), (2, DIFFERENT_PAIRS))
        earlier, earlier_receipt = sign_waiver_report(self.center, a_id, b_id, ['X', 'Y'], ['G'])
        self.assertEqual((earlier.minimum_cost, earlier.pairs), (1, SAME_PAIRS))
        self.reopen_center()
        stored = read_report(self.center, earlier_receipt.report_id)
        self.assertEqual((stored.minimum_cost, stored.waived_groups), (1, ('G',)))
        self.assertEqual([source.package_id for source in stored.sources], [a_id, b_id])

    def test_private_choice_both_accountings_allow_all_pairs(self):
        self._policies()
        a = self._issue_waiver('A', [
            soft('ordinary-private', public('X'), local('u'), 'same', 2),
            grouped('fee-private', public('X'), local('u'), 'different', 3),
        ])
        b = self._issue_waiver('B', [])
        a_id, b_id = self._accept(a[0]), self._accept(b[0])
        self.close_sources()
        ordinary, _ = sign_waiver_report(self.center, a_id, b_id, ['X', 'Y'], [])
        waived, _ = sign_waiver_report(self.center, a_id, b_id, ['X', 'Y'], ['G'])
        self.assertEqual((ordinary.minimum_cost, ordinary.pairs), (2, ALL_PAIRS))
        self.assertEqual((waived.minimum_cost, waived.pairs), (0, ALL_PAIRS))

    def test_hard_conflict_blocks_every_combination(self):
        self._policies()
        a = self._issue_waiver('A', [hard('a-same', public('X'), public('Y'), 'same')])
        b = self._issue_waiver('B', [hard('b-different', public('X'), public('Y'), 'different')])
        a_id, b_id = self._accept(a[0]), self._accept(b[0])
        self.close_sources()
        for combination in ([], ['G']):
            with self.subTest(combination=combination):
                with self.assertRaises(NoCommonExplanation):
                    sign_waiver_report(self.center, a_id, b_id, ['X', 'Y'], combination)
        self.assert_report_counts(0, 0)

    def test_mixed_versions_and_policy_mismatch_are_rejected(self):
        self._policies()
        v2_a = self._issue_waiver('A', [grouped('fee', public('X'), public('Y'))])
        v2_b = self._issue_waiver('B', [])
        v1_a = self.issue('A', [soft('plain', public('X'), public('Y'))])
        v1_b = self.issue('B')
        a2, b2 = self._accept(v2_a[0]), self._accept(v2_b[0])
        a1, b1 = self.receive(v1_a, v1_b)
        other = self._policy_mismatch_package()
        self.close_sources()
        for left, right in ((a1, b2), (a2, b1)):
            with self.subTest(left=left, right=right):
                with self.assertRaisesRegex(ValueError, 'V2 packages only'):
                    sign_waiver_report(self.center, left, right, ['X', 'Y'], [])
        with self.assertRaisesRegex(ValueError, 'V1 packages only'):
            sign_report(self.center, a2, b2, ['X', 'Y'])
        with self.assertRaisesRegex(ValueError, 'same waiver policy'):
            sign_waiver_report(self.center, a2, other, ['X', 'Y'], [])
        self.assert_report_counts(0, 0)

    def _policy_mismatch_package(self):
        # A legal V2 package whose policy content differs from the two stations' policy.
        wire = {
            'version': 2,
            'package_id': 'mismatch-B',
            'source': {'trial_id': 'T', 'station_id': 'B', 'revision': 0},
            'catalog': {'trial_id': 'T', 'stations': ['A', 'B'], 'terminals': ['X', 'Y']},
            'policy': {'groups': ['G', 'H'],
                       'approved_combinations': [[], ['G'], ['G', 'H'], ['H']]},
            'conditions': {'encoding': 'waiver-lex-costs', 'tables': [
                {'combination': [], 'costs': ['0', '0', '0', '0']},
                {'combination': ['G'], 'costs': ['0', '0', '0', '0']},
                {'combination': ['H'], 'costs': ['0', '0', '0', '0']},
                {'combination': ['G', 'H'], 'costs': ['0', '0', '0', '0']},
            ]},
        }
        return self._accept(wire)

    def test_unapproved_combination_and_bad_group_inputs_raise_value_error(self):
        self._policies()
        a = self._issue_waiver('A', [grouped('fee', public('X'), public('Y'))])
        b = self._issue_waiver('B', [])
        a_id, b_id = self._accept(a[0]), self._accept(b[0])
        self.close_sources()
        for waived in (['H'], ['G', 'G'], 'G', None):
            with self.subTest(waived=waived):
                with self.assertRaises(ValueError):
                    sign_waiver_report(self.center, a_id, b_id, ['X', 'Y'], waived)

    def test_unknown_package_raises_key_error(self):
        self._policies()
        a = self._issue_waiver('A', [])
        a_id = self._accept(a[0])
        self.close_sources()
        with self.assertRaises(KeyError):
            sign_waiver_report(self.center, a_id, 'missing-package', ['X', 'Y'], [])

    def test_reordered_catalog_aligns_by_terminal_identity(self):
        a = self._accept(self._external_v2(
            'aligned-A', 'A', terminals=('X', 'Y', 'Z'),
            costs=('0', '0', None, None, None, None, '0', '0')))
        b = self._accept(self._external_v2(
            'aligned-B', 'B', terminals=('Z', 'X', 'Y'),
            costs=(None, None, '0', '0', '0', '0', None, None)))
        self.close_sources()
        report, _ = sign_waiver_report(self.center, a, b, ('Z', 'X'), [])
        self.assertEqual((report.terminals, report.minimum_cost, report.pairs),
                         (('Z', 'X'), 0, DIFFERENT_PAIRS))

    def test_exact_integer_costs_survive_beyond_sqlite_and_decimal_limits(self):
        self._policies()
        huge = 10**4400 + 7
        rows = [grouped('huge', public('X'), public('Y'), 'different', huge)]
        a = self._issue_waiver('A', rows)
        b = self._issue_waiver('B', [])
        a_id, b_id = self._accept(a[0]), self._accept(b[0])
        validated = get_accepted_package(self.center, a_id)
        # The unsatisfiable X!=Y observation is charged in the equal states only.
        self.assertEqual(validated.costs_for(()), (huge, 0, 0, huge))
        self.assertEqual(validated.costs_for(('G',)), (0, 0, 0, 0))
        self.close_sources()
        ordinary, _ = sign_waiver_report(self.center, a_id, b_id, ['X', 'Y'], [])
        waived, receipt = sign_waiver_report(self.center, a_id, b_id, ['X', 'Y'], ['G'])
        self.assertTrue(ordinary.minimum_cost == 0)
        self.assertTrue(waived.minimum_cost == 0)
        export = json.loads(read_report(self.center, receipt.report_id, 'export'))
        self.assertEqual(export['minimum_cost'], '0')

    def _external_v2(self, package_id, station, *, terminals, costs, trial='T', stations=('A', 'B')):
        return {
            'version': 2,
            'package_id': package_id,
            'source': {'trial_id': trial, 'station_id': station, 'revision': 0},
            'catalog': {'trial_id': trial, 'stations': list(stations), 'terminals': list(terminals)},
            'policy': {'groups': ['G'], 'approved_combinations': [[], ['G']]},
            'conditions': {'encoding': 'waiver-lex-costs', 'tables': [
                {'combination': [], 'costs': list(costs)},
                {'combination': ['G'], 'costs': list(costs)},
            ]},
        }
