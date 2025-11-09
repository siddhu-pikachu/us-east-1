import streamlit as st
import sys
from pathlib import Path

# Add parent directory to path for imports
_root = Path(__file__).parent.parent.resolve()
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

from lib.config import settings
from lib.jira_adapter import connection_ok
from auth.session import get_current_role, gate
from auth.login import get_auth_user, logout, is_authenticated
from lib import data_access as da

st.set_page_config(page_title="NMC² Ops Console", layout="wide")

# Require authentication (but allow all roles)
if not is_authenticated():
    st.switch_page("pages/0_login.py")
    st.stop()

# Redirect to role-specific home page
current_role = get_current_role()
if current_role == "manager":
    st.switch_page("pages/2_Manager.py")
elif current_role == "technician":
    st.switch_page("pages/1_Technician.py")
elif current_role == "engineer":
    st.switch_page("pages/3_Engineer.py")
# If role is not one of the above, show this page (fallback)

# Hide unauthorized pages from sidebar
from streamlit_app.lib.sidebar import hide_unauthorized_pages
hide_unauthorized_pages()

auth_user = get_auth_user()

st.title("NMC² Ops Console")
st.caption("Role-aware Streamlit app with Jira integration and Demo Mode.")

# Navbar with user info and logout
col_nav1, col_nav2 = st.columns([3, 1])
with col_nav1:
    st.markdown(f"**Logged in as:** {auth_user} · **{current_role}**")
with col_nav2:
    if st.button("🚪 Logout", use_container_width=True):
        logout()
        st.switch_page("pages/0_login.py")

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
    
    # Role-specific navigation
    if current_role == "manager":
        st.page_link("pages/2_Manager.py", label="📊 Manager Dashboard")
        st.page_link("pages/2_Technician_Map.py", label="🗺️ Floor Map")
        st.page_link("pages/1_Technician.py", label="👥 Technicians")
        st.page_link("pages/2_Manager_Training.py", label="🎓 Tech Training")
        st.page_link("pages/2_Manager_Predictive.py", label="🔮 Predictive Maintenance")
        st.info("💡 **Tip:** Use Auto-Assign Agent to rebalance workload")
    elif current_role == "technician":
        st.page_link("pages/1_Technician.py", label="📋 My Tickets")
        st.page_link("pages/2_Technician_Map.py", label="🗺️ Floor Map")
        st.page_link("pages/4_Run.py", label="💻 Workstation")
        st.info("💡 **Tip:** Workstation → Start work to mark In-Progress")
    elif current_role == "engineer":
        st.page_link("pages/3_Engineer.py", label="➕ Create Ticket")
        st.page_link("pages/3_Engineer_Requests.py", label="📋 My Requests")
        st.info("💡 **Tip:** My Requests shows predicted finish times")

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

