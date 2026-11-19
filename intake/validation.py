from dataclasses import dataclass
from decimal import Decimal
import re

from evidence.terminals import PublicCatalog, build_catalog, require_identifier
from evidence.waiver_policy import WaiverPolicy, normalize_policy
from intake.codec import DecodedPackage
from station.waiver_analysis import WAIVER_CONDITIONS_ENCODING

_DECIMAL_COST = re.compile(r'0|[1-9][0-9]*')
_V1_FIELDS = {'version', 'package_id', 'source', 'catalog', 'conditions'}
_V2_FIELDS = _V1_FIELDS | {'policy'}


@dataclass(frozen=True)
class ValidatedPackage:
    package_id: str
    catalog: PublicCatalog
    station_id: str
    revision: int
    costs: tuple[int | None, ...]
    version: int = 1


@dataclass(frozen=True)
class WaiverConditionTable:
    combination: tuple[str, ...]
    costs: tuple[int | None, ...]


@dataclass(frozen=True)
class ValidatedWaiverPackage:
    package_id: str
    catalog: PublicCatalog
    station_id: str
    revision: int
    policy: WaiverPolicy
    tables: tuple[WaiverConditionTable, ...]
    version: int = 2

    @property
    def costs(self) -> tuple[int | None, ...]:
        """The empty-combination table is the ordinary V1 accounting."""
        return self.tables[0].costs if self.tables and self.tables[0].combination == () else self.costs_for(())

    def costs_for(self, combination: tuple[str, ...]) -> tuple[int | None, ...]:
        for table in self.tables:
            if table.combination == combination:
                return table.costs
        raise KeyError(combination)


def _object_with_fields(value: object, fields: set[str], label: str) -> dict:
    if not isinstance(value, dict) or value.keys() != fields:
        raise ValueError(f'invalid {label} fields')
    return value


def _decode_costs(costs: object, terminal_count: int) -> tuple[int | None, ...]:
    if not isinstance(costs, list) or len(costs) != 2**terminal_count:
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


def _validate_costs(value: object, terminal_count: int) -> tuple[int | None, ...]:
    fields = _object_with_fields(value, {'encoding', 'costs'}, 'conditions')
    if fields['encoding'] != 'lex-costs':
        raise ValueError('invalid conditions encoding')
    return _decode_costs(fields['costs'], terminal_count)


def _validate_source_and_catalog(fields: dict) -> tuple[PublicCatalog, str, int]:
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
    return catalog, station_id, revision


def _validate_v1(fields: dict) -> ValidatedPackage:
    package_id = require_identifier(fields['package_id'], 'package identifier')
    catalog, station_id, revision = _validate_source_and_catalog(fields)
    costs = _validate_costs(fields['conditions'], len(catalog.terminals))
    return ValidatedPackage(package_id, catalog, station_id, revision, costs)


def _validate_policy(value: object) -> WaiverPolicy:
    policy_fields = _object_with_fields(value, {'groups', 'approved_combinations'}, 'policy')
    groups = policy_fields['groups']
    combinations = policy_fields['approved_combinations']
    if not isinstance(groups, list) or not isinstance(combinations, list):
        raise ValueError('invalid waiver policy encoding')
    policy = normalize_policy(groups, combinations)
    if () not in policy.approved_combinations:
        raise ValueError('the empty combination must always be approved')
    return policy


def _validate_waiver_conditions(value: object, terminal_count: int,
                                policy: WaiverPolicy) -> tuple[WaiverConditionTable, ...]:
    fields = _object_with_fields(value, {'encoding', 'tables'}, 'conditions')
    if fields['encoding'] != WAIVER_CONDITIONS_ENCODING:
        raise ValueError('invalid waiver conditions encoding')
    raw_tables = fields['tables']
    if not isinstance(raw_tables, list) or len(raw_tables) != len(policy.approved_combinations):
        raise ValueError('waiver conditions must cover every approved combination exactly once')
    decoded = {}
    for raw_table in raw_tables:
        table_fields = _object_with_fields(raw_table, {'combination', 'costs'}, 'waiver table')
        combination_value = table_fields['combination']
        if not isinstance(combination_value, list):
            raise ValueError('a waiver combination must be an array')
        combination = tuple(combination_value)
        if combination not in policy.approved_combinations or combination in decoded:
            raise ValueError('waiver tables must match the approved combinations without duplicates')
        decoded[combination] = _decode_costs(table_fields['costs'], terminal_count)
    tables = tuple(
        WaiverConditionTable(combination, decoded[combination])
        for combination in policy.approved_combinations
    )
    _check_waiver_consistency(tables)
    return tables


def _check_waiver_consistency(tables: tuple[WaiverConditionTable, ...]) -> None:
    reference = tables[0]
    feasible = tuple(cost is not None for cost in reference.costs)
    by_combination = {table.combination: table for table in tables}
    for table in tables:
        mask = tuple(cost is not None for cost in table.costs)
        if mask != feasible:
            raise ValueError('hard feasibility must be identical for every combination')
    # Waiving more fees can never increase the minimum station cost.
    for table in tables:
        for combination, other in by_combination.items():
            if set(combination).issubset(set(table.combination)):
                for index, is_feasible in enumerate(feasible):
                    if is_feasible and other.costs[index] < table.costs[index]:
                        raise ValueError('waiver combination costs violate group monotonicity')


def _validate_v2(fields: dict) -> ValidatedWaiverPackage:
    package_id = require_identifier(fields['package_id'], 'package identifier')
    catalog, station_id, revision = _validate_source_and_catalog(fields)
    policy = _validate_policy(fields['policy'])
    tables = _validate_waiver_conditions(fields['conditions'], len(catalog.terminals), policy)
    return ValidatedWaiverPackage(package_id, catalog, station_id, revision, policy, tables)


def validate_package(decoded: DecodedPackage):
    value = decoded.value
    if not isinstance(value, dict):
        raise ValueError('invalid package fields')
    version = value.get('version')
    if type(version) is not int:
        raise ValueError('unsupported station package version')
    if version == 1:
        fields = _object_with_fields(value, _V1_FIELDS, 'package')
        return _validate_v1(fields)
    if version == 2:
        fields = _object_with_fields(value, _V2_FIELDS, 'package')
        return _validate_v2(fields)
    raise ValueError('unsupported station package version')
