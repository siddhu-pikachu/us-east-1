import streamlit as st
from lib.config import settings
from lib.jira_adapter import connection_ok
from auth.session import get_current_role
from lib import data_access as da

st.set_page_config(page_title="NMC² Ops Console", layout="wide")

st.title("NMC² Ops Console (MVP)")
st.caption("Role-aware Streamlit app with Jira integration and Demo Mode.")

# Role selector (stub)
st.sidebar.header("Role Selection")
role = st.sidebar.selectbox(
    "Select Role",
    ["technician", "manager", "engineer"],
    index=0,
    key="role_selector",
)
st.session_state["role"] = role
current_role = get_current_role()

# Load data for stats
all_tickets = da.load_tickets()
inventory_df = da.load_inventory()

# Ensure tickets have x,y coordinates for stats
if "x" not in all_tickets.columns or "y" not in all_tickets.columns:
    all_tickets = all_tickets.merge(
        inventory_df[["asset_id", "x", "y"]], on="asset_id", how="left"
    )

cols = st.columns(3)

with cols[0]:
    st.subheader("Environment")
    st.write(f"DEMO_MODE = **{settings.demo_mode}**")
    st.write(f"Jira base: `{settings.jira_base_url or 'demo'}`")
    ok = connection_ok()
    st.write(f"Jira connection: **{'OK' if ok else 'FAILED'}**")
    st.write(f"Current Role: **{current_role}**")

with cols[1]:
    st.subheader("Quick Links")
    st.page_link("pages/1_Technician.py", label="📋 Technician List")
    st.page_link("pages/2_Technician_Map.py", label="🗺️ Technician Map & Route")
    st.page_link("pages/2_Manager.py", label="📊 Manager Dashboard")
    st.page_link("pages/3_Engineer.py", label="➕ Engineer Create Ticket")

with cols[2]:
    st.subheader("Docs")
    st.markdown("- Set secrets in `.env` (see `.env.example`).")
    st.markdown("- Run `make seed` to generate synthetic data.")
    st.markdown("- Use Map & Route page for optimized task routing.")

# Stats footer
st.markdown("---")
st.subheader("📊 Ticket Statistics")
col_stat1, col_stat2, col_stat3 = st.columns(3)

with col_stat1:
    st.metric("Total Tickets", len(all_tickets))

with col_stat2:
    mapped_count = all_tickets[["x", "y"]].notna().all(axis=1).sum()
    st.metric("Mapped (have coords)", mapped_count)

with col_stat3:
    unmapped_count = (~all_tickets[["x", "y"]].notna().all(axis=1)).sum()
    st.metric("Unmapped", unmapped_count)

st.caption(
    f"**Note:** The Map page shows only mapped tickets with coordinates. "
    f"Unmapped tickets ({unmapped_count}) are excluded from routing."
)

