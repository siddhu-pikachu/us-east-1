import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import sys
import time
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
if "ops.route" in sys.modules:
    del sys.modules["ops.route"]
if "ops.assign" in sys.modules:
    del sys.modules["ops.assign"]
if "ops.techs" in sys.modules:
    del sys.modules["ops.techs"]
if "ops.scoring" in sys.modules:
    del sys.modules["ops.scoring"]
if "ops" in sys.modules:
    del sys.modules["ops"]

from streamlit_app.lib import data_access as da
from ops.scoring import compute_score, PRIO_COLOR
from ops.route import optimize
from ops.assign import prio_val, hours_old, jaccard
from ops.techs import load_technicians
from ops.live import build_live_df
from ops.runlock import get_runstate
from streamlit_app.lib.jira_adapter import add_comment
from streamlit_app.lib.floorplan_3d import create_3d_floorplan
from auth.session import gate

st.set_page_config(page_title="Action Plan", layout="wide")

# Hide unauthorized pages from sidebar
from streamlit_app.lib.sidebar import hide_unauthorized_pages
hide_unauthorized_pages()

# Role gate - allow technician and manager
gate(["technician", "manager"])

# Initialize session state keys
if "route_last_press" not in st.session_state:
    st.session_state["route_last_press"] = 0.0
if "route_points" not in st.session_state:
    st.session_state["route_points"] = []

st.title("🗺️ Data Hall Map & Route Optimizer")

# Load data
tickets_df = da.load_tickets()
techs_df = load_technicians()  # Use ops.techs for consistent loading
inventory_df = da.load_inventory()

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
if "assigned_to" in tickets_df.columns:
    assigned_tickets = tickets_df[tickets_df["assigned_to"].notna() & (tickets_df["assigned_to"] != "")]
    csv_assignment = dict(zip(assigned_tickets["ticket_id"], assigned_tickets["assigned_to"]))

# Use CSV assignment as primary source, session state as fallback
assignment = csv_assignment if csv_assignment else st.session_state.get("assignment", {})
# Also update session state with CSV assignments for consistency
if csv_assignment:
    st.session_state["assignment"] = csv_assignment

# CRITICAL: Sync one_in_progress_map with CSV status on every page load
# CSV is the source of truth - if CSV has no "in-progress", clear the mapping
has_active_runs = runstate and hasattr(runstate, "by_tech") and runstate.by_tech
tickets_status = set(tickets_df["status"].str.lower().unique())

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

live_df = build_live_df(tickets_df, assignment, runstate, one_ip)
st.session_state["live_tickets_df"] = live_df
all_df = live_df.copy()  # Keep reference for fallback

# Sidebar filters
st.sidebar.header("Filters")

# Status filter with "all" option
status_opts = ["all", "queued", "in-progress", "done"]
sel_status = st.sidebar.multiselect(
    "Status", status_opts, default=["queued", "in-progress"]
)
use_status = status_opts[1:] if "all" in sel_status else sel_status

# Technician filter with "all" option - use ALL names from CSV
tech_opts = ["all"] + sorted(techs_df["name"].astype(str).tolist())
prev_tech = st.session_state.get("selected_technician", "all")
sel_tech = st.sidebar.selectbox("Technician", tech_opts, index=0 if prev_tech == "all" else (tech_opts.index(prev_tech) if prev_tech in tech_opts else 0))

# Clear route if technician changed
if prev_tech != sel_tech:
    if "route_points" in st.session_state:
        del st.session_state["route_points"]
    if "route_ticket_ids" in st.session_state:
        del st.session_state["route_ticket_ids"]
    if "route_id" in st.session_state:
        del st.session_state["route_id"]

st.session_state["selected_technician"] = sel_tech

# Apply filters (use live_df)
filtered_df = live_df.copy()

# Status filter (use status_view for live sync)
if use_status:
    filtered_df = filtered_df[filtered_df["status_view"].str.lower().isin([s.lower() for s in use_status])]

