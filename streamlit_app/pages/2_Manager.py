import streamlit as st
import pandas as pd
import sys
from pathlib import Path

# Add parent directory to path for imports
_root = Path(__file__).parent.parent.parent.resolve()
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

# Clear any cached modules
if "auth" in sys.modules:
    del sys.modules["auth"]
if "auth.session" in sys.modules:
    del sys.modules["auth.session"]
if "ops.techs" in sys.modules:
    del sys.modules["ops.techs"]
if "ops.assign" in sys.modules:
    del sys.modules["ops.assign"]
if "ops" in sys.modules:
    del sys.modules["ops"]
if "streamlit_app.lib.jira_adapter" in sys.modules:
    del sys.modules["streamlit_app.lib.jira_adapter"]
if "lib.jira_adapter" in sys.modules:
    del sys.modules["lib.jira_adapter"]
if "streamlit_app.lib" in sys.modules:
    del sys.modules["streamlit_app.lib"]
if "lib" in sys.modules:
    del sys.modules["lib"]

from lib import data_access as da
from auth.session import gate
from ops.assign import auto_assign_balanced, choose_in_progress
from ops.techs import load_technicians, techs_as_list
from ops.policy import (
    AssignmentPolicy,
    DEFAULT_POLICY,
    BALANCED_PRESET,
    SPEED_PRESET,
    FAIR_PRESET,
)
from ops.live import build_live_df
from ops.runlock import get_runstate
from streamlit_app.lib.jira_adapter import assign_issue, load_tech_jira_mapping, get_client
from streamlit_app.lib.config import settings
import pandas as pd

st.set_page_config(page_title="Manager Dashboard", layout="wide")

# Hide unauthorized pages from sidebar
from streamlit_app.lib.sidebar import hide_unauthorized_pages
hide_unauthorized_pages()

# Role gate
gate(["manager"])

st.title("Manager Dashboard (MVP)")

# Force reload from CSV (clear cache)
if "all_tickets_df" in st.session_state:
    del st.session_state["all_tickets_df"]
tickets = da.load_tickets()
techs_df = load_technicians()
inventory_df = da.load_inventory()

# Load technicians from CSV
TECHS = techs_as_list(techs_df)

# Build live tickets view
runstate = get_runstate(st)

# CRITICAL: Clean up stale runs FIRST (older than 1 hour)
# This prevents stale active runs from showing tickets as in-progress
# Must happen BEFORE checking has_active_runs
if runstate and hasattr(runstate, "cleanup_stale_runs"):
    cleaned = runstate.cleanup_stale_runs(max_age_seconds=3600)
    if cleaned > 0:
        # Clear one_in_progress if runs were cleaned
        if "one_in_progress" in st.session_state:
            st.session_state["one_in_progress"] = {}

assignment = st.session_state.get("assignment", {})

# CRITICAL: Sync one_in_progress_map with CSV status on every page load
# CSV is the source of truth - if CSV has no "in-progress", clear the mapping
# Check for active runs AFTER cleanup
has_active_runs = runstate and hasattr(runstate, "by_tech") and bool(runstate.by_tech)
tickets_status = set(tickets["status"].str.lower().unique())

# CRITICAL: Clear one_in_progress mapping if:
# 1. No active runs exist, AND
# 2. CSV has no "in-progress" status
# This ensures stale mappings don't persist across page loads
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

# CRITICAL: Always rebuild live_df from fresh tickets DataFrame
# This ensures status_view reflects CSV status, not stale state
live_df = build_live_df(tickets, assignment, runstate, one_ip)
st.session_state["live_tickets_df"] = live_df

# Policy configuration
st.sidebar.header("⚙️ Assignment Policy")

policy_preset = st.sidebar.radio(
    "Preset",
    ["Balanced", "Speed", "Fair"],
    index=0,
    help="Balanced: Default settings\nSpeed: Prioritize critical tickets\nFair: Spread high-priority tickets more evenly",
)

if policy_preset == "Balanced":
    policy = BALANCED_PRESET
elif policy_preset == "Speed":
    policy = SPEED_PRESET
else:
    policy = FAIR_PRESET

