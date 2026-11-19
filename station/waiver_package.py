from dataclasses import asdict, dataclass
from decimal import Decimal
import hashlib
import json

from evidence.terminals import PublicCatalog
from evidence.waiver_policy import WaiverPolicy
from station.audit import AuditedRevision
from station.package import PackageProvenance
from station.waiver_analysis import WAIVER_CONDITIONS_ENCODING, WaiverAnalysis


@dataclass(frozen=True)
class WaiverStationPackage:
    package_id: str
    source: PackageProvenance
    catalog: PublicCatalog
    policy: WaiverPolicy
    analysis: WaiverAnalysis


def _policy_fields(policy: WaiverPolicy) -> dict:
    return {
        'groups': list(policy.groups),
        'approved_combinations': [list(combination) for combination in policy.approved_combinations],
    }


def _conditions_fields(analysis: WaiverAnalysis) -> dict:
    return {
        'encoding': WAIVER_CONDITIONS_ENCODING,
        'tables': [
            {
                'combination': list(table.combination),
                'costs': [None if cost is None else str(Decimal(cost)) for cost in table.costs],
            }
            for table in analysis.tables
        ],
    }


def business_fields(source: PackageProvenance, catalog: PublicCatalog,
                    policy: WaiverPolicy, analysis: WaiverAnalysis) -> dict:
    return {
        'version': 2,
        'source': asdict(source),
        'catalog': asdict(catalog),
        'policy': _policy_fields(policy),
        'conditions': _conditions_fields(analysis),
    }


def _encode(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(',', ':'))


def freeze_waiver_package(audited: AuditedRevision, policy: WaiverPolicy,
                          analysis: WaiverAnalysis, issue_number: int) -> WaiverStationPackage:
    source = PackageProvenance(audited.catalog.trial_id, audited.station_id, audited.revision)
    identity_seed = _encode((issue_number, business_fields(source, audited.catalog, policy, analysis)))
    package_id = 'pkg-' + hashlib.sha256(identity_seed.encode('utf-8')).hexdigest()
    return WaiverStationPackage(package_id, source, audited.catalog, policy, analysis)


def encode_waiver_package(package: WaiverStationPackage) -> str:
    fields = business_fields(package.source, package.catalog, package.policy, package.analysis)
    fields['package_id'] = package.package_id
    return _encode(fields)
