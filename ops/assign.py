from typing import List, Dict, Tuple
import math
from datetime import datetime, timezone
import pandas as pd


def prio_val(p: str) -> int:
    """Convert priority string to numeric value."""
    # Handle NaN, None, or non-string values
    if p is None:
        return 1
    # Check for NaN (float NaN)
    if isinstance(p, float) and math.isnan(p):
        return 1
    # Convert to string and title case
    p_str = str(p).strip() if p else ""
    return {"Critical": 4, "High": 3, "Medium": 2, "Low": 1}.get(
        p_str.title(), 1
    )


def hours_old(iso: str) -> float:
    """Calculate hours since ticket creation. Returns 0.0 if invalid."""
    if not iso:
        return 0.0
    try:
        # Handle ISO format with or without Z
        iso_clean = iso.replace("Z", "+00:00")
        dt = datetime.fromisoformat(iso_clean)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        now = datetime.now(timezone.utc)
        hours = (now - dt).total_seconds() / 3600.0
        return max(0.0, hours)
    except Exception:
        return 0.0


def dist(a: Tuple[float, float], b: Tuple[float, float]) -> float:
    """Calculate Euclidean distance between two points."""
    return math.hypot((a[0] - b[0]), (a[1] - b[1]))


def jaccard(a: List[str], b: List[str]) -> float:
    """Calculate Jaccard similarity between two tag lists."""
    A = set([x.lower() for x in (a or [])])
    B = set([x.lower() for x in (b or [])])
    if not A and not B:
        return 0.0
    intersection = len(A & B)
    union = len(A | B)
    return intersection / max(1, union)


def skill_match(skill_level: int, priority: str) -> float:
    """
    Calculate skill match score: prefer high skill for high priority.
    Returns 0..1.5
    """
    need = {"Critical": 5, "High": 4, "Medium": 3, "Low": 2}.get(
        (priority or "Medium").title(), 3
    )
    # Rough sigmoid-ish: skill above (need-2) gets bonus
    diff = skill_level - (need - 2)
    return min(1.5, max(0.0, diff / 3.0))




def capable(ticket: Dict, tech: Dict, policy) -> bool:
    """
    Check if a technician is capable of handling a ticket based on skill and tag thresholds.
    
    Args:
        ticket: Ticket dict with priority and tags
        tech: Tech dict with skill_level and tags
        policy: AssignmentPolicy instance
        
    Returns:
        True if tech meets skill and tag requirements
    """
    from ops.policy import AssignmentPolicy
    
    if not isinstance(policy, AssignmentPolicy):
        policy = AssignmentPolicy()  # fallback to default
    
    # Skill thresholds by priority
    need = {
        "Critical": policy.min_skill_for_critical,
        "High": policy.min_skill_for_high,
        "Medium": policy.min_skill_for_medium,
        "Low": policy.min_skill_for_low,
    }.get(str(ticket.get("priority", "Medium")).title(), policy.min_skill_for_medium)
    
    if int(tech.get("skill_level", 3)) < need:
        return False
    
    # Tag similarity check
    sim = jaccard(ticket.get("tags", []), tech.get("tags", []))
    return sim >= policy.min_tag_jaccard


def lpt_size(ticket: Dict, policy) -> float:
    """
    Calculate LPT "size" for a ticket (processing time + priority/impact/age weights).
    
    Args:
        ticket: Ticket dict
        policy: AssignmentPolicy instance
        
    Returns:
        Size value for LPT ordering (larger = process first)
    """
    from ops.policy import AssignmentPolicy
    
    if not isinstance(policy, AssignmentPolicy):
        policy = AssignmentPolicy()  # fallback to default
    
    eta = float(ticket.get("estimated_minutes", 15))
    pr = prio_val(ticket.get("priority"))
    imp = float(ticket.get("impact", 2))
    age = hours_old(ticket.get("created", ""))
    
    return (
        eta
        + policy.prio_weight * pr
        + policy.impact_weight * imp
        + policy.age_per_hour_weight * age
    )


