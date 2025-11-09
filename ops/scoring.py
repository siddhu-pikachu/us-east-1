from typing import Optional, Tuple

PRIO_COLOR = {"Critical": "#ef4444", "High": "#f59e0b", "Medium": "#22c55e", "Low": "#60a5fa"}


def prio_val(p):
    """Convert priority string to numeric value."""
    return {"Critical": 4, "High": 3, "Medium": 2, "Low": 1}.get(str(p).title(), 1)


def priority_value(p: str) -> int:
    """Convert priority string to numeric value (alias for prio_val)."""
    return prio_val(p)


def estimate_walk(prev_xy: Tuple[float, float], cur_xy: Tuple[float, float]) -> float:
    """Calculate Euclidean distance between two points."""
    return ((cur_xy[0] - prev_xy[0]) ** 2 + (cur_xy[1] - prev_xy[1]) ** 2) ** 0.5


def task_score(
    task: dict,
    technician: Optional[dict] = None,
    same_row_bonus: float = 0.6,
    walk_penalty: float = 0.8,
    cage_penalty: float = 1.0,
    prev_xy: Optional[Tuple[float, float]] = None,
) -> float:
    """
    Calculate task priority score.

    score = 2*impact + 1.5*priority + 1.2*redundancy_risk
            - walk_penalty*(estimated_walk/100.0)
            - cage_penalty*door_crossings
            + 0.7*skill_match + same_row_bonus*same_row

    Missing fields default to conservative values.
    Returns float (higher is better).
    """
    impact = task.get("impact", 2)  # 1..4
    prio = priority_value(task.get("priority"))
    risk = task.get("redundancy_risk", 1)  # 0..2
    skill = task.get("skill_match", 1.0)  # 0..1
    same_row = 1.0 if task.get("same_row", False) else 0.0

    est_walk = 0.0
    if prev_xy and task.get("x") is not None and task.get("y") is not None:
        x, y = task["x"], task["y"]
        est_walk = estimate_walk(prev_xy, (x, y))

    door_cross = task.get("door_crossings", 0)

    score = (
        2 * impact
        + 1.5 * prio
        + 1.2 * risk
        - walk_penalty * (est_walk / 100.0)
        - cage_penalty * door_cross
        + 0.7 * skill
        + same_row_bonus * same_row
    )

    return float(score)


def compute_score(row, start=(800, 860)):
    """
    Compute task score from row data.
    Simplified scoring for Top-N ranking.
    """
    try:
        x, y = float(row.get("x", 0)), float(row.get("y", 0))
        walk = ((x - start[0]) ** 2 + (y - start[1]) ** 2) ** 0.5
    except Exception:
        walk = 0.0

    impact = row.get("impact", 2)
    risk = row.get("redundancy_risk", 1)
    same_row = 1.0 if row.get("same_row", False) else 0.0

    return 2 * impact + 1.5 * prio_val(row.get("priority")) + 1.2 * risk - 0.8 * (walk / 100.0) + 0.6 * same_row

