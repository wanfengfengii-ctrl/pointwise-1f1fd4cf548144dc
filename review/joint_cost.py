from dataclasses import dataclass
from itertools import product

from evidence.terminals import public_state_index
from review.alignment import AlignedPackages, align_public_state


@dataclass(frozen=True)
class JointMinimum:
    cost: int
    states: tuple[tuple[int, ...], ...]


def find_joint_minimum(aligned: AlignedPackages) -> JointMinimum | None:
    left_costs = aligned.selection.left.costs
    right_costs = aligned.selection.right.costs
    best_cost = None
    best_states = []
    for state in product((0, 1), repeat=len(aligned.terminals)):
        left_state, right_state = align_public_state(aligned, state)
        left_cost = left_costs[public_state_index(left_state)]
        right_cost = right_costs[public_state_index(right_state)]
        if left_cost is None or right_cost is None:
            continue
        total = left_cost + right_cost
        if best_cost is None or total < best_cost:
            best_cost = total
            best_states = [state]
        elif total == best_cost:
            best_states.append(state)
    if best_cost is None:
        return None
    return JointMinimum(best_cost, tuple(best_states))