# Assignment filter
# Use assignment from CSV (already built above)
asg = assignment
if sel_tech != "all":
    if not asg:
        st.warning("No assignments yet. Manager: run Auto-Assign.")
        filtered_df = filtered_df.iloc[0:0]  # Empty dataframe
    else:
        # Match tech name case-insensitively
        assigned_ticket_ids = [k for k, v in asg.items() if v and str(v).lower().strip() == sel_tech.lower().strip()]
        filtered_df = filtered_df[filtered_df["ticket_id"].isin(assigned_ticket_ids)]
        st.info(f"Showing {len(filtered_df)} tickets assigned to {sel_tech}")
else:
    if asg:
        st.info(f"Showing all {len(filtered_df)} tickets (no assignment filter)")

# One-in-progress is already handled in live_df via status_view
# No need to manually update status here

# Ensure tickets have x,y coordinates
if "x" not in filtered_df.columns or "y" not in filtered_df.columns:
    # Merge with inventory to get coordinates
    filtered_df = filtered_df.merge(
        inventory_df[["asset_id", "x", "y"]], on="asset_id", how="left"
    )
    filtered_df["x"] = filtered_df["x"].fillna(800)
    filtered_df["y"] = filtered_df["y"].fillna(450)

# Add mapping flag and compute scores
df = filtered_df.copy()
df["mapped"] = df[["x", "y"]].notna().all(axis=1)
mapped = df[df["mapped"]].copy()

if not mapped.empty:
    mapped["score"] = mapped.apply(lambda r: compute_score(r), axis=1)

topn = int(st.sidebar.slider("Top-N Now", 5, 50, 10))
topn_df = mapped.sort_values("score", ascending=False).head(topn) if not mapped.empty else mapped

# Stash topn_df for Run page
st.session_state["map_topn_df"] = topn_df

# Show assignment load info if viewing specific tech
load_state = st.session_state.get("assign_load_state", {})
if sel_tech != "all" and load_state and sel_tech in load_state:
    ls = load_state[sel_tech]
    assigned_minutes = ls.get("minutes", 0)
    capacity = ls.get("capacity", 240)
    utilization = (assigned_minutes / capacity * 100) if capacity > 0 else 0
    ticket_count = len([k for k, v in assignment.items() if v and str(v).lower().strip() == sel_tech.lower().strip()])
    st.info(
        f"📊 Assigned {ticket_count} tickets · Est load: {assigned_minutes:.1f} min · Util: {utilization:.1f}%"
    )

# Fix counts: show correct mapped vs unmapped
mapped_mask = filtered_df[["x", "y"]].notna().all(axis=1)
st.caption(
    f"{len(filtered_df)} tasks in view — {mapped_mask.sum()} mapped, {len(filtered_df) - mapped_mask.sum()} unmapped"
)

# View toggle
view_mode = st.radio("View Mode", ["2D Map", "3D Floorplan"], horizontal=True, key="view_mode")

# Main area: Map and details
col_map, col_details = st.columns([2, 1])

