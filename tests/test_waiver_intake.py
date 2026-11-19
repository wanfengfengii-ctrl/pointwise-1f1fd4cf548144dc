import json
from copy import deepcopy

from intake.registry import accept_package, get_accepted_package
from intake.store import load_accepted_package
from intake.validation import ValidatedPackage, ValidatedWaiverPackage
from tests.fixtures import ShiftFixture


def _waiver_fields(package_id, station='A', *, groups=('G',), combinations=((), ('G',)),
                   tables=None, trial='T', stations=('A', 'B'), terminals=('X', 'Y'), revision=0):
    if tables is None:
        tables = [{'combination': list(combo), 'costs': ['0', '0', '0', '0']} for combo in combinations]
    return {
        'version': 2,
        'package_id': package_id,
        'source': {'trial_id': trial, 'station_id': station, 'revision': revision},
        'catalog': {'trial_id': trial, 'stations': list(stations), 'terminals': list(terminals)},
        'policy': {'groups': list(groups),
                   'approved_combinations': [list(combo) for combo in combinations]},
        'conditions': {'encoding': 'waiver-lex-costs', 'tables': tables},
    }


class WaiverIntakeTests(ShiftFixture):
    def test_equivalent_v2_replay_keeps_acceptance_number(self):
        fields = _waiver_fields('waiver-A', tables=[
            {'combination': [], 'costs': ['3', '2', '2', '3']},
            {'combination': ['G'], 'costs': ['0', '2', '2', '0']},
        ])
        first = accept_package(self.center, json.dumps(fields))
        reordered = deepcopy(fields)
        reordered['policy']['approved_combinations'] = [['G'], []]
        reordered['conditions']['tables'] = list(reversed(reordered['conditions']['tables']))
        replay = accept_package(self.center, json.dumps(reordered, indent=3, sort_keys=False).encode('utf-8'))
        self.assertEqual(replay, first)
        accepted = get_accepted_package(self.center, 'waiver-A')
        self.assertIsInstance(accepted, ValidatedWaiverPackage)
        self.assertEqual(accepted.version, 2)
        self.assertEqual(accepted.policy.groups, ('G',))
        self.assertEqual(accepted.costs_for(('G',)), (0, 2, 2, 0))
        self.assertEqual(accepted.costs, (3, 2, 2, 3))

    def test_same_identifier_with_different_content_is_rejected(self):
        fields = _waiver_fields('waiver-conflict')
        accept_package(self.center, json.dumps(fields))
        altered = deepcopy(fields)
        altered['conditions']['tables'][0]['costs'][0] = '9'
        with self.assertRaisesRegex(ValueError, 'different content'):
            accept_package(self.center, json.dumps(altered))

    def test_v1_and_v2_packages_coexist(self):
        v1 = {
            'version': 1, 'package_id': 'plain-A',
            'source': {'trial_id': 'T', 'station_id': 'A', 'revision': 0},
            'catalog': {'trial_id': 'T', 'stations': ['A', 'B'], 'terminals': ['X', 'Y']},
            'conditions': {'encoding': 'lex-costs', 'costs': ['0', None, None, '0']},
        }
        accept_package(self.center, json.dumps(v1))
        accept_package(self.center, json.dumps(_waiver_fields('waiver-A')))
        self.assertIsInstance(get_accepted_package(self.center, 'plain-A'), ValidatedPackage)
        self.assertIsInstance(get_accepted_package(self.center, 'waiver-A'), ValidatedWaiverPackage)

    def test_invalid_v2_payloads_are_rejected_without_side_effects(self):
        baseline = _waiver_fields('baseline-A')
        accept_package(self.center, json.dumps(baseline))
        good_tables = [
            {'combination': [], 'costs': ['3', '2', '2', '3']},
            {'combination': ['G'], 'costs': ['0', '2', '2', '0']},
        ]
        candidates = []
        # Wrong top-level field set and bad version marker.
        missing = deepcopy(baseline); missing['package_id'] = 'c1'; del missing['policy']
        candidates.append(missing)
        bad_version = deepcopy(baseline); bad_version['package_id'] = 'c2'; bad_version['version'] = 3
        candidates.append(bad_version)
        # Feasibility masks differ across combinations.
        mask = _waiver_fields('c3', tables=[
            {'combination': [], 'costs': ['0', '0', '0', '0']},
            {'combination': ['G'], 'costs': [None, '0', '0', '0']},
        ])
        candidates.append(mask)
        # Monotonicity violation: waiving G raises a cost.
        mono = _waiver_fields('c4', tables=[
            {'combination': [], 'costs': ['0', '0', '0', '0']},
            {'combination': ['G'], 'costs': ['5', '0', '0', '0']},
        ])
        candidates.append(mono)
        # Coverage gap: a combination has no table.
        coverage = _waiver_fields('c5', tables=[good_tables[0]])
        candidates.append(coverage)
        # Duplicate table for one combination.
        duplicate = _waiver_fields('c6', tables=[good_tables[0], deepcopy(good_tables[0])])
        candidates.append(duplicate)
        # Table references an undeclared combination.
        stray = deepcopy(baseline); stray['package_id'] = 'c7'
        stray['conditions']['tables'][1]['combination'] = ['H']
        candidates.append(stray)
        # Policy combination uses an undeclared group.
        undeclared = _waiver_fields('c8', groups=('G',), combinations=((), ('H',)))
        candidates.append(undeclared)
        # Non-decimal and malformed costs.
        bad_cost = _waiver_fields('c9', tables=[
            {'combination': [], 'costs': ['00', '0', '0', '0']},
            {'combination': ['G'], 'costs': ['0', '0', '0', '0']},
        ])
        candidates.append(bad_cost)
        for wire in candidates:
            with self.subTest(package_id=wire['package_id']):
                with self.assertRaises(ValueError):
                    accept_package(self.center, json.dumps(wire))
        self.assertEqual(load_accepted_package(self.center, 'baseline-A') is not None, True)
        for package_id in ('c1', 'c2', 'c3', 'c4', 'c5', 'c6', 'c7', 'c8', 'c9'):
            self.assertIsNone(get_accepted_package(self.center, package_id))
