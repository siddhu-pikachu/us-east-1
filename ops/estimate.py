from typing import Dict

# Base minutes for each task type (adjusted for 10-60 min range, avg ~25 min)
BASE_MIN = {
    "recable_port": 25,  # walk 5 + recable 12 + verify 8
    "install_server": 45,  # unbox 8 + rack 15 + power/net 15 + post 7
    "swap_psu": 28,
    "reseat_blade": 22,
    "audit_label": 18,
    "recable": 25,
    "install": 45,
    "swap": 28,
    "reseat": 22,
    "audit": 18,
    "replace_sfp": 20,
}

# Priority modifiers (urgency compresses time slightly)
PRIO_SLACK = {"Critical": -2, "High": -1, "Medium": 0, "Low": 3}

# Rack complexity by row letter (farther rows may be slower)
RACK_COMPLEXITY = {"A": 0, "B": 1, "C": 2, "D": 3, "E": 4, "F": 5, "G": 6, "H": 7}


def estimate_minutes(t: Dict) -> int:
    """
    Estimate minutes for a ticket based on type, priority, and location.
    
    Args:
        t: Ticket dict with keys: type, priority, asset_id
        
    Returns:
        Estimated minutes (6-90 range)
    """
    task_type = str(t.get("type", "")).lower()
    
    # Find base time (try exact match, then partial match)
    base = BASE_MIN.get(task_type, 15)
    for key, val in BASE_MIN.items():
        if key in task_type:
            base = val
            break
    
    # Priority adjustment
    priority = str(t.get("priority", "Medium")).title()
    pr_adj = PRIO_SLACK.get(priority, 0)
    
    # Aisle complexity by first letter of asset_id (e.g., "C-08" -> row C)
    asset_id = str(t.get("asset_id", "A-01"))
    row_letter = asset_id[:1].upper() if asset_id else "A"
    aisle_adj = RACK_COMPLEXITY.get(row_letter, 0)
    
    # Calculate total
    minutes = max(10, int(base + pr_adj + aisle_adj))
    
    # Cap to range: 10..60 minutes (1 hour max)
    return max(10, min(60, minutes))

