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

st.set_page_config(page_title="Manager", layout="wide")

# Role gate
gate(["manager"])

st.title("Manager Dashboard (MVP)")

tickets = da.load_tickets()
techs = da.load_technicians()

col1, col2 = st.columns(2)

with col1:
    st.subheader("Open vs In-Progress vs Done")
    st.bar_chart(tickets["status"].value_counts())

with col2:
    st.subheader("Tickets by Priority")
    st.bar_chart(tickets["priority"].value_counts())

st.caption("Heatmap and efficiency graphs will be added after MVP.")

