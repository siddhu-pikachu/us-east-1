from typing import Dict


def task_score(
    impact: float,
    priority: float,
    skill_match: float,
    walk_time: float,
    door_penalty: float,
    same_row: float,
    outside_window: float,
) -> float:
    return (
        2.0 * impact
        + 1.5 * priority
        + 0.7 * skill_match
        - 0.8 * walk_time
        - 0.5 * door_penalty
        + 0.6 * same_row
        - 0.9 * outside_window
    )


def normalize(x: float) -> float:
    return max(0.0, min(1.0, x))

