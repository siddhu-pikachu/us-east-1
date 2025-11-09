import streamlit as st
import sys
import time
from pathlib import Path
from datetime import datetime

# Add parent directory to path for imports
_root = Path(__file__).parent.parent.parent.resolve()
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

# Clear any cached modules to ensure fresh imports
if "auth" in sys.modules:
    del sys.modules["auth"]
if "auth.session" in sys.modules:
    del sys.modules["auth.session"]
if "ops.history" in sys.modules:
    del sys.modules["ops.history"]
if "ops" in sys.modules:
    del sys.modules["ops"]

from streamlit_app.lib import data_access as da
from ops.sop import get_sop, get_tools
from ops.verify import verify_asset, preflight_ok
from ops.evidence import build_comment
from ops.history import log_completion, calc_completed_minutes
from ops.runlock import get_runstate
from ops.jira_wrap import JiraWrap
from streamlit_app.lib.jira_adapter import add_comment
from auth.session import gate

st.set_page_config(page_title="Ticket Update", layout="wide")

# Hide unauthorized pages from sidebar
from streamlit_app.lib.sidebar import hide_unauthorized_pages
hide_unauthorized_pages()

# Role gate - allow technician and manager (manager in read-only)
gate(["technician", "manager"])

from auth.session import get_current_role
from auth.login import get_auth_user, normalize_username

current_role = get_current_role()
auth_user = get_auth_user()
is_readonly = current_role == "manager"

st.title("💻 Workstation — Scan, SOP, Evidence")
if is_readonly:
    st.info("👁️ **Read-only mode** — You are viewing as a manager. Actions are disabled.")

# Initialize Jira wrapper and run state
if "jira_wrap" not in st.session_state:
    jira_client = st.session_state.get("jira_client")
    st.session_state["jira_wrap"] = JiraWrap(jira_client) if jira_client else None

jw = st.session_state.get("jira_wrap")
runstate = get_runstate(st)

# Get current technician
if is_readonly:
    # Manager: use selected technician from session or default
    tech_name = st.session_state.get("selected_technician", "all")
    if tech_name == "all":
        # Try to get from assignment
        assignment = st.session_state.get("assignment", {})
        if active_id := st.session_state.get("route_ticket_ids", [None])[0]:
            tech_name = assignment.get(active_id, "Ava")  # fallback
        else:
            # Default to first tech for manager view
            techs_df = da.load_technicians()
            if len(techs_df) > 0:
                tech_name = techs_df.iloc[0]["name"]
else:
    # Technician: use logged-in user, try to match CSV name
    from ops.techs import load_technicians
    techs_df = load_technicians()
    original_name = st.session_state.get("auth_original_name", auth_user)
    matching_techs = techs_df[techs_df["name"].str.lower().str.strip() == original_name.lower().strip()]
    if len(matching_techs) > 0:
        tech_name = matching_techs.iloc[0]["name"]
    else:
        tech_name = original_name

# Initialize session state
if "steps_log" not in st.session_state:
    st.session_state["steps_log"] = {}
if "run_pointer" not in st.session_state:
    st.session_state["run_pointer"] = 0
if "ticket_start_time" not in st.session_state:
    st.session_state["ticket_start_time"] = {}

# Mode selector
mode = st.radio("Source", ["Route run", "Single ticket"], horizontal=True)

# Get ticket data
tickets_df = st.session_state.get("map_topn_df")
all_df = st.session_state.get("all_tickets_df")
if all_df is None:
    all_df = da.load_tickets()
    st.session_state["all_tickets_df"] = all_df

# Ensure tickets have coordinates
if tickets_df is not None and ("x" not in tickets_df.columns or "y" not in tickets_df.columns):
    inventory_df = da.load_inventory()
    tickets_df = tickets_df.merge(
        inventory_df[["asset_id", "x", "y"]], on="asset_id", how="left"
    )


def _get_ticket_by_id(tid):
    """Get ticket by ID from available dataframes."""
    df = tickets_df if tickets_df is not None else all_df
    if df is None:
        return None
    r = df[df["ticket_id"] == tid]
    return None if r.empty else r.iloc[0].to_dict()


# Get ticket IDs based on mode
if mode == "Route run":
    ticket_ids = st.session_state.get("route_ticket_ids", [])
    if not ticket_ids:
        st.warning("No route loaded. Build route on Technician Map and click Start Run.")
        st.info("💡 Go to **Technician Map & Route** page, build a route, then click 'Start Run ▶'")
        st.stop()
    ptr = st.session_state["run_pointer"]
    ptr = min(ptr, len(ticket_ids) - 1)
    st.session_state["run_pointer"] = ptr
    active_id = ticket_ids[ptr]
    
    # Get tech name from assignment
    assignment = st.session_state.get("assignment", {})
    tech_name = assignment.get(active_id, st.session_state.get("selected_technician", "Ava"))
    
    # Note: We do NOT set status to in-progress here
    # Status will only change when "Start work" button is clicked
    
    st.info(f"📍 Ticket {ptr + 1} of {len(ticket_ids)} in route")