with st.sidebar.expander("Advanced Policy Settings"):
    min_tag_jaccard = st.slider(
        "Min Tag Similarity",
        0.0,
        1.0,
        policy.min_tag_jaccard,
        0.05,
        help="Minimum Jaccard similarity for tag matching (0.0 = any match, 1.0 = exact match)",
    )
    max_high_per_tech = st.slider(
        "Max High-Priority per Tech",
        1,
        5,
        policy.max_high_per_tech,
        help="Maximum Critical/High tickets per technician (soft limit)",
    )
    allow_overtime_factor = st.slider(
        "Overtime Factor",
        1.0,
        1.5,
        policy.allow_overtime_factor,
        0.05,
        help="Allow assignment up to this factor of capacity (1.0 = no overtime, 1.15 = 115%)",
    )
    
    # Update policy with custom values
    policy = AssignmentPolicy(
        min_tag_jaccard=min_tag_jaccard,
        max_high_per_tech=max_high_per_tech,
        allow_overtime_factor=allow_overtime_factor,
        min_skill_for_critical=policy.min_skill_for_critical,
        min_skill_for_high=policy.min_skill_for_high,
        min_skill_for_medium=policy.min_skill_for_medium,
        min_skill_for_low=policy.min_skill_for_low,
        prio_weight=policy.prio_weight,
        impact_weight=policy.impact_weight,
        age_per_hour_weight=policy.age_per_hour_weight,
    )
    
    st.caption("Skill thresholds:")
    st.caption(f"  Critical: {policy.min_skill_for_critical}, High: {policy.min_skill_for_high}")
    st.caption(f"  Medium: {policy.min_skill_for_medium}, Low: {policy.min_skill_for_low}")

# Ensure tickets have coordinates
if "x" not in tickets.columns or "y" not in tickets.columns:
    tickets = tickets.merge(
        inventory_df[["asset_id", "x", "y"]], on="asset_id", how="left"
    )

# Auto-Assignment section
st.subheader("📋 Auto-Assignment")

# Auto-Assign Agent toggle
col_toggle1, col_toggle2 = st.columns([2, 1])
with col_toggle1:
    auto_assign_agent_enabled = st.toggle(
        "🤖 Auto-Assign Agent",
        value=st.session_state.get("auto_assign_agent_enabled", False),
        help="When enabled, automatically re-assigns tickets to optimize workload balance"
    )
    st.session_state["auto_assign_agent_enabled"] = auto_assign_agent_enabled

with col_toggle2:
    if auto_assign_agent_enabled:
        last_assign_ts = st.session_state.get("auto_assign_last_run")
        if last_assign_ts:
            from datetime import datetime
            try:
                last_dt = datetime.fromisoformat(last_assign_ts) if isinstance(last_assign_ts, str) else last_assign_ts
                time_str = last_dt.strftime("%H:%M:%S")
                st.caption(f"🟢 Agent active · last assignment {time_str}")
            except:
                st.caption("🟢 Agent active")
        else:
            st.caption("🟢 Agent active")
    else:
        st.caption("⚪ Agent inactive")

# Auto-run agent if enabled
if auto_assign_agent_enabled:
    # Check if we should run (every N seconds or on rerun)
    import time
    current_time = time.time()
    last_run_time = st.session_state.get("auto_assign_last_run_time", 0)
    run_interval = 30  # Run every 30 seconds
    
    if current_time - last_run_time >= run_interval:
        # Run auto-assign
        assignable = live_df[
            live_df["status_view"].isin(["queued", "in-progress"])
        ].copy()
        
        if not assignable.empty:
            # Build ticket dicts
            ticket_dicts = []
            for _, row in assignable.iterrows():
                ticket_dicts.append({
                    "ticket_id": row["ticket_id"],
                    "x": row.get("x"),
                    "y": row.get("y"),
                    "priority": row.get("priority", "Medium"),
                    "impact": row.get("impact", 2),
                    "redundancy_risk": row.get("redundancy_risk", 0),
                    "same_row": False,
                    "estimated_minutes": row.get("estimated_minutes", 30),
                    "created": row.get("created", ""),
                    "tags": row.get("tags", []),
                    "type": row.get("type", ""),
                    "asset_id": row.get("asset_id", ""),
                })
            
            # Get current assignment
            current_assignment = st.session_state.get("assignment", {})
            
            # Run auto-assign
            from ops.assign import auto_assign_balanced
            techs_list = techs_df.to_dict("records")
            new_assignment, _ = auto_assign_balanced(ticket_dicts, techs_list, policy)
            
            # Only update if it improves balance or has unassigned tasks
            if new_assignment != current_assignment:
                # Check if new assignment is better (has fewer unassigned or better balance)
                unassigned_old = len(ticket_dicts) - len(current_assignment)
                unassigned_new = len(ticket_dicts) - len(new_assignment)
                
                if unassigned_new < unassigned_old or unassigned_new == 0:
                    st.session_state["assignment"] = new_assignment
                    st.session_state["auto_assign_last_run"] = datetime.now().isoformat()
                    st.session_state["auto_assign_last_run_time"] = current_time
                    
                    # CRITICAL: Save assignments to CSV so all portals see them
                    tickets = da.load_tickets()
                    for ticket_id, tech_name in new_assignment.items():
                        # Find the ticket and update assigned_to
                        mask = tickets["ticket_id"] == ticket_id
                        if mask.any():
                            # Use original tech name from CSV if available, otherwise use normalized name
                            matching_techs = techs_df[techs_df["name"].str.lower().str.strip() == tech_name.lower().strip()]
                            if len(matching_techs) > 0:
                                csv_tech_name = matching_techs.iloc[0]["name"]
                            else:
                                csv_tech_name = tech_name
                            tickets.loc[mask, "assigned_to"] = csv_tech_name
                    
                    # Save updated tickets to CSV
                    da.save_tickets(tickets)
                    
                    # Clear cache to force reload
                    if "all_tickets_df" in st.session_state:
                        del st.session_state["all_tickets_df"]
                    
                    st.rerun()

