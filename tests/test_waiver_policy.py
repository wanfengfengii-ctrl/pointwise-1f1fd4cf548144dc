from evidence.observations import EvidenceChange, Observation
from evidence.revisions import read_revision, revise_evidence
from evidence.trials import register_waiver_policy
from evidence.waiver_policy import normalize_policy
from tests.fixtures import ShiftFixture, public, soft


class WaiverPolicyTests(ShiftFixture):
    def test_registration_normalizes_and_is_idempotent(self):
        result = register_waiver_policy(self.sources['A'], 'T', ['H', 'G'], [['H'], ['G', 'H']])
        self.assertEqual(result, {
            'groups': ('G', 'H'),
            'approved_combinations': ((), ('G', 'H'), ('H',)),
        })
        # Same content with different order and the empty combo omitted returns the same value.
        again = register_waiver_policy(self.sources['A'], 'T', ['H', 'G'], [['H', 'G'], ['H']])
        self.assertEqual(again, result)
        # The other station library registers the same policy independently.
        self.assertEqual(register_waiver_policy(self.sources['B'], 'T', ['H', 'G'], [['H'], ['G', 'H']]), result)

    def test_empty_policy_always_keeps_the_empty_combination(self):
        self.assertEqual(normalize_policy([], []), type(normalize_policy([], []))((), ((),)))
        registered = register_waiver_policy(self.sources['A'], 'T', [], ())
        self.assertEqual(registered, {'groups': (), 'approved_combinations': ((),)})

    def test_policy_content_is_fixed_after_first_registration(self):
        register_waiver_policy(self.sources['A'], 'T', ['G'], [[], ['G']])
        with self.assertRaisesRegex(ValueError, 'fixed'):
            register_waiver_policy(self.sources['A'], 'T', ['G', 'H'], [[], ['G'], ['H'], ['G', 'H']])
        with self.assertRaisesRegex(ValueError, 'fixed'):
            register_waiver_policy(self.sources['A'], 'T', ['G'], [[]])

    def test_invalid_policy_structures_are_rejected(self):
        for groups, combinations in (
            (['G', 'G'], [[]]),
            (['G'], [['G'], ['G']]),
            (['G'], [['H']]),
            (['G'], [['G', 'G']]),
            ('G', [[]]),
            (['G'], ('G',)),
            (['bad group'], [[]]),
        ):
            with self.subTest(groups=groups, combinations=combinations):
                with self.assertRaises(ValueError):
                    register_waiver_policy(self.sources['A'], 'T', groups, combinations)

    def test_missing_trial_raises_key_error(self):
        with self.assertRaises(KeyError):
            register_waiver_policy(self.sources['A'], 'absent', ['G'], [[]])


class FeeGroupTests(ShiftFixture):
    def _policy(self, station='A'):
        register_waiver_policy(self.sources[station], 'T', ['G'], [[], ['G']])

    def test_only_soft_registered_evidence_can_be_grouped(self):
        self._policy()
        grouped = Observation('fee', public('X'), public('Y'), 'different', 'soft', 4, 'G')
        snapshot = self.record('A', [grouped])
        self.assertEqual(read_revision(self.sources['A'], 'T', 'A', snapshot.revision).observations[0].fee_group, 'G')
        for bad in (
            Observation('h', public('X'), public('Y'), 'same', 'hard', None, 'G'),
            Observation('s', public('X'), public('Y'), 'different', 'soft', 1, 'Z'),
        ):
            with self.subTest(bad=bad.record_id):
                with self.assertRaises(ValueError):
                    self.record('A', [bad])

    def test_group_requires_a_registered_policy(self):
        grouped = Observation('fee', public('X'), public('Y'), 'different', 'soft', 4, 'G')
        with self.assertRaisesRegex(ValueError, 'not declared'):
            self.record('A', [grouped])

    def test_invalid_batch_writes_nothing(self):
        self._policy()
        good = Observation('fee', public('X'), public('Y'), 'different', 'soft', 4, 'G')
        bad = Observation('h', public('X'), public('Y'), 'same', 'hard', None, 'G')
        with self.assertRaises(ValueError):
            revise_evidence(self.sources['A'], 'T', 'A', 0, [
                EvidenceChange('add', 'fee', good), EvidenceChange('add', 'h', bad),
            ])
        self.assertEqual(read_revision(self.sources['A'], 'T', 'A', 0).observations, ())

    def test_replace_controls_and_resets_grouping(self):
        self._policy()
        grouped = Observation('fee', public('X'), public('Y'), 'different', 'soft', 4, 'G')
        first = self.record('A', [grouped])
        plain = soft('fee', public('X'), public('Y'), 'different', 4)
        second = revise_evidence(
            self.sources['A'], 'T', 'A', first.revision,
            [EvidenceChange('replace', 'fee', plain)],
        )
        self.assertIsNone(second.observations[0].fee_group)
        # An unrelated add keeps the base revision's grouping.
        third = revise_evidence(
            self.sources['A'], 'T', 'A', first.revision,
            [EvidenceChange('add', 'other', soft('other', public('X'), public('Y'), weight=2))],
        )
        groups = {row.record_id: row.fee_group for row in third.observations}
        self.assertEqual(groups, {'fee': 'G', 'other': None})

    def test_declared_but_unused_group_remains_valid(self):
        self._policy('A')
        self._policy('B')
        # Station B never uses G, but the policy still registers and revisions stay ordinary.
        snapshot = self.record('B', [soft('plain', public('X'), public('Y'), weight=2)])
        self.assertIsNone(snapshot.observations[0].fee_group)
