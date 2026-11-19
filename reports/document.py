from dataclasses import asdict, dataclass
from decimal import Decimal


@dataclass(frozen=True)
class ReportSource:
    package_id: str
    trial_id: str
    station_id: str
    revision: int


@dataclass(frozen=True)
class ReportSnapshot:
    trial_id: str
    terminals: tuple[str, str]
    minimum_cost: int
    pairs: tuple[tuple[int, int], ...]
    sources: tuple[ReportSource, ReportSource]
    policy: dict | None = None
    waived_groups: tuple[str, ...] | None = None


def build_report_snapshot(trial_id: str, terminals: tuple[str, str], minimum_cost: int,
                          pairs: tuple[tuple[int, int], ...],
                          sources: tuple[ReportSource, ReportSource],
                          policy: dict | None = None,
                          waived_groups: tuple[str, ...] | None = None) -> ReportSnapshot:
    first, second = terminals
    left, right = sources
    fixed_pairs = tuple((a, b) for a, b in pairs)
    return ReportSnapshot(
        trial_id, (first, second), minimum_cost, fixed_pairs, (left, right), policy, waived_groups,
    )


def snapshot_fields(report: ReportSnapshot) -> dict:
    fields = {
        'trial_id': report.trial_id,
        'terminals': list(report.terminals),
        'minimum_cost': str(Decimal(report.minimum_cost)),
        'pairs': [list(pair) for pair in report.pairs],
        'sources': [asdict(source) for source in report.sources],
    }
    if report.policy is not None:
        fields['policy'] = {
            'groups': list(report.policy['groups']),
            'approved_combinations': [list(combination) for combination in report.policy['approved_combinations']],
        }
        fields['waived_groups'] = list(report.waived_groups)
    return fields


def snapshot_from_fields(fields: dict) -> ReportSnapshot:
    first, second = fields['terminals']
    left, right = fields['sources']
    pairs = tuple((a, b) for a, b in fields['pairs'])
    policy = fields.get('policy')
    if policy is not None:
        policy = {
            'groups': tuple(policy['groups']),
            'approved_combinations': tuple(
                tuple(combination) for combination in policy['approved_combinations']
            ),
        }
    waived_groups = None if 'waived_groups' not in fields else tuple(fields['waived_groups'])
    return ReportSnapshot(
        fields['trial_id'], (first, second), int(Decimal(fields['minimum_cost'])), pairs,
        (ReportSource(**left), ReportSource(**right)), policy, waived_groups,
    )
