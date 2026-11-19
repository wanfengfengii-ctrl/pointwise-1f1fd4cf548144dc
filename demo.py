from contextlib import closing
from dataclasses import replace
import json
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory

from evidence.observations import EvidenceChange, Observation
from evidence.revision_store import initialize_evidence_store
from evidence.revisions import revise_evidence
from evidence.terminals import EndpointRef
from evidence.trials import open_trial
from intake.registry import accept_package
from intake.store import initialize_intake_store
from reports.read import read_report
from reports.register import initialize_report_store, load_publish_receipt
from review.request import sign_report
from station.issue import initialize_issue_store, issue_package


def _endpoint(spec, station):
    scope, name = spec
    return EndpointRef(scope, name, station if scope == 'local' else None)


def _observation(spec, station):
    return Observation(
        spec['record_id'], _endpoint(spec['left'], station), _endpoint(spec['right'], station),
        spec['relation'], spec['kind'], spec.get('weight'),
    )


def _result(report):
    return {'minimum_cost': report.minimum_cost, 'pairs': [list(pair) for pair in report.pairs]}


def _prepare_station(path, sample, station):
    trial = sample['trial']
    rows = [_observation(spec, station) for spec in sample['observations'][station]]
    with closing(sqlite3.connect(path)) as db:
        initialize_evidence_store(db)
        initialize_issue_store(db)
        open_trial(db, trial, sample['stations'], sample['terminals'])
        changes = [EvidenceChange('add', row.record_id, row) for row in rows]
        original = revise_evidence(db, trial, station, 0, changes)
        return issue_package(db, trial, station, original.revision)


def _correct_station(path, sample, original):
    correction = sample['correction']
    station = correction['station']
    record_id = correction['record_id']
    spec = next(spec for spec in sample['observations'][station] if spec['record_id'] == record_id)
    corrected_row = replace(_observation(spec, station), relation=correction['relation'])
    change = EvidenceChange('replace', record_id, corrected_row)
    with closing(sqlite3.connect(path)) as db:
        initialize_evidence_store(db)
        initialize_issue_store(db)
        corrected = revise_evidence(db, sample['trial'], station, original.revision, [change])
        return issue_package(db, sample['trial'], station, corrected.revision)


def _initialize_center(db):
    initialize_intake_store(db)
    initialize_report_store(db)


def run_demo(sample, folder):
    first, second = sample['stations']
    paths = {station: folder / f'station-{station}.db' for station in sample['stations']}
    issued = {station: _prepare_station(paths[station], sample, station) for station in sample['stations']}
    center_path = folder / 'center.db'
    with closing(sqlite3.connect(center_path)) as center:
        _initialize_center(center)
        package_ids = {station: accept_package(center, wire).package_id for station, (wire, _) in issued.items()}
        old_report, old_receipt = sign_report(center, package_ids[first], package_ids[second], sample['request'])

    station = sample['correction']['station']
    new_wire, corrected_issue = _correct_station(paths[station], sample, issued[station][1])
    with closing(sqlite3.connect(center_path)) as center:
        _initialize_center(center)
        new_package_ids = dict(package_ids)
        new_package_ids[station] = accept_package(center, new_wire).package_id
        new_report, new_receipt = sign_report(center, new_package_ids[first], new_package_ids[second], sample['request'])
        saved = read_report(center, old_receipt.report_id)
        reprinted = json.loads(read_report(center, old_receipt.report_id, 'export'))
        persisted_receipt = load_publish_receipt(center, old_receipt.report_id)

    expected = sample['expected']['before']
    actual = _result(old_report)
    corrected = _result(new_report)
    expected_export = {
        **expected, 'terminals': sample['request'], 'revisions': [1, 1], 'original_package_ids': True,
    }
    actual_export = {
        'minimum_cost': int(reprinted['minimum_cost']), 'pairs': reprinted['pairs'],
        'terminals': reprinted['terminals'], 'revisions': [source['revision'] for source in reprinted['sources']],
        'original_package_ids': [source['package_id'] for source in reprinted['sources']] == [package_ids[first], package_ids[second]],
    }
    if actual != expected or actual_export != expected_export or saved != old_report or persisted_receipt != old_receipt:
        raise AssertionError((expected, actual, expected_export, actual_export))
    if corrected != sample['expected']['after']:
        raise AssertionError((sample['expected']['after'], corrected))
    matching_source = next(source for source in new_report.sources if source.station_id == station)
    if (new_receipt.report_id == old_receipt.report_id or matching_source.package_id != corrected_issue.package_id
            or matching_source.revision != 2 or reprinted['report_id'] != old_receipt.report_id):
        raise AssertionError('report provenance does not match the two frozen handoffs')
    scenario = {
        'case_id': 'v5',
        'input': {key: sample[key] for key in ('trial', 'stations', 'terminals', 'request', 'observations')},
        'expected': expected,
        'actual': actual,
        'downstream_expected': expected_export,
        'downstream_actual': actual_export,
        'code_paths': [
            'station/analysis.py', 'station/issue.py', 'intake/registry.py', 'review/joint_cost.py',
            'review/conclusions.py', 'reports/register.py', 'reports/export.py',
        ],
        'oracle': 'X=u and u=Y force equality. The independent weight-one check is violated on both equal pairs.',
    }
    print('POINTWISE_SCENARIO ' + json.dumps(scenario, sort_keys=True))
    print(json.dumps({
        'original_report': reprinted,
        'corrected_report': {'report_id': new_receipt.report_id, **corrected},
    }, sort_keys=True))


def main():
    path = Path(__file__).resolve().parent / 'examples' / 'shift.json'
    sample = json.loads(path.read_text(encoding='utf-8'))
    with TemporaryDirectory() as directory:
        run_demo(sample, Path(directory))
    from waiver_demo import run_waiver_demo
    with TemporaryDirectory() as directory:
        run_waiver_demo(Path(directory))


if __name__ == '__main__':
    main()