def auto_assign_balanced(
    tickets: List[Dict], techs: List[Dict], policy=None
) -> Tuple[Dict[str, str], Dict[str, Dict]]:
    """
    LPT-based assignment with capability constraints:
      1) Sort tickets by decreasing lpt_size.
      2) For each ticket, pick the feasible tech with the *lowest current load* (minutes),
         respecting high-ticket quota & soft overtime cap; if none feasible under caps, relax caps.
    
    Args:
        tickets: List of ticket dicts
        techs: List of tech dicts
        policy: AssignmentPolicy instance (or None for default)
        
    Returns:
        Tuple of (assignment_map, load_state)
        - assignment_map: ticket_id -> tech_name
        - load_state: tech_name -> {minutes, capacity, high_count, ...}
    """
    from ops.policy import AssignmentPolicy, DEFAULT_POLICY
    
    if policy is None:
        policy = DEFAULT_POLICY
    
    # Tech state
    state = {
        t["name"]: {
            "minutes": 0.0,
            "capacity": float(t.get("capacity_min", 240)),
            "skill_level": int(t.get("skill_level", 3)),
            "tags": [s.lower() for s in t.get("tags", [])],
            "team": t.get("team", ""),
            "high_count": 0,
        }
        for t in techs
    }
    
    # Pre-sort tickets by LPT size (largest first)
    sorted_tix = sorted(tickets, key=lambda x: lpt_size(x, policy), reverse=True)
    
    asg: Dict[str, str] = {}
    
    def feasible(name: str, tk: Dict, enforce_caps: bool) -> bool:
        """Check if tech is feasible for ticket."""
        st = state[name]
        
        # Capability gate
        tech_dict = {
            "skill_level": st["skill_level"],
            "tags": st["tags"],
        }
        if not capable(tk, tech_dict, policy):
            return False
        
        # Soft quotas/caps (optional on 2nd pass)
        if enforce_caps:
            if (
                str(tk.get("priority", "")).title() in ("Critical", "High")
                and st["high_count"] >= policy.max_high_per_tech
            ):
                return False
            if st["minutes"] > policy.allow_overtime_factor * st["capacity"]:
                return False
        
        return True
    
    for tk in sorted_tix:
        # Two-pass: try with caps, then relax if needed
        picked = None
        for enforce in (True, False):
            candidates = [n for n in state.keys() if feasible(n, tk, enforce)]
            if candidates:
                # Choose least-loaded tech
                picked = min(candidates, key=lambda n: state[n]["minutes"])
                break
        
        if picked is None:
            # Final fallback: ignore capability (shouldn't happen if data ok)
            picked = min(state.keys(), key=lambda n: state[n]["minutes"])
        
        asg[tk["ticket_id"]] = picked
        
        # Update load
        state[picked]["minutes"] += float(tk.get("estimated_minutes", 15))
        
        if str(tk.get("priority", "")).title() in ("Critical", "High"):
            state[picked]["high_count"] += 1
    
    return asg, state


def urgency_score(t: dict, tech_tags: List[str] = None, tech_skill: int = 3) -> float:
    """Calculate urgency score: higher is more urgent.
    
    Args:
        t: Ticket dict
        tech_tags: Technician tags for tag matching
        tech_skill: Technician skill level for skill matching
    """
    pr = prio_val(t.get("priority", "Low"))
    imp = t.get("impact", 2)
    age_h = hours_old(t.get("created", ""))
    
    base_score = 3 * pr + 2 * imp + 0.05 * age_h
    
    # Add skill and tag matching bonuses
    if tech_tags is not None:
        ticket_tags = t.get("tags", [])
        tag_bonus = 1.2 * jaccard(ticket_tags, tech_tags)
        base_score += tag_bonus
    
    skl_bonus = 0.8 * skill_match(tech_skill, t.get("priority", "Medium"))
    base_score += skl_bonus
    
    return base_score


def choose_in_progress(
    assign_map: Dict[str, str], tickets_df: pd.DataFrame, techs_list: List[Dict] = None
) -> Dict[str, str]:
    """
    Returns tech_name -> ticket_id for the ONE ticket that should be 'in-progress' per tech.
    Chooses the most urgent ticket for each technician, considering skills and tags.
    
    Args:
        assign_map: ticket_id -> tech_name mapping
        tickets_df: DataFrame with ticket data including tags
        techs_list: List of tech dicts with tags and skill_level
    """
    by_tech: Dict[str, str] = {}
    
    # Build tech lookup
    tech_lookup = {}
    if techs_list:
        for tech in techs_list:
            tech_lookup[tech["name"]] = {
                "tags": [s.lower() for s in tech.get("tags", [])],
                "skill_level": int(tech.get("skill_level", 3)),
            }

    # Subset assigned tickets
    asg_df = tickets_df[tickets_df["ticket_id"].isin(assign_map.keys())].copy()
    asg_df["assignee"] = asg_df["ticket_id"].map(assign_map)

    for name, grp in asg_df.groupby("assignee"):
        # Get tech info for tag/skill matching
        tech_info = tech_lookup.get(name, {})
        tech_tags = tech_info.get("tags", [])
        tech_skill = tech_info.get("skill_level", 3)
        
        # Convert rows to dicts and find most urgent
        best_ticket = None
        best_score = -1.0

        for _, row in grp.iterrows():
            ticket_dict = row.to_dict()
            score = urgency_score(ticket_dict, tech_tags, tech_skill)
            if score > best_score:
                best_score = score
                best_ticket = row["ticket_id"]

        if best_ticket:
            by_tech[name] = best_ticket

    return by_tech

