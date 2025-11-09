"""
Demo login system with username=password authentication.

Roles:
- Manager: stevejobs / stevejobs
- Engineer: stevewozniak / stevewozniak  
- Technician: any name from technicians.csv, password = name (case-insensitive)
"""

import streamlit as st
from pathlib import Path
import pandas as pd
import re


def normalize_username(name: str) -> str:
    """Normalize username to slug format (lowercase, spaces to dots)."""
    # Convert to lowercase and replace spaces/hyphens with dots
    normalized = re.sub(r'[\s\-]+', '.', name.lower().strip())
    # Remove any remaining special chars except dots
    normalized = re.sub(r'[^a-z0-9.]+', '', normalized)
    return normalized


def load_technician_names() -> set:
    """Load all technician names from CSV and normalize them."""
    tech_csv = Path("data") / "technicians.csv"
    if not tech_csv.exists():
        return set()
    
    try:
        df = pd.read_csv(tech_csv)
        if "name" not in df.columns:
            return set()
        # Normalize all names to slugs
        names = {normalize_username(name) for name in df["name"].dropna()}
        return names
    except Exception:
        return set()


def login(username: str, password: str) -> tuple[bool, str | None]:
    """
    Hardcoded login for demo - checks against hardcoded users and technicians CSV.
    
    Returns:
        (True, role) if login successful, (False, None) otherwise
    """
    if not username or not password:
        return False, None
    
    # Normalize username and password (case-insensitive)
    username_normalized = normalize_username(username)
    password_normalized = normalize_username(password)
    
    # Check if username matches password (required for all logins)
    if username_normalized != password_normalized:
        return False, None
    
    # Manager: steve.jobs (normalized from "steve jobs" or "steve.jobs")
    if username_normalized == "steve.jobs":
        return True, "manager"
    
    # Engineer: steve.wozniak (normalized from "steve wozniak" or "steve.wozniak")
    if username_normalized == "steve.wozniak":
        return True, "engineer"
    
    # Technician: check against all technicians from CSV
    tech_names = load_technician_names()
    if username_normalized in tech_names:
        # Find original name from CSV to store
        try:
            df = pd.read_csv(Path("data") / "technicians.csv")
            if "name" in df.columns:
                # Find matching name (case-insensitive, normalized)
                for original_name in df["name"].dropna():
                    if normalize_username(original_name) == username_normalized:
                        import streamlit as st
                        st.session_state["auth_original_name"] = original_name
                        break
        except Exception:
            pass
        return True, "technician"
    
    return False, None


def logout():
    """Clear authentication from session state."""
    keys_to_remove = ["auth_user", "auth_role", "auth_login_ts"]
    for key in keys_to_remove:
        if key in st.session_state:
            del st.session_state[key]
    # Also clear the old role selector
    if "role" in st.session_state:
        del st.session_state["role"]


def is_authenticated() -> bool:
    """Check if user is authenticated."""
    return "auth_user" in st.session_state and "auth_role" in st.session_state


def get_auth_user() -> str | None:
    """Get authenticated username."""
    return st.session_state.get("auth_user")


def get_auth_role() -> str | None:
    """Get authenticated user role."""
    return st.session_state.get("auth_role")


def require_auth():
    """Require authentication - redirect to login if not authenticated."""
    if not is_authenticated():
        st.switch_page("pages/0_login.py")
        st.stop()

