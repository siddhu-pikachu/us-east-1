import streamlit as st
import pandas as pd
import sys
from pathlib import Path

# Add parent directory to path for imports
_root = Path(__file__).parent.parent.parent.resolve()
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

# Clear any cached modules to ensure fresh imports
if "auth" in sys.modules:
    del sys.modules["auth"]
if "auth.session" in sys.modules:
    del sys.modules["auth.session"]
if "ops.assign" in sys.modules:
    del sys.modules["ops.assign"]
if "ops.techs" in sys.modules:
    del sys.modules["ops.techs"]
if "ops" in sys.modules:
    del sys.modules["ops"]

from lib import data_access as da
from auth.session import gate
from auth.login import get_auth_user, normalize_username
from ops.assign import prio_val, hours_old, jaccard
from ops.techs import load_technicians
from ops.live import build_live_df
from ops.runlock import get_runstate
import pandas as pd

st.set_page_config(page_title="Technician Dashboard", layout="wide")

# Hide unauthorized pages from sidebar
from streamlit_app.lib.sidebar import hide_unauthorized_pages
hide_unauthorized_pages()

# Role gate - allow both technician and manager (manager sees all)
gate(["technician", "manager"])

# Get current user and role
from auth.session import get_current_role
current_role = get_current_role()
auth_user = get_auth_user()

# Determine page title and scope
if current_role == "technician":
    st.title("📋 My Tickets")
    # Technician sees only their own tickets
    tech_name_filter = auth_user  # Use logged-in username
    show_tech_selector = False
else:
    st.title("👥 Technicians")
    # Manager sees all technicians
    tech_name_filter = None
    show_tech_selector = True

assets = da.load_assets()
# Force reload from CSV (clear cache)
if "all_tickets_df" in st.session_state:
    del st.session_state["all_tickets_df"]
tickets = da.load_tickets()
techs_df = load_technicians()

# Build live tickets view
runstate = get_runstate(st)

# Clean up stale runs (older than 1 hour)
if runstate and hasattr(runstate, "cleanup_stale_runs"):
    cleaned = runstate.cleanup_stale_runs(max_age_seconds=3600)
    if cleaned > 0:
        # Clear one_in_progress if runs were cleaned
        if "one_in_progress" in st.session_state:
            st.session_state["one_in_progress"] = {}

# Build assignment from CSV (source of truth) or use session state as fallback
csv_assignment = {}
if "assigned_to" in tickets.columns:
    assigned_tickets = tickets[tickets["assigned_to"].notna() & (tickets["assigned_to"] != "")]
    csv_assignment = dict(zip(assigned_tickets["ticket_id"], assigned_tickets["assigned_to"]))

# Use CSV assignment as primary source, session state as fallback
assignment = csv_assignment if csv_assignment else st.session_state.get("assignment", {})
# Also update session state with CSV assignments for consistency
if csv_assignment:
    st.session_state["assignment"] = csv_assignment

# CRITICAL: Sync one_in_progress_map with CSV status on every page load
# CSV is the source of truth - if CSV has no "in-progress", clear the mapping
has_active_runs = runstate and hasattr(runstate, "by_tech") and runstate.by_tech
tickets_status = set(tickets["status"].str.lower().unique())

# Clear one_in_progress mapping if:
# 1. No active runs exist, AND
# 2. CSV has no "in-progress" status
if not has_active_runs and "in-progress" not in tickets_status:
    # CSV has no in-progress and no active runs - clear the mapping
    if "one_in_progress" in st.session_state:
        st.session_state["one_in_progress"] = {}

# CRITICAL: Only use one_in_progress if there are actual active runs
# We don't need it for display - status_view always matches CSV status
# The one_in_progress mapping is only useful for knowing which ticket each tech is working on
# when there's an active run, but build_live_df doesn't use it to change status_view
one_ip = {}
if has_active_runs:
    # Active runs exist - we can use the mapping for reference, but build_live_df
    # will determine status_view from CSV status and active runs only
    one_ip = st.session_state.get("one_in_progress", {})
# Otherwise, don't use mapping - status_view will match CSV status

live_df = build_live_df(tickets, assignment, runstate, one_ip)
st.session_state["live_tickets_df"] = live_df

st.sidebar.header("Filters")

# Status filter with "all" option
status_opts = ["all", "queued", "in-progress", "done"]
sel_status = st.sidebar.multiselect(
    "Status", status_opts, default=["queued", "in-progress"]
)
use_status = status_opts[1:] if "all" in sel_status else sel_status

# Technician filter - only show selector for managers
if show_tech_selector:
    tech_opts = ["all"] + sorted(techs_df["name"].astype(str).tolist())
    sel_tech = st.sidebar.selectbox("Technician", tech_opts, index=0)
    st.session_state["selected_technician"] = sel_tech
