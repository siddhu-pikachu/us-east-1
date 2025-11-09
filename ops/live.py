import time
import pandas as pd
from typing import Dict, Optional


def build_live_df(
    base_df: pd.DataFrame,
    assignment: dict,
    runstate,
    one_in_progress_map: dict,
) -> pd.DataFrame:
    """
    Returns a DataFrame with synced fields:
      assignee, status_view, eta_minutes, started_ts, elapsed_min, remaining_min
    
    Args:
        base_df: Base tickets DataFrame
        assignment: ticket_id -> tech_name mapping
        runstate: RunState instance (or None)
        one_in_progress_map: tech_name -> ticket_id mapping for one-in-progress policy
        
    Returns:
        DataFrame with live status and timer fields
    """
    df = base_df.copy()

    # Assignee mapping
    df["assignee"] = df["ticket_id"].map(assignment) if assignment else df.get("assignee", None)

    # ETA
    df["eta_minutes"] = df.get("estimated_minutes", 15).astype(float)

    # CRITICAL: Always keep UI (status_view) in sync with CSV (status)
    # CSV is the source of truth - status_view should always match CSV status
    # The only exception is when there's an active run (handled below)
    # Ensure status is string and handle NaN
    df["status"] = df["status"].fillna("queued").astype(str)
    df["status_view"] = df["status"].str.lower()

    # NOTE: one_in_progress_map parameter is unused and kept for backward compatibility
    # We do NOT use it to change status_view - CSV status is always the source of truth
    # The only way status_view becomes "in-progress" is:
    # 1. CSV status is "in-progress", OR
    # 2. There's an active run (handled in the "Overlay active runs" section below)

    # Initialize timer fields
    now = time.time()
    df["started_ts"] = pd.NA
    df["elapsed_min"] = 0.0
    df["remaining_min"] = df["eta_minutes"].astype(float)

    # Overlay active runs with timers
    # CRITICAL: Only show tickets as "in-progress" if there's an actual active run
    # This ensures UI matches reality - if tech clicked "Start work", show it as in-progress
    if runstate and hasattr(runstate, "by_tech"):
        for tech, ar in runstate.by_tech.items():
            mask = df["ticket_id"] == ar.ticket_id
            if mask.any():
                # Only update status_view if there's an active run
                # This is the ONLY place where status_view can differ from CSV status
                df.loc[mask, "status_view"] = "in-progress"
                elapsed = max(
                    0.0, (now - ar.started_ts - ar.paused_seconds) / 60.0
                )
                df.loc[mask, "started_ts"] = ar.started_ts
                df.loc[mask, "elapsed_min"] = elapsed
                df.loc[mask, "remaining_min"] = (
                    df.loc[mask, "eta_minutes"].astype(float) - elapsed
                ).clip(lower=0.0)

    return df

