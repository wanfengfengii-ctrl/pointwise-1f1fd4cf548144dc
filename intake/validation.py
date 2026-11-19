from dataclasses import dataclass
from decimal import Decimal
import re

from evidence.terminals import PublicCatalog, build_catalog, require_identifier
from intake.codec import DecodedPackage

_DECIMAL_COST = re.compile(r'0|[1-9][0-9]*')


@dataclass(frozen=True)
class ValidatedPackage:
    package_id: str
    catalog: PublicCatalog
    station_id: str
    revision: int
    costs: tuple[int | None, ...]


def _object_with_fields(value: object, fields: set[str], label: str) -> dict:
    if not isinstance(value, dict) or value.keys() != fields:
        raise ValueError(f'invalid {label} fields')
    return value


def _validate_costs(value: object, terminal_count: int) -> tuple[int | None, ...]:
    fields = _object_with_fields(value, {'encoding', 'costs'}, 'conditions')
    costs = fields['costs']
    if fields['encoding'] != 'lex-costs' or not isinstance(costs, list) or len(costs) != 2**terminal_count:
        raise ValueError('invalid complete public-state cost table')
    result = []
    for cost in costs:
        if cost is None:
            result.append(None)
        elif isinstance(cost, str) and _DECIMAL_COST.fullmatch(cost) is not None:
            result.append(int(Decimal(cost)))
        else:
            raise ValueError('invalid state cost')
    return tuple(result)


def validate_package(decoded: DecodedPackage) -> ValidatedPackage:
    fields = _object_with_fields(decoded.value, {'version', 'package_id', 'source', 'catalog', 'conditions'}, 'package')
    version = fields['version']
    if type(version) is not int or version != 1:
        raise ValueError('unsupported station package version')
    package_id = require_identifier(fields['package_id'], 'package identifier')
    source = _object_with_fields(fields['source'], {'trial_id', 'station_id', 'revision'}, 'source')
    catalog_fields = _object_with_fields(fields['catalog'], {'trial_id', 'stations', 'terminals'}, 'catalog')
    catalog = build_catalog(catalog_fields['trial_id'], catalog_fields['stations'], catalog_fields['terminals'])
    trial_id = require_identifier(source['trial_id'], 'source trial identifier')
    station_id = require_identifier(source['station_id'], 'source station identifier')
    revision = source['revision']
    if trial_id != catalog.trial_id or station_id not in catalog.stations:
        raise ValueError('package source disagrees with its trial catalog')
    if type(revision) is not int or not 0 <= revision < 2**63:
        raise ValueError('invalid package revision')
    costs = _validate_costs(fields['conditions'], len(catalog.terminals))
    return ValidatedPackage(package_id, catalog, station_id, revision, costs)
