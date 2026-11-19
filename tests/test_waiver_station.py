import json
import sqlite3

from evidence.observations import Observation
from evidence.trials import register_waiver_policy
from intake.codec import decode_package
from intake.validation import validate_package
from station.issue import issue_package, issue_waiver_package, read_issued_package
from station.waiver_analysis import WAIVER_CONDITIONS_ENCODING
from tests.fixtures import (
    ShiftFixture, install_commit_block, local, public, remove_commit_block, row_count, soft,
)


def grouped(record_id, left, right, relation='different', weight=1, group='G'):
    return Observation(record_id, left, right, relation, 'soft', weight, group)


class WaiverStationTests(ShiftFixture):
    def _policy(self, station='A', trial='T'):
        register_waiver_policy(self.sources[station], trial, ['G'], [[], ['G']])

    def test_v2_package_carries_policy_and_per_combination_tables(self):
        self._policy()
        rows = [
            soft('ordinary-A', public('X'), public('Y'), 'same', 2),
            grouped('fee-A', public('X'), public('Y'), 'different', 3),
        ]
        revision = self.record('A', rows).revision
        wire, receipt = issue_waiver_package(self.sources['A'], 'T', 'A', revision)
        parsed = json.loads(wire)
        self.assertEqual(parsed['version'], 2)
        self.assertEqual(set(parsed), {'version', 'package_id', 'source', 'catalog', 'policy', 'conditions'})
        self.assertEqual(parsed['policy'], {'groups': ['G'], 'approved_combinations': [[], ['G']]})
        self.assertEqual(parsed['conditions']['encoding'], WAIVER_CONDITIONS_ENCODING)
        combinations = [table['combination'] for table in parsed['conditions']['tables']]
        self.assertEqual(combinations, [[], ['G']])
        tables = {tuple(table['combination']): table['costs'] for table in parsed['conditions']['tables']}
        # Empty combination reproduces the ordinary V1 accounting; waiving G removes the fee.
        self.assertEqual(tables[()], ['3', '2', '2', '3'])
        self.assertEqual(tables[('G',)], ['0', '2', '2', '0'])
        self.assertEqual(read_issued_package(self.sources['A'], receipt.package_id), (wire, receipt))
        self.assertNotIn('fee-A', wire)
        self.assertNotIn('record_id', wire)

    def test_v1_issue_still_emits_version_one(self):
        self._policy()
        rows = [grouped('fee-A', public('X'), public('Y'), 'different', 3)]
        revision = self.record('A', rows).revision
        wire, receipt = issue_package(self.sources['A'], 'T', 'A', revision)
        parsed = json.loads(wire)
        self.assertEqual(parsed['version'], 1)
        self.assertNotIn('policy', parsed)
        validated = validate_package(decode_package(wire))
        self.assertEqual(validated.version, 1)
        self.assertEqual(validated.costs, (3, 0, 0, 3))

    def test_unknown_revision_and_missing_policy_raise_key_error(self):
        with self.assertRaises(KeyError):
            issue_waiver_package(self.sources['A'], 'T', 'A', 7)
        self._policy()
        self.sources['A'].execute(
            "INSERT INTO trials (trial_id, first_station, second_station, terminals) VALUES ('T2', 'A', 'B', '[\"X\"]')"
        )
        self.sources['A'].execute(
            "INSERT INTO station_revisions (trial_id, station_id, revision, parent_revision, observations) "
            "VALUES ('T2', 'A', 0, NULL, '[]')"
        )
        with self.assertRaises(KeyError):
            issue_waiver_package(self.sources['A'], 'T2', 'A', 0)

    def test_private_choice_recomputes_minimum_per_combination(self):
        self._policy()
        rows = [
            soft('ordinary-private', public('X'), local('u'), 'same', 2),
            grouped('fee-private', public('X'), local('u'), 'different', 3),
        ]
        revision = self.record('A', rows).revision
        wire, _ = issue_waiver_package(self.sources['A'], 'T', 'A', revision)
        tables = {tuple(t['combination']): t['costs'] for t in json.loads(wire)['conditions']['tables']}
        self.assertEqual(tables[()], ['2', '2', '2', '2'])
        self.assertEqual(tables[('G',)], ['0', '0', '0', '0'])

    def test_hard_feasibility_is_identical_in_every_combination(self):
        self._policy()
        from tests.fixtures import hard
        rows = [
            hard('pin', public('X'), local('u')),
            grouped('fee', local('u'), public('Y'), 'same', 3),
        ]
        revision = self.record('A', rows).revision
        wire, _ = issue_waiver_package(self.sources['A'], 'T', 'A', revision)
        tables = [t['costs'] for t in json.loads(wire)['conditions']['tables']]
        masks = [[cost is None for cost in table] for table in tables]
        self.assertEqual(masks[0], masks[1])

    def test_commit_failure_rolls_back_waiver_issue_and_retry_succeeds(self):
        self._policy()
        revision = self.record('A', [grouped('fee-A', public('X'), public('Y'))]).revision
        install_commit_block(self.sources['A'], 'issue_receipts')
        with self.assertRaises(sqlite3.IntegrityError):
            issue_waiver_package(self.sources['A'], 'T', 'A', revision)
        self.assertFalse(self.sources['A'].in_transaction)
        self.sources['A'].close()
        reopened = self.connect_station('A')
        self.assertEqual(row_count(reopened, 'issued_packages'), 0)
        self.assertEqual(row_count(reopened, 'issue_receipts'), 0)
        remove_commit_block(reopened)
        wire, receipt = issue_waiver_package(reopened, 'T', 'A', revision)
        self.assertEqual(read_issued_package(reopened, receipt.package_id), (wire, receipt))