# Get queued and in-progress tickets for assignment (use live_df)
assignable = live_df[
    live_df["status_view"].isin(["queued", "in-progress"])
].copy()

if st.button("🔄 Auto-Assign Tickets (Balanced)", type="primary"):
    if assignable.empty:
        st.warning("No assignable tickets (queued or in-progress).")
    else:
        # Build ticket dicts with created timestamp, tags
        ticket_dicts = []
        for _, row in assignable.iterrows():
            ticket_dicts.append(
                {
                    "ticket_id": row["ticket_id"],
                    "x": row.get("x"),
                    "y": row.get("y"),
                    "priority": row.get("priority", "Medium"),
                    "impact": row.get("impact", 2),
                    "redundancy_risk": row.get("redundancy_risk", 0),
                    "same_row": False,  # Could be computed if needed
                    "estimated_minutes": row.get("estimated_minutes", 30),
                    "created": row.get("created", ""),  # Include created timestamp for aging
                    "tags": row.get("tags", []),  # Include tags for matching
                    "type": row.get("type", ""),  # Include type for estimation
                    "asset_id": row.get("asset_id", ""),  # Include asset_id for estimation
                }
            )

        # Run balanced auto-assignment
        assignment, load_state = auto_assign_balanced(ticket_dicts, TECHS, policy)
        st.session_state["assignment"] = assignment
        st.session_state["assign_load_state"] = load_state

        # CRITICAL: Save assignments to CSV so all portals see them
        # Update assigned_to column in tickets DataFrame
        tickets = da.load_tickets()
        for ticket_id, tech_name in assignment.items():
            # Find the ticket and update assigned_to
            mask = tickets["ticket_id"] == ticket_id
            if mask.any():
                # Use original tech name from CSV if available, otherwise use normalized name
                # Match tech name to CSV format (case-insensitive)
                techs_df = da.load_technicians()
                matching_techs = techs_df[techs_df["name"].str.lower().str.strip() == tech_name.lower().strip()]
                if len(matching_techs) > 0:
                    csv_tech_name = matching_techs.iloc[0]["name"]
                else:
                    csv_tech_name = tech_name
                tickets.loc[mask, "assigned_to"] = csv_tech_name
        
        # Save updated tickets to CSV
        da.save_tickets(tickets)
        
        # Clear cache to force reload
        if "all_tickets_df" in st.session_state:
            del st.session_state["all_tickets_df"]

        # CRITICAL: Do NOT compute one_in_progress after assignment
        # Status should only change when tech clicks "Start work" on Run page
        # The one_in_progress mapping should only exist when there's an actual active run
        # or when CSV already has "in-progress" status
        # Clear any stale one_in_progress mapping since we just assigned fresh tickets
        if "one_in_progress" in st.session_state:
            del st.session_state["one_in_progress"]

        # Rebuild live_df after assignment to update summary table
        # CRITICAL: Reload tickets from CSV to ensure we have fresh data
        tickets = da.load_tickets()
        runstate = get_runstate(st)
        # Pass empty dict for one_in_progress since we don't have active runs yet
        live_df = build_live_df(tickets, assignment, runstate, {})
        st.session_state["live_tickets_df"] = live_df

        # Assign tickets in Jira automatically based on ACTUAL assignments in tickets.csv
        jira_assigned = 0
        jira_errors = 0
        if not settings.demo_mode:
            # Load mappings (both email and accountId)
            tech_jira_email_map, tech_jira_account_id_map = load_tech_jira_mapping()
            jira_ticket_map = {}
            jira_mapping_file = Path("data") / "jira_ticket_mapping.csv"
            if jira_mapping_file.exists():
                jira_df = pd.read_csv(jira_mapping_file)
                jira_ticket_map = dict(zip(jira_df["ticket_id"], jira_df["jira_key"]))
            
            # CRITICAL: Use tickets.csv as source of truth for assignments
            # Find tickets that are actually assigned to technicians in the mapping
            from streamlit_app.lib.jira_adapter import add_comment, add_labels
            import ast
            import re
            
            for _, ticket_row in tickets.iterrows():
                ticket_id = ticket_row["ticket_id"]
                assigned_to = ticket_row.get("assigned_to", "")
                
                # Only process if ticket is assigned to a tech in our mapping
                if pd.notna(assigned_to) and assigned_to and assigned_to in tech_jira_email_map:
                    if ticket_id not in jira_ticket_map:
                        continue  # Skip if no Jira mapping exists
                    
                    jira_key = jira_ticket_map[ticket_id]
                    tech_name = assigned_to
                    jira_email = tech_jira_email_map[tech_name]
                    account_id = tech_jira_account_id_map.get(tech_name)
                    
                    # Assign in Jira
                    if assign_issue(jira_key, jira_email, account_id):
                        jira_assigned += 1
                        
                        # Add labels from tags
                        tags_str = ticket_row.get("tags", "")
                        # Ensure tags_str is a scalar string, not an array/Series
                        # Handle case where get() returns a Series
                        if isinstance(tags_str, pd.Series):
                            tags_str = tags_str.iloc[0] if len(tags_str) > 0 else ""
                        
                        # Now check if it's NaN and convert to string
                        # Use try/except to handle any edge cases
                        try:
                            # Check for None or empty first
                            if tags_str is None:
                                tags_str = ""
                            # Check for NaN (but avoid pd.isna() on Series)
                            elif isinstance(tags_str, (float, int)):
                                # For numeric types, check if it's NaN
                                import math
                                if isinstance(tags_str, float) and math.isnan(tags_str):
                                    tags_str = ""
                                else:
                                    tags_str = str(tags_str)
                            elif tags_str == "":
                                tags_str = ""
                            else:
                                tags_str = str(tags_str)
                        except (ValueError, TypeError):
                            tags_str = ""
                        
                        if tags_str and tags_str.strip():
                            try:
                                # Parse the nested tags format
                                # The tags are in a weird nested format, extract actual tag words
                                labels = []
                                
                                # Extract all alphanumeric words from the string
                                words = re.findall(r'[a-zA-Z_][a-zA-Z0-9_]*', str(tags_str))
                                
                                # Filter to common tag keywords (avoid Python keywords like 'list', 'str', etc.)
                                valid_tag_keywords = {
                                    'network', 'cabling', 'server', 'install', 'repair', 'labeling',
                                    'maintenance', 'upgrade', 'replacement', 'audit', 'configuration'
                                }
                                
                                # Find words that match known tag keywords
                                found_tags = [w for w in words if w.lower() in valid_tag_keywords]
                                
                                # Also look for any word that appears multiple times (likely a real tag)
                                from collections import Counter
                                word_counts = Counter(words)
                                common_words = [w for w, count in word_counts.items() 
                                              if count > 1 and len(w) > 2 and w.isalpha()]
                                
                                # Combine and deduplicate
                                labels = list(set(found_tags + common_words))
                                
                                # Add labels to Jira
                                if labels:
                                    add_labels(jira_key, labels)
                            except Exception as e:
                                print(f"Warning: Could not parse/add labels for {ticket_id}: {e}")
                    else:
                        jira_errors += 1

        if jira_assigned > 0:
            st.success(f"✅ Assigned {len(assignment)} tickets to technicians ({jira_assigned} synced to Jira)")
        elif jira_errors > 0:
            st.warning(f"✅ Assigned {len(assignment)} tickets locally ({jira_errors} Jira assignments failed)")
        else:
            st.success(f"✅ Assigned {len(assignment)} tickets to technicians")

