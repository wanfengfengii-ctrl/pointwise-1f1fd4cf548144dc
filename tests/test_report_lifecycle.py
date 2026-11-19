import json
import sqlite3

from evidence.observations import EvidenceChange
from evidence.revision_store import initialize_evidence_store
from evidence.revisions import read_revision, revise_evidence
from evidence.trials import open_trial
from intake.registry import accept_package, get_accepted_package
from intake.store import initialize_intake_store, load_accepted_package
from reports.read import read_report
from reports.register import initialize_report_store, load_publish_receipt
from review.request import sign_report
from station.issue import initialize_issue_store, issue_package, read_issued_package
from tests.fixtures import (
    DIFFERENT_PAIRS, SAME_PAIRS, ShiftFixture, hard, install_commit_block,
    linked_rows, local, public, remove_commit_block, row_count, soft,
)


class ReportLifecycleTests(ShiftFixture):
    def test_real_commit_failure_rolls_back_report_and_receipt(self):
        a = self.issue('A', linked_rows())
        b = self.issue('B', [soft('oppose', public('X'), public('Y'))])
        ids = self.receive(a, b)
        self.close_sources()
        install_commit_block(self.center, 'publish_receipts')
        with self.assertRaisesRegex(sqlite3.IntegrityError, 'FOREIGN KEY'):
            sign_report(self.center, *ids, ('X', 'Y'))
        self.assertFalse(self.center.in_transaction)
        self.reopen_center()
        self.assert_report_counts(0, 0)
        self.assertEqual(row_count(self.center, 'fixture_pending'), 0)
        self.assertIsNone(read_report(self.center, 1))
        self.assertIsNone(load_publish_receipt(self.center, 1))
        for package_id in ids:
            self.assertIsNotNone(get_accepted_package(self.center, package_id))
        remove_commit_block(self.center)
        report, receipt = sign_report(self.center, *ids, ('X', 'Y'))
        self.reopen_center()
        self.assert_report_counts(1, 1)
        self.assertEqual((report.minimum_cost, report.pairs), (1, SAME_PAIRS))
        self.assertEqual(read_report(self.center, receipt.report_id), report)
        self.assertEqual(load_publish_receipt(self.center, receipt.report_id), receipt)

    def test_correction_reopen_and_export_keep_old_report_and_provenance(self):
        a = self.issue('A', linked_rows())
        b = self.issue('B', [soft('oppose', public('X'), public('Y'))])
        a_id, b_id = self.receive(a, b)
        self.close_sources()
        old, old_receipt = sign_report(self.center, a_id, b_id, ('Y', 'X'))
        self.assertEqual((old.minimum_cost, old.pairs, old.terminals), (1, SAME_PAIRS, ('Y', 'X')))
        with_a = self.connect_station('A')
        change = EvidenceChange('replace', 'wire-y', hard('wire-y', local('u'), public('Y'), 'different'))
        corrected = revise_evidence(with_a, 'T', 'A', a[1].revision, [change])
        new_wire, new_issue = issue_package(with_a, 'T', 'A', corrected.revision)
        self.assertEqual(read_issued_package(with_a, a_id), a)
        with_a.close()
        self.reopen_center()
        new_id = accept_package(self.center, new_wire).package_id
        new, new_receipt = sign_report(self.center, new_id, b_id, ('Y', 'X'))
        self.assertEqual((new.minimum_cost, new.pairs), (0, DIFFERENT_PAIRS))
        self.assertEqual((new.sources[0].package_id, new.sources[0].revision), (new_issue.package_id, 2))
        self.assertEqual(new.sources[1], old.sources[1])
        self.assertNotEqual(new_receipt.report_id, old_receipt.report_id)
        self.reopen_center()
        self.assertEqual(read_report(self.center, old_receipt.report_id), old)
        self.assertEqual(read_report(self.center, new_receipt.report_id), new)
        exported = json.loads(read_report(self.center, old_receipt.report_id, 'export'))
        self.assertEqual(exported, {
            'report_id': old_receipt.report_id, 'trial_id': 'T', 'terminals': ['Y', 'X'],
            'minimum_cost': '1', 'pairs': [[0, 0], [1, 1]],
            'sources': [
                {'package_id': a_id, 'trial_id': 'T', 'station_id': 'A', 'revision': 1},
                {'package_id': b_id, 'trial_id': 'T', 'station_id': 'B', 'revision': 1},
            ],
        })
        self.assertEqual(self.center.execute('SELECT report_id FROM report_exports').fetchall(), [(old_receipt.report_id,)])
        self.assert_report_counts(2, 2)

    def test_reinitialize_keeps_user_corrections_packages_and_reports(self):
        db = self.sources['A']
        base = self.record('A', linked_rows())
        change = EvidenceChange('replace', 'wire-y', hard('wire-y', local('u'), public('Y'), 'different'))
        corrected = revise_evidence(db, 'T', 'A', base.revision, [change])
        issued = issue_package(db, 'T', 'A', corrected.revision)
        right = self.issue('B')
        a, b = self.receive(issued, right)
        accepted = load_accepted_package(self.center, a)
        report, receipt = sign_report(self.center, a, b, ('X', 'Y'))
        initialize_evidence_store(db)
        initialize_issue_store(db)
        open_trial(db, 'T', ('A', 'B'), ('X', 'Y'))
        self.assertEqual(read_revision(db, 'T', 'A', corrected.revision), corrected)
        self.assertEqual(read_issued_package(db, a), issued)
        self.close_sources()
        initialize_intake_store(self.center)
        initialize_report_store(self.center)
        self.reopen_center()
        self.assertEqual(load_accepted_package(self.center, a), accepted)
        self.assertEqual(read_report(self.center, receipt.report_id), report)
        self.assertEqual(load_publish_receipt(self.center, receipt.report_id), receipt)
        later, _ = sign_report(self.center, a, b, ('X', 'Y'))
        self.assertEqual((later.minimum_cost, later.pairs), (0, DIFFERENT_PAIRS))

    def test_missing_report_read_and_export_do_not_create_success_records(self):
        self.assertIsNone(read_report(self.center, 999))
        self.assertIsNone(read_report(self.center, 999, 'export'))
        self.assertIsNone(load_publish_receipt(self.center, 999))
        self.assertEqual(row_count(self.center, 'report_exports'), 0)
        with self.assertRaises(ValueError):
            read_report(self.center, 999, 'other-mode')
        self.assert_report_counts(0, 0)