with col_map:
    if view_mode == "3D Floorplan":
        st.subheader("3D Interactive Floorplan")
        
        # Create 3D floorplan
        fig_3d = create_3d_floorplan(
            tickets_df=topn_df if not topn_df.empty else None,
            inventory_df=inventory_df,
            show_racks=True,
            show_tickets=True,
            show_equipment=True,
        )
        
        st.plotly_chart(fig_3d, use_container_width=True, key="floorplan_3d")
        
        st.caption("💡 **Interactive Controls:** Rotate (click & drag), Zoom (scroll), Pan (shift + drag)")
    else:
        st.subheader("Floorplan Map")

    # Create Plotly figure with floorplan background
    fig = go.Figure()

    # Define room boundaries to match 3D layout exactly
    # All scaled down 20x and depth increased by 200ft (1100 total depth)
    rooms_2d = {
        "High-Heat Server Room (Top)": {
            "bounds": [(0, 600), (0, 1100)],  # Top-left (matches 3D: scaled 0-30, 0-55 = original 0-600, 0-1100)
            "color": "rgba(200, 200, 200, 0.2)",
        },
        "High-Heat Server Room (Bottom)": {
            "bounds": [(0, 400), (0, 800)],  # Bottom-left (matches 3D: scaled 0-20, 0-40 = original 0-400, 0-800)
            "color": "rgba(200, 200, 200, 0.2)",
        },
        "Colocation Room": {
            "bounds": [(1000, 1600), (0, 1100)],  # Right side (matches 3D: scaled 50-80, 0-55 = original 1000-1600, 0-1100)
            "color": "rgba(180, 180, 200, 0.2)",
        },
        "NOC Room": {
            "bounds": [(400, 800), (0, 500)],  # Bottom-center (matches 3D: scaled 20-40, 0-25 = original 400-800, 0-500)
            "color": "rgba(150, 200, 150, 0.2)",
        },
        "Staging Room": {
            "bounds": [(800, 1000), (0, 500)],  # Bottom-right (matches 3D: scaled 40-50, 0-25 = original 800-1000, 0-500)
            "color": "rgba(200, 200, 150, 0.2)",
        },
    }
    
    # Add room outlines to match 3D layout
    for room_name, room_data in rooms_2d.items():
        x_min, x_max = room_data["bounds"][0]
        y_min, y_max = room_data["bounds"][1]
        
        # Room outline rectangle
        fig.add_shape(
            type="rect",
            x0=x_min, x1=x_max, y0=y_min, y1=y_max,
            line=dict(color="rgba(150, 150, 150, 0.6)", width=2),
            fillcolor=room_data["color"],
            layer="below",
        )
    
    # Add floorplan image as background (if exists)
    floorplan_path = Path("data/floorplan.png")
    if floorplan_path.exists():
        fig.add_layout_image(
            dict(
                source=str(floorplan_path),
                x=0,
                y=1100,  # Updated to match increased depth (was 900)
                sizex=1600,
                sizey=1100,  # Updated to match increased depth (was 900)
                xref="x",
                yref="y",
                sizing="stretch",
                layer="below",
                opacity=0.3,  # Semi-transparent so room outlines show
            )
        )

    # Filter tickets to only show those within data hall rooms
    def is_in_room_2d(x, y):
        """Check if a point is within any defined room."""
        for room_name, room_data in rooms_2d.items():
            x_min, x_max = room_data["bounds"][0]
            y_min, y_max = room_data["bounds"][1]
            if x_min <= x <= x_max and y_min <= y <= y_max:
                return True
        return False
    
    # Filter topn_df to only tickets within rooms
    if not topn_df.empty:
        topn_df = topn_df[
            topn_df.apply(lambda row: is_in_room_2d(float(row["x"]), float(row["y"])), axis=1)
        ]
    
    # Group by (x,y) to handle overlapping pins
    plot_rows = []
    for (x, y), g in topn_df.groupby(["x", "y"]):
        # Pick color by max priority
        rank = g["priority"].map(
            lambda p: {"Critical": 4, "High": 3, "Medium": 2, "Low": 1}.get(
                str(p).title(), 1
            )
        )
        top = g.iloc[rank.argmax()]
        hover = "<br>".join(
            f"{r.ticket_id} · {r.priority} · {getattr(r, 'status_view', r.status)}" for r in g.itertuples()
        )
        plot_rows.append(
            {
                "x": float(x),
                "y": float(y),
                "color": PRIO_COLOR.get(top.priority, "#60a5fa"),
                "hover": hover,
                "count": len(g),
            }
        )

    plot_df = pd.DataFrame(plot_rows)

    # Add single scatter trace for all pins
    if not plot_df.empty:
        fig.add_trace(
            go.Scatter(
                x=plot_df["x"],
                y=plot_df["y"],
                mode="markers+text",
                name="Tickets",
                marker=dict(
                    size=12,
                    color=plot_df["color"],
                    line=dict(width=2, color="white"),
                ),
                text=[
                    f"{count}x" if count > 1 else ""
                    for count in plot_df["count"]
                ],
                textposition="top center",
                textfont=dict(size=8),
                hovertext=plot_df["hover"],
                hoverinfo="text",
            )
        )

    # Add NOC start point (top-right corner of data hall)
    # Position matches 3D: (77.5, 53.75) scaled = (1550, 1075) original
    fig.add_trace(
        go.Scatter(
            x=[1550],  # Matches 3D X position (77.5 * 20 = 1550)
            y=[1075],  # Matches 3D Y position (53.75 * 20 = 1075), moved 200ft along depth axis
            mode="markers",
            name="NOC (Start)",
            marker=dict(size=15, color="#0000FF", symbol="star"),
        )
    )

    # Configure layout
    fig.update_xaxes(range=[0, 1600], visible=False)
    fig.update_yaxes(
        range=[0, 1100], visible=False, scaleanchor="x", scaleratio=1  # Updated depth to 1100 (was 900)
    )
    fig.update_layout(
        width=1000,
        height=600,
        showlegend=True,
        hovermode="closest",
        margin=dict(l=0, r=0, t=0, b=0),
    )

    # Draw route if available (starting from NOC at top-right)
    pts = st.session_state.get("route_points", [])
    if pts:
        route_x = [1550] + [p["x"] for p in pts]  # NOC at (1550, 1075)
        route_y = [1075] + [p["y"] for p in pts]  # Updated to match new NOC position
        fig.add_trace(
            go.Scatter(
                x=route_x,
                y=route_y,
                mode="lines+markers+text",
                name="Route",
                line=dict(color="#0000FF", width=3, dash="dash"),
                marker=dict(size=12, color="#0000FF"),
                text=["NOC"] + [f"{i+1}" for i in range(len(pts))],
                textposition="top center",
                textfont=dict(size=10, color="white"),
            )
        )

    # Display map
    st.plotly_chart(fig, use_container_width=True, key="map")

    # Route building section
    st.subheader("Route Optimization")
    col_route1, col_route2 = st.columns([3, 1])

    with col_route1:
        # Only show Build Route if specific tech selected
        if sel_tech != "all":
            press = st.button("🔧 Build Route", type="primary", use_container_width=True)
        else:
            press = False
            st.info("💡 Select a specific technician to build routes.")

    with col_route2:
        if st.button("Clear Route"):
            st.session_state["route_points"] = []
            st.session_state["route_ticket_ids"] = []
            st.session_state["route_id"] = ""
            st.session_state["route_distance"] = 0.0
            st.rerun()

    # Debounced route building
    now = time.time()
    if press and now - st.session_state["route_last_press"] > 0.75:
        st.session_state["route_last_press"] = now
        # Build points_raw from currently assigned Top-N
        if not topn_df.empty:
            points_raw = []
            for r in topn_df.itertuples():
                if pd.notna(r.x) and pd.notna(r.y):
                    points_raw.append(
                        {
                            "ticket_id": r.ticket_id,
                            "x": float(r.x),
                            "y": float(r.y),
                            "doors": getattr(r, "doors", 0) if hasattr(r, "doors") else 0,
                            "cage_changes": getattr(r, "cage_changes", 0)
                            if hasattr(r, "cage_changes")
                            else 0,
                        }
                    )

            if points_raw:
                try:
                    result = optimize(points_raw, start=(1550, 1075))  # NOC at top-right corner, matches 3D position
                    # Validate result structure
                    if not isinstance(result, dict) or "sequence" not in result:
                        st.error(f"Route optimization returned unexpected format: {type(result)} - {result}")
                        st.stop()
                    
                    st.session_state["route_ticket_ids"] = result["sequence"]
                    st.session_state["route_id"] = result.get("route_id", "")
                    st.session_state["route_distance"] = result.get("distance", 0.0)

                    # Build route_points for drawing (in sequence order)
                    route_points = []
                    ticket_dict = {r.ticket_id: (float(r.x), float(r.y)) for r in topn_df.itertuples() if pd.notna(r.x) and pd.notna(r.y)}
                    for tid in result["sequence"]:
                        if tid in ticket_dict:
                            x, y = ticket_dict[tid]
                            route_points.append({"ticket_id": tid, "x": x, "y": y})
                    st.session_state["route_points"] = route_points

                    st.success(
                        f"Route {result['route_id']}: {len(result['sequence'])} stops · {result['distance']:.1f} px"
                    )
                    st.rerun()
                except Exception as e:
                    st.error(f"Error building route: {e}")
                    import traceback
                    st.code(traceback.format_exc())
                    st.stop()

    # Display route results (only if specific tech selected, not "all")
    route_ids = st.session_state.get("route_ticket_ids", [])
    route_id = st.session_state.get("route_id", "")
    route_distance = st.session_state.get("route_distance", 0.0)
    pts = st.session_state.get("route_points", [])

    if sel_tech == "all":
        st.info("💡 Select a specific technician to build and view routes.")
    elif route_ids:
        # Show route info banner
        st.info(f"📍 **Start:** NOC (1550, 1075) | **Route ID:** `{route_id}` | **Distance:** {route_distance:.1f} px")
        
        st.success(f"✅ Route ready with {len(route_ids)} stops.")
        st.subheader("📋 Run Sheet (Ordered)")
        run_sheet_data = []
        
        # Build ticket lookup dict
        ticket_lookup = {}
        if not topn_df.empty:
            for _, row in topn_df.iterrows():
                ticket_lookup[row["ticket_id"]] = row
        if all_df is not None:
            for _, row in all_df.iterrows():
                if row["ticket_id"] not in ticket_lookup:
                    ticket_lookup[row["ticket_id"]] = row
        
        # Build run sheet in sequence order (route order is already optimized)
        run_sheet_data = []
        for idx, ticket_id in enumerate(route_ids, 1):
            ticket_row = ticket_lookup.get(ticket_id)
            run_sheet_data.append(
                {
                    "#": idx,
                    "Ticket ID": ticket_id,
                    "Asset": ticket_row.get("asset_id", "N/A") if ticket_row is not None else "N/A",
                    "Summary": ticket_row.get("summary", "") if ticket_row is not None else "N/A",
                    "Priority": ticket_row.get("priority", "") if ticket_row is not None else "N/A",
                }
            )
        run_sheet_df = pd.DataFrame(run_sheet_data)
        run_sheet_df = run_sheet_df.reset_index(drop=True)
        st.dataframe(run_sheet_df, use_container_width=True, hide_index=True)

        # Export buttons
        col_exp1, col_exp2 = st.columns(2)

        with col_exp1:
            ticket_list = "\n".join([f"{i+1}. {tid}" for i, tid in enumerate(route_ids)])
            st.code(ticket_list, language="text")
            st.caption("Copy the ticket order above")

        with col_exp2:
            if st.button("💬 Comment Route to Jira"):
                route_summary = f"Optimized route ({len(route_ids)} stops, Route ID: {route_id}):\n\n"
                route_summary += "\n".join([f"{i+1}. {tid}" for i, tid in enumerate(route_ids)])
                
                # Post comment to each ticket (if Jira integration available)
                success_count = 0
                for ticket_id in route_ids:
                    try:
                        # Try to extract Jira key from ticket_id (format: KAN-123 or TICK-1)
                        if ticket_id.startswith("TICK-"):
                            # Demo mode - just log
                            st.info(f"Demo mode: Would comment on {ticket_id}")
                        else:
                            add_comment(ticket_id, route_summary)
                            success_count += 1
                    except Exception as e:
                        st.warning(f"Could not comment on {ticket_id}: {e}")
                
                if success_count > 0:
                    st.success(f"✅ Posted route summary to {success_count} ticket(s)")

        # Start Run button (only show if specific tech selected, not "all")
        if route_ids and sel_tech != "all" and st.button("Start Run ▶", type="primary", use_container_width=True):
            # Ensure route_id is set
            if "route_id" not in st.session_state:
                st.session_state["route_id"] = route_id
            st.switch_page("pages/4_Run.py")

with col_details:
    st.subheader("📝 Ticket Details")

    # Ticket selection dropdown
    if not topn_df.empty:
        sel_id = st.selectbox("Select ticket", topn_df["ticket_id"].tolist())
        details = topn_df[topn_df["ticket_id"] == sel_id].iloc[0].to_dict()
        display_data = {
            k: details[k]
            for k in ["ticket_id", "summary", "asset_id", "priority", "status"]
            if k in details
        } | {"score": float(details.get("score", 0))}
        st.json(display_data)
    else:
        st.info("No mapped tickets available")

    # SOP and tools section
    st.subheader("🔧 SOP & Tools")
    st.markdown("""
    **Standard Procedure:**
    1. Setup (2 min)
    2. Per-U work (0.2 min/U)
    3. Verification (1 min)
    
    **Common Tools:**
    - Screwdriver set
    - Cable tester
    - Label printer
    - ESD wrist strap
    """)

    # ETA calculation
    if "selected_ticket" in st.session_state:
        ticket = st.session_state.selected_ticket
        u_value = ticket.get("u", 1)
        eta = 2 + (0.2 * u_value) + 1
        st.metric("Estimated Time", f"{eta:.1f} minutes")

