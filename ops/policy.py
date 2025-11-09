from dataclasses import dataclass


@dataclass
class AssignmentPolicy:
    """Policy configuration for ticket assignment."""

    # Capability thresholds
    min_skill_for_critical: int = 4
    min_skill_for_high: int = 3
    min_skill_for_medium: int = 2
    min_skill_for_low: int = 1
    min_tag_jaccard: float = 0.2  # 0..1; minimum tag similarity to count as "capable"
    allow_overtime_factor: float = 1.15  # cap minutes as soft limit (e.g., 115% of capacity)

    # Prioritization into LPT "size"
    prio_weight: float = 6.0  # priority contribution to size
    impact_weight: float = 3.0
    age_per_hour_weight: float = 0.04  # small bump per hour old (prevents starvation)

    # Quotas (soft)
    max_high_per_tech: int = 2


DEFAULT_POLICY = AssignmentPolicy()

BALANCED_PRESET = AssignmentPolicy()  # good default

SPEED_PRESET = AssignmentPolicy(prio_weight=7.5)  # pushes criticals harder

FAIR_PRESET = AssignmentPolicy(max_high_per_tech=1)  # spreads highs more

