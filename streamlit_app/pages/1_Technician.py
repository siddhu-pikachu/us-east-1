import streamlit as st
import pandas as pd
import sys
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

from lib import data_access as da
from auth.session import gate

st.set_page_config(page_title="Technician", layout="wide")

# Role gate
gate(["technician"])

st.title("Technician")

assets = da.load_assets()
tickets = da.load_tickets()
techs = da.load_technicians()

st.sidebar.header("Filters")
me = st.sidebar.selectbox("Technician", techs["name"].tolist())
status = st.sidebar.multiselect(
    "Status", ["queued", "in-progress", "done"], default=["queued", "in-progress"]
)

filtered = tickets[tickets["status"].isin(status)]

st.write(f"{len(filtered)} tasks in view.")

# Simple list for MVP
st.dataframe(
    filtered[["ticket_id", "summary", "asset_id", "priority", "deadline", "status"]],
    use_container_width=True,
)

st.info("Map & routing will be added next. This page is functional for listing/selection in MVP.")

# Add link to map page
st.markdown("---")
col1, col2 = st.columns([3, 1])
with col1:
    st.write("**Ready to optimize your route?**")
with col2:
    st.page_link("pages/2_Technician_Map.py", label="🗺️ Open Map & Route Optimizer →", icon="🗺️")

