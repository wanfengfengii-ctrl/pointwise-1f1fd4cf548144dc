import sqlite3

from evidence.observations import EvidenceChange
from evidence.revision_store import initialize_evidence_store
from evidence.revisions import read_revision, revise_evidence
from evidence.trials import open_trial
from intake.codec import decode_package
from intake.validation import validate_package
from station.audit import audit_revision
from station.issue import initialize_issue_store, issue_package, read_issued_package
from tests.fixtures import (
    ShiftFixture, hard, install_commit_block, linked_rows, local, public,
    remove_commit_block, row_count, soft,
)


class StationDayTests(ShiftFixture):
    def test_issue_selected_revision_after_correction(self):
        db = self.sources['A']
        first = self.record('A', linked_rows())
        old_wire, old_receipt = issue_package(db, 'T', 'A', first.revision)
        corrected = hard('wire-y', local('u'), public('Y'), 'different')
        second = revise_evidence(db, 'T', 'A', first.revision, [EvidenceChange('replace', 'wire-y', corrected)])
        self.assertEqual(second.parent_revision, first.revision)
        new_wire, new_receipt = issue_package(db, 'T', 'A', second.revision)
        reissued_wire, reissued_receipt = issue_package(db, 'T', 'A', first.revision)
        self.assertEqual((old_receipt.revision, new_receipt.revision, reissued_receipt.revision), (1, 2, 1))
        self.assertEqual(read_issued_package(db, old_receipt.package_id), (old_wire, old_receipt))
        self.assertNotEqual(old_receipt.package_id, reissued_receipt.package_id)
        for wire, expected in (
            (old_wire, (0, None, None, 0)),
            (new_wire, (None, 0, 0, None)),
            (reissued_wire, (0, None, None, 0)),
        ):
            self.assertEqual(validate_package(decode_package(wire)).costs, expected)
            self.assertNotIn('wire-y', wire)
            self.assertNotIn('"u"', wire)
        self.assertEqual(read_revision(db, 'T', 'A', first.revision), first)

    def test_open_retry_keeps_revisions_and_rejects_other_parameters(self):
        db = self.sources['A']
        first = self.record('A', linked_rows())
        initialize_evidence_store(db)
        initialize_issue_store(db)
        catalog = open_trial(db, 'T', ['A', 'B'], ['X', 'Y'])
        self.assertEqual(catalog.terminals, ('X', 'Y'))
        self.assertEqual(read_revision(db, 'T', 'A', 0).observations, ())
        self.assertEqual(read_revision(db, 'T', 'B', 0).observations, ())
        self.assertEqual(read_revision(db, 'T', 'A', first.revision), first)
        for trial, stations, terminals in (
            ('T', ('A', 'B'), ('Y', 'X')),
            ('T2', ('A', 'A'), ('X',)),
            ('T2', ('A', 'B'), ('X', 'X')),
            ('T2', ('A', 'B'), ()),
            ('bad trial', ('A', 'B'), ('X',)),
        ):
            with self.subTest(trial=trial, stations=stations, terminals=terminals):
                with self.assertRaises(ValueError):
                    open_trial(db, trial, stations, terminals)
        self.assertEqual(row_count(db, 'trials'), 1)
        self.assertEqual(row_count(db, 'station_revisions'), 3)

    def test_bad_batch_preserves_entire_base_and_revision_chain(self):
        db = self.sources['A']
        base = self.record('A', linked_rows())
        change = EvidenceChange('replace', 'wire-y', hard('wire-y', local('u'), public('Y'), 'different'))
        bad = EvidenceChange('add', 'bad', soft('bad', public('X'), public('Y'), weight=0))
        with self.assertRaises(ValueError):
            revise_evidence(db, 'T', 'A', base.revision, [change, bad])
        self.assertEqual(read_revision(db, 'T', 'A', base.revision), base)
        self.assertEqual(row_count(db, 'station_revisions'), 3)
        self.assertEqual(audit_revision(db, 'T', 'A', base.revision).analysis.cost_for((0, 0)), 0)
        self.assertIsNone(audit_revision(db, 'T', 'A', base.revision).analysis.cost_for((0, 1)))
        corrected = revise_evidence(db, 'T', 'A', base.revision, [change])
        self.assertEqual((corrected.parent_revision, corrected.revision), (1, 2))

    def test_revision_and_endpoint_scope_and_evidence_limits(self):
        db = self.sources['A']
        with self.assertRaises(KeyError):
            revise_evidence(db, 'T', 'A', 8, [EvidenceChange('remove', 'absent')])
        for rows in (
            [hard('x', local('u', 'B'), public('Y'))],
            [hard('x', public('missing'), public('Y'))],
            [soft('x', public('X'), public('Y'), weight=True)],
            [hard(f'f{i}', local(f'u{i}'), public('Y')) for i in range(7)],
            [soft(f'r{i}', public('X'), public('Y')) for i in range(25)],
        ):
            with self.subTest(records=len(rows), first=rows[0].record_id):
                with self.assertRaises(ValueError):
                    self.record('A', rows)
        with self.assertRaises(ValueError):
            revise_evidence(db, 'T', 'A', 0, [EvidenceChange('remove', 'absent')])
        self.assertEqual(row_count(db, 'station_revisions'), 2)
        first = self.record('A', linked_rows())
        removed = revise_evidence(db, 'T', 'A', first.revision, [EvidenceChange('remove', 'wire-y')])
        self.assertEqual(tuple(row.record_id for row in removed.observations), ('wire-x',))
        self.assertEqual(audit_revision(db, 'T', 'A', removed.revision).analysis.costs, (0, 0, 0, 0))

    def test_unknown_revision_and_failed_issue_create_no_records(self):
        db = self.sources['A']
        with self.assertRaises(KeyError):
            issue_package(db, 'T', 'A', 9)
        install_commit_block(db, 'issue_receipts')
        with self.assertRaisesRegex(sqlite3.IntegrityError, 'FOREIGN KEY'):
            issue_package(db, 'T', 'A', 0)
        self.assertFalse(db.in_transaction)
        db.close()
        reopened = self.connect_station('A')
        self.assertEqual(row_count(reopened, 'issued_packages'), 0)
        self.assertEqual(row_count(reopened, 'issue_receipts'), 0)
        self.assertEqual(row_count(reopened, 'fixture_pending'), 0)
        remove_commit_block(reopened)
        wire, receipt = issue_package(reopened, 'T', 'A', 0)
        self.assertEqual(read_issued_package(reopened, receipt.package_id), (wire, receipt))
        self.assertEqual(row_count(reopened, 'issued_packages'), 1)
        self.assertEqual(row_count(reopened, 'issue_receipts'), 1)
