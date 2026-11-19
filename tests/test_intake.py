from copy import deepcopy
import json

from intake.registry import accept_package, get_accepted_package
from intake.store import load_accepted_package
from tests.fixtures import ShiftFixture, external_fields, row_count


class IntakeTests(ShiftFixture):
    def test_exact_replay_returns_original_and_conflicting_content_is_rejected(self):
        fields = external_fields('fixed-A', 'A', ('0', None, None, '0'), revision=3)
        first = accept_package(self.center, json.dumps(fields))
        retry = accept_package(self.center, json.dumps(fields, indent=2, sort_keys=True).encode('utf-8'))
        self.assertEqual(retry, first)
        self.assertEqual(first.package_id, 'fixed-A')
        self.assertEqual(len(first.content_digest), 64)
        fields['conditions']['costs'] = [None, '0', '0', None]
        with self.assertRaisesRegex(ValueError, 'different content'):
            accept_package(self.center, json.dumps(fields))
        self.reopen_center()
        self.assertEqual(load_accepted_package(self.center, 'fixed-A'), first)
        fixed = get_accepted_package(self.center, 'fixed-A')
        self.assertEqual((fixed.revision, fixed.costs), (3, (0, None, None, 0)))
        self.assertEqual(row_count(self.center, 'accepted_packages'), 1)

    def test_invalid_payloads_preserve_existing_acceptance(self):
        baseline = external_fields('fixed-A', 'A', ('0', None, None, '0'))
        accepted = accept_package(self.center, json.dumps(baseline))
        variants = ['{', b'\xff', '{"version":1,"version":1}', '[]']
        for section, key, value in (
            (None, 'version', True),
            (None, 'version', 2),
            (None, 'package_id', ''),
            ('source', 'trial_id', 'other'),
            ('source', 'station_id', 'C'),
            ('source', 'revision', -1),
            ('source', 'revision', True),
            ('catalog', 'terminals', ['X', 'X']),
            ('catalog', 'terminals', [f'P{i}' for i in range(7)]),
            ('conditions', 'encoding', 'unknown'),
            ('conditions', 'costs', ['0']),
            ('conditions', 'costs', ['0', '0', '-1', '0']),
            ('conditions', 'costs', ['0', '0', '00', '0']),
            ('conditions', 'costs', ['0', '0', 0, '0']),
            ('conditions', 'costs', ['0', '0', True, '0']),
        ):
            altered = deepcopy(baseline)
            altered['package_id'] = 'candidate'
            if section is None:
                altered[key] = value
            else:
                altered[section][key] = value
            variants.append(json.dumps(altered))
        for wire in variants:
            with self.subTest(wire=wire):
                with self.assertRaises(ValueError):
                    accept_package(self.center, wire)
        self.assertEqual(load_accepted_package(self.center, 'fixed-A'), accepted)
        self.assertIsNone(get_accepted_package(self.center, 'candidate'))
        self.assertEqual(row_count(self.center, 'accepted_packages'), 1)
