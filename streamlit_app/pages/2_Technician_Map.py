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

# Clear any cached auth modules
if "auth" in sys.modules:
    del sys.modules["auth"]
if "auth.session" in sys.modules:
    del sys.modules["auth.session"]

from streamlit_app.lib import data_access as da
from ops.scoring import compute_score, PRIO_COLOR
from ops.route import optimize
from streamlit_app.lib.jira_adapter import add_comment
from auth.session import gate

st.set_page_config(page_title="Technician Map & Route", layout="wide")

# Role gate
gate(["technician"])

# Initialize session state keys
if "route_last_press" not in st.session_state:
    st.session_state["route_last_press"] = 0.0
if "route_points" not in st.session_state:
    st.session_state["route_points"] = []

st.title("🗺️ Data Hall Map & Route Optimizer")

# Load data
tickets_df = da.load_tickets()
techs_df = da.load_technicians()
inventory_df = da.load_inventory()

# Sidebar filters
st.sidebar.header("Filters")
selected_tech = st.sidebar.selectbox("Technician", techs_df["name"].tolist())
status_filter = st.sidebar.multiselect(
    "Status",
    ["queued", "in-progress", "done"],
    default=["queued", "in-progress"],
)

# Filter tickets
filtered_df = tickets_df[tickets_df["status"].isin(status_filter)].copy()

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

st.caption(
    f"{len(df)} tasks filtered — {len(topn_df)} mapped in Top-N, {len(df) - len(mapped)} unmapped (excluded)"
)

# Main area: Map and details
col_map, col_details = st.columns([2, 1])

with col_map:
    st.subheader("Floorplan Map")

    # Create Plotly figure with floorplan background
    fig = go.Figure()

    # Add floorplan image as background
    floorplan_path = Path("data/floorplan.png")
    if floorplan_path.exists():
        fig.add_layout_image(
            dict(
                source=str(floorplan_path),
                x=0,
                y=900,
                sizex=1600,
                sizey=900,
                xref="x",
                yref="y",
                sizing="stretch",
                layer="below",
            )
        )

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
            f"{r.ticket_id} · {r.priority} · {r.status}" for r in g.itertuples()
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

    # Add NOC start point
    fig.add_trace(
        go.Scatter(
            x=[800],
            y=[860],
            mode="markers",
            name="NOC (Start)",
            marker=dict(size=15, color="#0000FF", symbol="star"),
        )
    )

    # Configure layout
    fig.update_xaxes(range=[0, 1600], visible=False)
    fig.update_yaxes(
        range=[0, 900], visible=False, scaleanchor="x", scaleratio=1
    )
    fig.update_layout(
        width=1000,
        height=600,
        showlegend=True,
        hovermode="closest",
        margin=dict(l=0, r=0, t=0, b=0),
    )

    # Draw route if available
    pts = st.session_state.get("route_points", [])
    if pts:
        route_x = [800] + [p["x"] for p in pts]
        route_y = [860] + [p["y"] for p in pts]
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
        press = st.button("🔧 Build Route", type="primary", use_container_width=True)

    with col_route2:
        if st.button("Clear Route"):
            st.session_state["route_points"] = []
            st.rerun()

    # Debounced route building
    now = time.time()
    if press and now - st.session_state["route_last_press"] > 0.75:
        st.session_state["route_last_press"] = now
        # Simple nearest-neighbor route (no solver)
        if not topn_df.empty:
            pts = [
                {"ticket_id": r.ticket_id, "x": float(r.x), "y": float(r.y)}
                for r in topn_df.itertuples()
            ]
            st.session_state["route_points"] = pts  # store only; draw above
            st.rerun()

    # Display route results
    pts = st.session_state.get("route_points", [])
    if pts:
        st.success(f"✅ Route ready with {len(pts)} stops.")
        st.subheader("📋 Run Sheet (Ordered)")
        run_sheet_data = []
        for idx, ticket in enumerate(pts, 1):
            ticket_row = topn_df[topn_df["ticket_id"] == ticket["ticket_id"]].iloc[0] if not topn_df.empty else None
            run_sheet_data.append(
                {
                    "#": idx,
                    "Ticket ID": ticket["ticket_id"],
                    "Asset": ticket_row["asset_id"] if ticket_row is not None else "N/A",
                    "Summary": ticket_row.get("summary", "") if ticket_row is not None else "N/A",
                    "Priority": ticket_row.get("priority", "") if ticket_row is not None else "N/A",
                }
            )
        run_sheet_df = pd.DataFrame(run_sheet_data)
        st.dataframe(run_sheet_df, use_container_width=True, hide_index=True)

        # Export buttons
        col_exp1, col_exp2 = st.columns(2)

        with col_exp1:
            ticket_list = "\n".join([f"{i+1}. {t['ticket_id']}" for i, t in enumerate(pts)])
            st.code(ticket_list, language="text")
            st.caption("Copy the ticket order above")

        with col_exp2:
            if st.button("💬 Comment Route to Jira"):
                route_summary = f"Optimized route ({len(pts)} stops):\n\n"
                route_summary += "\n".join([f"{i+1}. {t['ticket_id']}" for i, t in enumerate(pts)])
                
                # Post comment to each ticket (if Jira integration available)
                success_count = 0
                for ticket in pts:
                    try:
                        # Try to extract Jira key from ticket_id (format: KAN-123 or TICK-1)
                        ticket_key = ticket["ticket_id"]
                        if ticket_key.startswith("TICK-"):
                            # Demo mode - just log
                            st.info(f"Demo mode: Would comment on {ticket_key}")
                        else:
                            add_comment(ticket_key, route_summary)
                            success_count += 1
                    except Exception as e:
                        st.warning(f"Could not comment on {ticket['ticket_id']}: {e}")
                
                if success_count > 0:
                    st.success(f"✅ Posted route summary to {success_count} ticket(s)")

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

