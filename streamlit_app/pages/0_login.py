"""
Login page for NMC² Ops Console.

Demo login: username = password
- Manager: steve.jobs / steve.jobs
- Engineer: steve.wozniak / steve.wozniak
- Technician: any name from technicians.csv, password = name
"""

import streamlit as st
import sys
from pathlib import Path

# Add parent directory to path for imports
_root = Path(__file__).parent.parent.parent.resolve()
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

from auth.login import login, normalize_username

st.set_page_config(
    page_title="Login", 
    page_icon="🔐", 
    layout="centered",
    initial_sidebar_state="collapsed"
)

# Hide sidebar menu on login page
st.markdown("""
<style>
    [data-testid="stSidebar"] {
        display: none;
    }
</style>
""", unsafe_allow_html=True)

# If already logged in, redirect to role-specific home page
if "auth_user" in st.session_state and "auth_role" in st.session_state:
    role = st.session_state.get("auth_role")
    if role == "manager":
        st.switch_page("pages/2_Manager.py")
    elif role == "technician":
        st.switch_page("pages/1_Technician.py")
    elif role == "engineer":
        st.switch_page("pages/3_Engineer.py")
    else:
        st.switch_page("0_Home.py")
    st.stop()

st.title("🔐 NMC² Ops Console Login")

st.markdown("### Demo Login")
st.caption("**Username = Password** (case-insensitive)")

# Get pre-filled values from session state (set by pre-fill buttons)
prefill_user = st.session_state.get("prefill_username", "")
prefill_pass = st.session_state.get("prefill_password", "")

# Login form
with st.form("login_form"):
    username = st.text_input("Username", value=prefill_user)
    password = st.text_input("Password", type="password", value=prefill_pass)
    
    submitted = st.form_submit_button("Login", type="primary")
    
    if submitted:
        if not username or not password:
            st.error("Please enter both username and password")
        else:
            success, role = login(username, password)
            if success:
                # Store auth in session state
                st.session_state["auth_user"] = username
                st.session_state["auth_role"] = role
                st.session_state["auth_login_ts"] = st.session_state.get("_session_id", "unknown")
                
                # Original name should already be stored by login() if technician
                # For non-technicians, store username as original
                if "auth_original_name" not in st.session_state:
                    st.session_state["auth_original_name"] = username
                
                # Clear pre-fill values after successful login
                if "prefill_username" in st.session_state:
                    del st.session_state["prefill_username"]
                if "prefill_password" in st.session_state:
                    del st.session_state["prefill_password"]
                
                # Set flag for post-form handling
                st.session_state["_login_just_succeeded"] = True
                st.session_state["_login_username"] = username
                st.session_state["_login_role"] = role
                st.rerun()
            else:
                st.error("❌ Invalid username or password")

# Handle successful login - redirect to role-specific home page
if st.session_state.get("_login_just_succeeded", False):
    login_role = st.session_state.get("_login_role", "")
    
    # Clear the flag
    del st.session_state["_login_just_succeeded"]
    if "_login_username" in st.session_state:
        del st.session_state["_login_username"]
    if "_login_role" in st.session_state:
        del st.session_state["_login_role"]
    
    # Redirect to role-specific home page
    if login_role == "manager":
        st.switch_page("pages/2_Manager.py")
    elif login_role == "technician":
        st.switch_page("pages/1_Technician.py")
    elif login_role == "engineer":
        st.switch_page("pages/3_Engineer.py")
    else:
        st.switch_page("0_Home.py")

# Quick links for demo
st.markdown("---")
st.markdown("### Quick Links (for demo)")

col1, col2, col3 = st.columns(3)

with col1:
    st.markdown("**Manager**")
    st.markdown("Username: `steve.jobs`")
    st.markdown("Password: `steve.jobs`")
    if st.button("🔗 Pre-fill Manager", use_container_width=True):
        st.session_state["prefill_username"] = "steve.jobs"
        st.session_state["prefill_password"] = "steve.jobs"
        st.rerun()

with col2:
    st.markdown("**Engineer**")
    st.markdown("Username: `steve.wozniak`")
    st.markdown("Password: `steve.wozniak`")
    if st.button("🔗 Pre-fill Engineer", use_container_width=True):
        st.session_state["prefill_username"] = "steve.wozniak"
        st.session_state["prefill_password"] = "steve.wozniak"
        st.rerun()

with col3:
    st.markdown("**Technician**")
    # Load first technician from CSV for demo
    from auth.login import load_technician_names, normalize_username
    import pandas as pd
    from pathlib import Path
    tech_csv = Path("data") / "technicians.csv"
    tech_username = "ava"  # default
    tech_original = "Ava"  # default
    if tech_csv.exists():
        try:
            df = pd.read_csv(tech_csv)
            if "name" in df.columns and len(df) > 0:
                tech_original = df["name"].iloc[0]
                tech_username = normalize_username(tech_original)
        except Exception:
            pass
    st.markdown(f"Username: `{tech_username}`")
    st.markdown(f"Password: `{tech_username}`")
    if st.button("🔗 Pre-fill Technician", use_container_width=True):
        st.session_state["prefill_username"] = tech_username
        st.session_state["prefill_password"] = tech_username
        st.rerun()

st.caption("💡 Click buttons above to pre-fill both username and password, then click Login")

