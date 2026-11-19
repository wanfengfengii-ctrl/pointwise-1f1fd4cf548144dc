from dataclasses import dataclass

from evidence.terminals import require_identifier
from review.selection import ReviewSelection


@dataclass(frozen=True)
class AlignedPackages:
    selection: ReviewSelection
    terminals: tuple[str, ...]
    right_coordinates: tuple[int, ...]
    requested: tuple[str, str]
    requested_coordinates: tuple[int, int]


def align_packages(selection: ReviewSelection, requested: tuple[str, ...] | list[str]) -> AlignedPackages:
    terminals = selection.left.catalog.terminals
    right_terminals = selection.right.catalog.terminals
    if set(terminals) != set(right_terminals):
        raise ValueError('packages disagree on the public terminals')
    if not isinstance(requested, (tuple, list)) or len(requested) != 2:
        raise ValueError('an ordered pair of public terminals is required')
    first, second = (require_identifier(name, 'requested terminal') for name in requested)
    coordinates = {name: index for index, name in enumerate(terminals)}
    if first not in coordinates or second not in coordinates:
        raise ValueError('requested terminal is outside the public catalog')
    return AlignedPackages(
        selection, terminals, tuple(coordinates[name] for name in right_terminals),
        (first, second), (coordinates[first], coordinates[second]),
    )


def align_public_state(aligned: AlignedPackages,
                       state: tuple[int, ...]) -> tuple[tuple[int, ...], tuple[int, ...]]:
    if len(state) != len(aligned.terminals):
        raise ValueError('a complete public state is required')
    return state, tuple(state[index] for index in aligned.right_coordinates)
