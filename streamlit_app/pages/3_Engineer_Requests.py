"""
My Requests page for Engineers.

Shows tickets created by the logged-in engineer with predicted finish times.
"""

import streamlit as st
import sys
import pandas as pd
from pathlib import Path
from datetime import datetime, timedelta

# Add parent directory to path for imports
_root = Path(__file__).parent.parent.parent.resolve()
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

from lib import data_access as da
from auth.session import gate
from auth.login import get_auth_user
from ops.live import build_live_df
from ops.runlock import get_runstate

st.set_page_config(page_title="Ticket Request", layout="wide")

# Hide unauthorized pages from sidebar
from streamlit_app.lib.sidebar import hide_unauthorized_pages
hide_unauthorized_pages()

# Role gate
gate(["engineer"])

auth_user = get_auth_user()

st.title("📋 My Requests")
st.markdown(f"Tickets created by **{auth_user}**")

# Load tickets
tickets = da.load_tickets()
assignment = st.session_state.get("assignment", {})
runstate = get_runstate(st)
one_ip = st.session_state.get("one_in_progress", {})

# Filter to tickets created by this engineer
# Check both created_by and reporter fields
# Also check for "engineer" as fallback for backwards compatibility
if tickets.empty or "created_by" not in tickets.columns:
    engineer_tickets = pd.DataFrame()
else:
    # Handle NaN values in created_by
    created_by_clean = tickets["created_by"].fillna("").astype(str)
    reporter_clean = tickets.get("reporter", pd.Series([""] * len(tickets))).fillna("").astype(str)
    
    engineer_tickets = tickets[
        (created_by_clean.str.lower() == auth_user.lower()) |
        (reporter_clean.str.lower() == auth_user.lower()) |
        (created_by_clean.str.lower() == "engineer")  # Fallback for old tickets
    ].copy()

if len(engineer_tickets) == 0:
    st.info("No tickets found. Create tickets using the 'Create Ticket' page.")
    st.stop()

# Build live_df for these tickets
live_df = build_live_df(engineer_tickets, assignment, runstate, one_ip)

# Calculate predicted finish times
def calculate_predicted_finish(row, now: datetime) -> datetime:
    """Calculate predicted finish time for a ticket."""
    status = row.get("status_view", row.get("status", "queued")).lower()
    eta_minutes = float(row.get("estimated_minutes", 30))
    
    if status == "done":
        # Already done - use completion time if available
        return now  # Or could use actual completion time
    
    elif status == "in-progress":
        # In progress - calculate remaining time
        # Check if there's an active run
        ticket_id = row.get("ticket_id")
        tech_name = assignment.get(ticket_id)
        
        if tech_name and runstate:
            active_run = runstate.get_active(tech_name)
            if active_run and active_run.ticket_id == ticket_id:
                # Calculate elapsed time
                from ops.history import calc_completed_minutes
                elapsed = calc_completed_minutes(active_run.started_ts, active_run.paused_seconds)
                remaining = max(0, eta_minutes - elapsed)
                return now + timedelta(minutes=remaining)
        
        # In progress but no active run data - use full ETA
        return now + timedelta(minutes=eta_minutes)
    
    else:
        # Queued - estimate wait time + ETA
        # Simple estimate: average wait time based on current load
        # For demo: assume 15-30 min wait + ETA
        wait_minutes = 20  # Could be calculated from assignment load
        return now + timedelta(minutes=wait_minutes + eta_minutes)

now = datetime.now()
live_df["predicted_finish"] = live_df.apply(
    lambda row: calculate_predicted_finish(row, now), axis=1
)

# Display table
st.markdown("### Ticket Status")

# Filter options
col1, col2 = st.columns(2)
with col1:
    status_filter = st.multiselect(
        "Filter by Status",
        ["queued", "in-progress", "done"],
        default=["queued", "in-progress"]
    )
with col2:
    priority_filter = st.multiselect(
        "Filter by Priority",
        ["Low", "Medium", "High", "Critical"],
        default=["Low", "Medium", "High", "Critical"]
    )

# Apply filters
filtered_df = live_df[
    (live_df["status_view"].str.lower().isin([s.lower() for s in status_filter])) &
    (live_df["priority"].isin(priority_filter))
].copy()

# Sort by predicted finish time
filtered_df = filtered_df.sort_values("predicted_finish")

# Display
if len(filtered_df) == 0:
    st.info("No tickets match the selected filters.")
else:
    # Format display columns
    display_df = filtered_df[[
        "ticket_id", "summary", "priority", "status_view", 
        "assigned_to", "predicted_finish"
    ]].copy()
    
    # Format predicted finish time
    display_df["predicted_finish"] = display_df["predicted_finish"].apply(
        lambda dt: dt.strftime("%Y-%m-%d %H:%M") if isinstance(dt, datetime) else "N/A"
    )
    
    # Rename columns for display
    display_df.columns = [
        "Ticket ID", "Summary", "Priority", "Status",
        "Assigned Technician", "Predicted Finish Time"
    ]
    
    st.dataframe(
        display_df,
        use_container_width=True,
        hide_index=True
    )
    
    # Summary stats
    st.markdown("---")
    col_stat1, col_stat2, col_stat3 = st.columns(3)
    with col_stat1:
        st.metric("Total Requests", len(engineer_tickets))
    with col_stat2:
        # Use status_view column (not the renamed "Status" column)
        in_progress = len(filtered_df[filtered_df["status_view"].str.lower() == "in-progress"])
        st.metric("In Progress", in_progress)
    with col_stat3:
        # Use status_view column (not the renamed "Status" column)
        done = len(filtered_df[filtered_df["status_view"].str.lower() == "done"])
        st.metric("Completed", done)