# Show assignment summary (use live_df)
assignment = st.session_state.get("assignment", {})
load_state = st.session_state.get("assign_load_state", {})
live_df = st.session_state.get("live_tickets_df", tickets)

if assignment and not live_df.empty:
    # Aggregate from live_df
    assigned_df = live_df[live_df["assignee"].notna()].copy()
    
    # Initialize variables
    agg = pd.DataFrame(columns=["assignee", "tasks", "eta_min", "elapsed_min", "remaining_min"])
    tech_high = {}
    
    if not assigned_df.empty:
        agg = assigned_df.groupby("assignee").agg(
            tasks=("ticket_id", "count"),
            eta_min=("eta_minutes", "sum"),
            elapsed_min=("elapsed_min", "sum"),
            remaining_min=("remaining_min", "sum"),
        ).reset_index()
        agg["utilization_pct"] = (agg["elapsed_min"] / agg["eta_min"].clip(lower=1)) * 100
        
        # Count high-priority tickets per tech
        for ticket_id, tech_name in assignment.items():
            ticket_row = live_df[live_df["ticket_id"] == ticket_id]
            if not ticket_row.empty:
                priority = ticket_row.iloc[0].get("priority", "")
                if priority in ["Critical", "High"]:
                    tech_high[tech_name] = tech_high.get(tech_name, 0) + 1

    # Merge with tech info
    summary_data = []
    for tech in TECHS:
        name = tech["name"]
        # Find tech in aggregation results
        tech_row = None
        if not agg.empty and "assignee" in agg.columns:
            tech_matches = agg[agg["assignee"] == name]
            if not tech_matches.empty:
                tech_row = tech_matches.iloc[0]  # This is a Series, not DataFrame
        
        # Get in-progress ticket from live_df (based on actual CSV status and active runs)
        # This ensures we show the real in-progress ticket, not a computed one
        in_progress_ticket = "—"
        if not live_df.empty:
            tech_tickets = live_df[(live_df["assignee"] == name) & (live_df["status_view"] == "in-progress")]
            if not tech_tickets.empty:
                # Get the first in-progress ticket for this tech
                in_progress_ticket = tech_tickets.iloc[0]["ticket_id"]
        
        if tech_row is not None:
            row = tech_row  # tech_row is already a Series from iloc[0]
            capacity = tech.get("capacity_min", 240)
            # Utilization = elapsed time / capacity if work is in progress
            # Otherwise, show assigned load (ETA) / capacity
            elapsed = row["elapsed_min"]
            total_assigned = row["eta_min"]  # Total ETA of assigned tickets
            
            if elapsed > 0:
                # Work is in progress - use elapsed time
                utilization = (elapsed / capacity * 100) if capacity > 0 else 0
            else:
                # Work hasn't started - show assigned load percentage
                utilization = (total_assigned / capacity * 100) if capacity > 0 else 0
            
            summary_data.append(
                {
                    "Technician": name,
                    "Skill": tech.get("skill_level", 3),
                    "Total": int(row["tasks"]),
                    "High": tech_high.get(name, 0),
                    "ETA Min": round(row["eta_min"], 1),
                    "Elapsed Min": round(row["elapsed_min"], 1),
                    "Remaining Min": round(row["remaining_min"], 1),
                    "Util %": f"{utilization:.1f}%",
                    "In-Progress": in_progress_ticket,
                }
            )
        else:
            # Tech with no assignments
            summary_data.append(
                {
                    "Technician": name,
                    "Skill": tech.get("skill_level", 3),
                    "Total": 0,
                    "High": 0,
                    "ETA Min": 0.0,
                    "Elapsed Min": 0.0,
                    "Remaining Min": 0.0,
                    "Util %": "0.0%",
                    "In-Progress": "—",
                }
            )

    # Sort by remaining minutes descending to show load distribution
    summary_df = pd.DataFrame(summary_data)
    summary_df = summary_df.sort_values("Remaining Min", ascending=False).reset_index(drop=True)
    st.dataframe(summary_df, use_container_width=True, hide_index=True)
    
    # Show load balance metrics
    if not agg.empty:
        max_remaining = agg["remaining_min"].max()
        min_remaining = agg[agg["remaining_min"] > 0]["remaining_min"].min() if (agg["remaining_min"] > 0).any() else 0
        if min_remaining > 0:
            balance_ratio = max_remaining / min_remaining
            st.caption(
                f"Total assigned: {len(assignment)} tickets across {len(agg)} technicians · "
                f"Max remaining: {max_remaining:.1f} min · Balance ratio: {balance_ratio:.2f}x"
            )
        else:
            st.caption(f"Total assigned: {len(assignment)} tickets across {len(agg)} technicians")
    else:
        st.caption(f"Total assigned: {len(assignment)} tickets across 0 technicians")
else:
    st.info("No assignments yet. Click 'Auto-Assign Tickets (Balanced)' to assign tickets to technicians.")

st.markdown("---")

# Dashboard charts
col1, col2 = st.columns(2)

with col1:
    st.subheader("Open vs In-Progress vs Done")
    st.bar_chart(tickets["status"].value_counts())

with col2:
    st.subheader("Tickets by Priority")
    st.bar_chart(tickets["priority"].value_counts())

st.caption("Heatmap and efficiency graphs will be added after MVP.")