else:
    # Single ticket mode
    if tickets_df is not None and not tickets_df.empty:
        available_ids = tickets_df["ticket_id"].tolist()
    elif all_df is not None and not all_df.empty:
        available_ids = all_df["ticket_id"].tolist()
    else:
        available_ids = []
    if not available_ids:
        st.warning("No tickets available.")
        st.stop()
    sel = st.selectbox("Choose ticket", available_ids)
    active_id = sel
    
    # Get tech name from assignment
    assignment = st.session_state.get("assignment", {})
    tech_name = assignment.get(active_id, st.session_state.get("selected_technician", "Ava"))

# Get active ticket
ticket = _get_ticket_by_id(active_id)
if ticket is None:
    st.error("Ticket not found in current dataset.")
    st.stop()

# Check for active run
active_run = runstate.get_active(tech_name)
if active_run and active_run.ticket_id != active_id:
    st.warning(
        f"⚠️ You have an active run on {active_run.ticket_id}. Finish or abort it first."
    )
    st.info(f"Active run started at {time.strftime('%H:%M:%S', time.localtime(active_run.started_ts))}")

# Track start time for this ticket (legacy, may be removed)
if active_id not in st.session_state["ticket_start_time"]:
    st.session_state["ticket_start_time"][active_id] = time.time()

# Display ticket header
st.subheader(f"{active_id} · {ticket.get('summary', '')}")
st.caption(
    f"Asset: {ticket.get('asset_id', '?')} · Priority: {ticket.get('priority', '?')} · Status: {ticket.get('status', '?')}"
)

# Preflight check
ok_pf, msg_pf = preflight_ok(ticket)
if not ok_pf:
    st.error(f"Preflight blocked: {msg_pf}")

# Scan box
scan_val = st.text_input(
    "Scan or enter asset code",
    key="scan_box",
    placeholder="e.g., C-08 or asset barcode",
)

# Verify asset
verified, vmsg = verify_asset(scan_val, ticket.get("asset_id", ""))
st.checkbox("Verified asset match", value=verified, disabled=True)

if not verified and vmsg and scan_val:
    st.warning(vmsg)

# Touch activity on scan verification
if verified:
    runstate.touch(tech_name)

# SOP Steps
task_type = ticket.get("type", "recable_port")
steps = get_sop(task_type)
run_id = st.session_state.setdefault(
    "current_run_id", datetime.utcnow().strftime("%H%M%S")
)
logs = st.session_state["steps_log"].setdefault(active_id, [])

st.markdown("### SOP Steps")

for s in steps:
    disabled = (s.requires_scan and not verified) or not ok_pf
    step_done = any(l["id"] == s.id and l.get("done") for l in logs)
    button_label = ("✅ " if step_done else "▶ ") + s.label

    if st.button(
        button_label,
        key=f"btn_{active_id}_{s.id}",
        disabled=disabled or is_readonly,
        use_container_width=True,
    ):
        logs.append(
            {
                "id": s.id,
                "label": s.label,
                "done": True,
                "ts": datetime.utcnow().strftime("%H:%M:%SZ"),
            }
        )
        st.session_state["steps_log"][active_id] = logs
        runstate.touch(tech_name)  # Touch activity on step completion
        st.rerun()

# Tools
st.markdown("#### Tools")
tools_list = get_tools(task_type)
st.write(", ".join(tools_list) if tools_list else "—")

# Notes
notes = st.text_area("Notes (optional)", key=f"notes_{active_id}")

# Start work / Grace / Pause-Resume section
active_run = runstate.get_active(tech_name)
can_start = runstate.can_start(tech_name) and not active_run

if not active_run:
    # Start work section
    st.markdown("### 🚀 Start Work")
    confirm = st.checkbox("Confirm start (no scan available)", key="confirm_start")
    start_enabled = can_start and (verified or confirm)

    colA, colB = st.columns(2)
    with colA:
        if st.button(
            "Start work",
            disabled=not start_enabled or is_readonly,
            type="primary",
            use_container_width=True,
        ):
            run_id = datetime.utcnow().strftime("%Y%m%d%H%M%S")
            ar = runstate.start(tech_name, active_id, run_id)
            
            # Update ticket status to in-progress (THIS is when it changes)
            tickets_df = da.load_tickets()
            if active_id in tickets_df["ticket_id"].values:
                tickets_df.loc[tickets_df["ticket_id"] == active_id, "status"] = "in-progress"
                da.save_tickets(tickets_df)
                # Clear cache to force reload
                if "all_tickets_df" in st.session_state:
                    del st.session_state["all_tickets_df"]
            
            # Transition Jira status
            if jw:
                jw.safe_transition(active_id, "In Progress")
            
            st.success("✅ Started. Grace window active — you can Abort for ~45s.")
            st.rerun()

    with colB:
        if st.button("Abort (grace only)", use_container_width=True, disabled=is_readonly):
            if runstate.abort_if_in_grace(tech_name):
                if jw:
                    jw.safe_transition(active_id, "To Do")
                st.success("Aborted start; reverted to queued.")
            else:
                st.info("Grace window expired.")
            st.rerun()
