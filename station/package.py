from dataclasses import asdict, dataclass
from decimal import Decimal
import hashlib
import json

from evidence.terminals import PublicCatalog
from station.analysis import ConditionedAnalysis
from station.audit import AuditedRevision


@dataclass(frozen=True)
class PackageProvenance:
    trial_id: str
    station_id: str
    revision: int


@dataclass(frozen=True)
class StationPackage:
    package_id: str
    source: PackageProvenance
    catalog: PublicCatalog
    analysis: ConditionedAnalysis


def _business_fields(source: PackageProvenance, catalog: PublicCatalog,
                     analysis: ConditionedAnalysis) -> dict:
    return {
        'version': 1,
        'source': asdict(source),
        'catalog': asdict(catalog),
        'conditions': {
            'encoding': 'lex-costs',
            'costs': [None if cost is None else str(Decimal(cost)) for cost in analysis.costs],
        },
    }


def _encode(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(',', ':'))


def freeze_package(audited: AuditedRevision, issue_number: int) -> StationPackage:
    source = PackageProvenance(audited.catalog.trial_id, audited.station_id, audited.revision)
    identity_seed = _encode((issue_number, _business_fields(source, audited.catalog, audited.analysis)))
    package_id = 'pkg-' + hashlib.sha256(identity_seed.encode('utf-8')).hexdigest()
    return StationPackage(package_id, source, audited.catalog, audited.analysis)


def encode_package(package: StationPackage) -> str:
    fields = _business_fields(package.source, package.catalog, package.analysis)
    fields['package_id'] = package.package_id
    return _encode(fields)
