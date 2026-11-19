from dataclasses import dataclass

from review.alignment import AlignedPackages
from review.joint_cost import JointMinimum
from review.selection import ReviewSelection


@dataclass(frozen=True)
class ReviewConclusion:
    selection: ReviewSelection
    terminals: tuple[str, str]
    minimum_cost: int
    pairs: tuple[tuple[int, int], ...]


def build_conclusion(aligned: AlignedPackages, minimum: JointMinimum) -> ReviewConclusion:
    first, second = aligned.requested_coordinates
    pairs = {(state[first], state[second]) for state in minimum.states}
    return ReviewConclusion(aligned.selection, aligned.requested, minimum.cost, tuple(sorted(pairs)))