else:
    # Active run controls
    st.markdown("### ⏸️ Active Run Controls")
    ar = active_run
    elapsed = calc_completed_minutes(ar.started_ts, ar.paused_seconds)
    remaining = max(0.0, float(ticket.get("estimated_minutes", 15)) - elapsed)
    
    col1, col2, col3 = st.columns(3)
    with col1:
        if not ar.paused and st.button("Pause", use_container_width=True, disabled=is_readonly):
            if not is_readonly:
                runstate.pause(tech_name)
                st.rerun()
        if ar.paused and st.button("Resume", use_container_width=True, disabled=is_readonly):
            if not is_readonly:
                runstate.resume(tech_name)
                st.rerun()
    
    with col2:
        st.metric("Elapsed", f"{elapsed:.1f} min")
    
    with col3:
        st.metric("Remaining", f"{remaining:.1f} min")
    
    # Idle check
    if runstate.idle_check(tech_name):
        st.warning("⚠️ No activity for 20 min. Mark idle to revert?")
        if st.button("Revert to queued", disabled=is_readonly):
            runstate.finish(tech_name)
            if jw:
                jw.safe_transition(active_id, "To Do")
            st.rerun()

# Action buttons
col1, col2 = st.columns(2)

with col1:
    # Only allow completion if there's an active run
    active_run = runstate.get_active(tech_name)
    complete_disabled = not (verified and ok_pf) or not active_run
    
    if st.button(
        "Complete & Comment to Jira",
        type="primary",
        use_container_width=True,
        disabled=complete_disabled or is_readonly,
    ):
        # Finish the run
        ar = runstate.finish(tech_name)  # clears lock
        if not ar:
            st.error("No active run found.")
            st.stop()
        
        # Calculate completed time
        elapsed_min = calc_completed_minutes(ar.started_ts, ar.paused_seconds)
        eta_minutes = float(ticket.get("estimated_minutes", 15))
        overran = elapsed_min > eta_minutes + 1.0
        
        # Check for follow-up
        had_followup = bool(
            notes
            and any(
                word in notes.lower()
                for word in ["follow", "revisit", "recheck", "verify again"]
            )
        )
        
        # Get assignee score (placeholder)
        assignee_score = 0.0
        
        # Build comment with marker
        run_id = ar.run_id
        comment = build_comment(run_id, active_id, logs, notes, distance_m=None)
        marker = f"[Run {run_id}]"
        
        # Post comment and transition (idempotent)
        if jw:
            jw.add_comment_once(active_id, comment, marker)
            jw.safe_transition(active_id, "Done")
        else:
            # Fallback to direct comment if no wrapper
            try:
                add_comment(active_id, comment)
            except Exception as e:
                st.warning(f"Could not post comment: {e}")
        
        # Log to history
        try:
            log_completion(
                ticket=ticket,
                tech=tech_name,
                completed_minutes=elapsed_min,
                eta_minutes=eta_minutes,
                overran=overran,
                had_followup=had_followup,
                assignee_score=assignee_score,
            )
        except Exception as e:
            st.warning(f"Could not log to history: {e}")
        
        # Update ticket status to "done"
        tickets_df = da.load_tickets()
        if active_id in tickets_df["ticket_id"].values:
            tickets_df.loc[tickets_df["ticket_id"] == active_id, "status"] = "done"
            da.save_tickets(tickets_df)
            # Clear cache to force reload
            if "all_tickets_df" in st.session_state:
                del st.session_state["all_tickets_df"]
        
        st.success(f"✅ Completed in ~{elapsed_min:.1f} min. Logged & transitioned.")
        
        if mode == "Route run":
            # Move to next ticket
            next_ptr = min(st.session_state["run_pointer"] + 1, len(ticket_ids) - 1)
            st.session_state["run_pointer"] = next_ptr
            
            # Note: We do NOT automatically set next ticket to in-progress
            # Tech must click "Start work" on the next ticket to begin it
            
            st.rerun()
        else:
            st.rerun()

with col2:
    if mode == "Route run" and st.button("Skip →", use_container_width=True, disabled=is_readonly):
        st.session_state["run_pointer"] = min(
            st.session_state["run_pointer"] + 1, len(ticket_ids) - 1
        )
        st.rerun()