else:
    # Technician: use their own name, no selector
    # Try to get original name from CSV for matching
    original_name = st.session_state.get("auth_original_name", tech_name_filter)
    # Match against CSV names (case-insensitive)
    matching_techs = techs_df[techs_df["name"].str.lower().str.strip() == original_name.lower().strip()]
    if len(matching_techs) > 0:
        sel_tech = matching_techs.iloc[0]["name"]
    else:
        # Fallback to normalized name
        sel_tech = original_name
    st.session_state["selected_technician"] = sel_tech
    st.sidebar.info(f"👤 Viewing tickets for: **{sel_tech}**")

# Apply filters (use live_df)
filtered = live_df.copy()

# Status filter (use status_view for live sync)
if use_status:
    filtered = filtered[filtered["status_view"].str.lower().isin([s.lower() for s in use_status])]

# Assignment filter - build from CSV (source of truth) or use session state as fallback
# Build assignment dict from CSV assigned_to column
csv_assignment = {}
if "assigned_to" in tickets.columns:
    assigned_tickets = tickets[tickets["assigned_to"].notna() & (tickets["assigned_to"] != "")]
    csv_assignment = dict(zip(assigned_tickets["ticket_id"], assigned_tickets["assigned_to"]))

# Use CSV assignment as primary source, session state as fallback
asg = csv_assignment if csv_assignment else st.session_state.get("assignment", {})
# Also update session state with CSV assignments for consistency
if csv_assignment:
    st.session_state["assignment"] = csv_assignment

if sel_tech != "all":
    if not asg:
        st.warning("No assignments yet. Manager: run Auto-Assign.")
        filtered = filtered.iloc[0:0]  # Empty dataframe
    else:
        # Match tech name case-insensitively
        assigned_ticket_ids = [k for k, v in asg.items() if v and str(v).lower().strip() == sel_tech.lower().strip()]
        filtered = filtered[filtered["ticket_id"].isin(assigned_ticket_ids)]
        st.info(f"Showing {len(filtered)} tickets assigned to {sel_tech}")
else:
    if asg:
        st.info(f"Showing all {len(filtered)} tickets (no assignment filter)")

# One-in-progress is already handled in live_df via status_view
# No need to manually update status here

# Urgency-based sorting with tag matching
def urgency_score(row, tech_tags=None):
    """Calculate urgency score: higher = more urgent."""
    # Handle NaN/None values safely
    priority = row.get("priority", "Low")
    if priority is None or (isinstance(priority, float) and pd.isna(priority)):
        priority = "Low"
    pr = prio_val(priority)
    imp = row.get("impact", 2)
    if pd.isna(imp):
        imp = 2
    age_h = hours_old(row.get("created", ""))
    base_score = 3 * pr + 2 * imp + 0.06 * age_h
    
    # Add tag matching bonus if viewing specific tech
    if tech_tags is not None:
        ticket_tags = row.get("tags", [])
        tag_bonus = 0.7 * jaccard(ticket_tags, tech_tags)
        base_score += tag_bonus
    
    # Urgent first (priority dominates), then age lifts older tasks
    return -base_score

if not filtered.empty:
    # Get tech tags if viewing specific tech
    tech_tags = None
    if sel_tech != "all":
        tech_row = techs_df[techs_df["name"] == sel_tech]
        if not tech_row.empty:
            tech_tags = tech_row.iloc[0].get("tags", [])
    
    filtered["_urgency"] = filtered.apply(
        lambda r: urgency_score(r, tech_tags), axis=1
    )
    filtered = filtered.sort_values("_urgency", ascending=True)
    filtered = filtered.drop(columns=["_urgency"])

# Show assignment load info if viewing specific tech
load_state = st.session_state.get("assign_load_state", {})
if sel_tech != "all" and load_state and sel_tech in load_state:
    ls = load_state[sel_tech]
    assigned_minutes = ls.get("minutes", 0)
    capacity = ls.get("capacity", 240)
    utilization = (assigned_minutes / capacity * 100) if capacity > 0 else 0
    ticket_count = len([k for k, v in st.session_state.get("assignment", {}).items() if v == sel_tech])
    st.info(
        f"📊 Assigned {ticket_count} tickets · Est load: {assigned_minutes:.1f} min · Util: {utilization:.1f}%"
    )

st.write(f"{len(filtered)} tasks in view.")

# Reset index for 0-based numbering (use status_view for display)
view_df = filtered[["ticket_id", "summary", "asset_id", "priority", "deadline", "status_view"]].copy()
view_df = view_df.rename(columns={"status_view": "status"})  # Rename for display
view_df = view_df.reset_index(drop=True)
st.dataframe(view_df, use_container_width=True, hide_index=True)

st.info("Map & routing will be added next. This page is functional for listing/selection in MVP.")

# Add link to map page
st.markdown("---")
col1, col2 = st.columns([3, 1])
with col1:
    st.write("**Ready to optimize your route?**")
with col2:
    st.page_link("pages/2_Technician_Map.py", label="🗺️ Open Map & Route Optimizer →", icon="🗺️")

