from datetime import datetime
from typing import List, Dict


def build_comment(
    run_id: str,
    ticket_id: str,
    steps: List[Dict],
    notes: str,
    distance_m: float | None = None,
) -> str:
    """Build formatted Jira comment from run evidence."""
    ts = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%SZ")
    lines = [f"[Run {run_id}] Ticket {ticket_id} completed at {ts}"]
    if distance_m is not None:
        lines.append(f"Route distance: {distance_m:.1f} m")
    lines.append("Steps:")
    for s in steps:
        mark = "✅" if s.get("done") else "⏺"
        when = s.get("ts", "")
        lines.append(f"- {mark} {s['id']} — {s['label']} {when}")
    if notes:
        lines.append(f"Notes: {notes}")
    return "\n".join(lines)

