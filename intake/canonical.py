from decimal import Decimal
import json

from intake.codec import DecodedPackage, canonical_content
from intake.validation import ValidatedWaiverPackage


def _cost_text(cost: int | None) -> str | None:
    return None if cost is None else str(Decimal(cost))


def canonical_waiver_content(validated: ValidatedWaiverPackage) -> str:
    """Rebuild the V2 wire in canonical form from the validated business content.

    Policy sets and condition tables are reordered together, so equivalent
    re-submissions differing only in whitespace, object key order, group array
    order or table position hash to the same content.
    """
    value = {
        'version': 2,
        'package_id': validated.package_id,
        'source': {
            'trial_id': validated.catalog.trial_id,
            'station_id': validated.station_id,
            'revision': validated.revision,
        },
        'catalog': {
            'trial_id': validated.catalog.trial_id,
            'stations': list(validated.catalog.stations),
            'terminals': list(validated.catalog.terminals),
        },
        'policy': {
            'groups': list(validated.policy.groups),
            'approved_combinations': [
                list(combination) for combination in validated.policy.approved_combinations
            ],
        },
        'conditions': {
            'encoding': 'waiver-lex-costs',
            'tables': [
                {
                    'combination': list(table.combination),
                    'costs': [_cost_text(cost) for cost in table.costs],
                }
                for table in validated.tables
            ],
        },
    }
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False)


def canonical_for(decoded: DecodedPackage, validated) -> str:
    if isinstance(validated, ValidatedWaiverPackage):
        return canonical_waiver_content(validated)
    return canonical_content(decoded)
