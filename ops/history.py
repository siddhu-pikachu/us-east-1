import os
import csv
import time
from typing import Dict

HIST_PATH = "data/history_tickets.csv"


def _ensure_file():
    """Ensure history CSV file exists with proper headers."""
    if not os.path.exists(HIST_PATH):
        os.makedirs(os.path.dirname(HIST_PATH), exist_ok=True)
        with open(HIST_PATH, "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(
                [
                    "ticket_id",
                    "tech",
                    "priority",
                    "type",
                    "tags",
                    "created",
                    "completed_minutes",
                    "eta_minutes",
                    "overran",
                    "had_followup",
                    "assignee_score",
                    "assigned_at",
                ]
            )


def calc_completed_minutes(start_ts: float, paused_seconds: float) -> float:
    """
    Calculate completed minutes from start timestamp and paused seconds.
    
    Args:
        start_ts: Start timestamp (time.time())
        paused_seconds: Total paused seconds
        
    Returns:
        Completed minutes (elapsed - paused)
    """
    import time
    return max(0.0, (time.time() - start_ts - paused_seconds) / 60.0)


def log_completion(
    ticket: Dict,
    tech: str,
    completed_minutes: float,
    eta_minutes: float,
    overran: bool,
    had_followup: bool,
    assignee_score: float,
):
    """
    Log a completed ticket to history CSV.
    
    Args:
        ticket: Ticket dict with ticket_id, priority, type, tags, created
        tech: Technician name who completed it
        completed_minutes: Actual time taken
        eta_minutes: Estimated time
        overran: Whether actual > estimated
        had_followup: Whether follow-up was needed
        assignee_score: Score that led to this assignment
    """
    _ensure_file()
    with open(HIST_PATH, "a", newline="") as f:
        w = csv.writer(f)
        w.writerow(
            [
                ticket.get("ticket_id", ""),
                tech,
                ticket.get("priority", ""),
                ticket.get("type", ""),
                "|".join(ticket.get("tags", []) or []),
                ticket.get("created", ""),
                round(completed_minutes, 1),
                int(eta_minutes),
                int(overran),
                int(had_followup),
                round(assignee_score, 3),
                int(time.time()),
            ]
        )

