"""
Session management with authentication gating.

Updated to use new auth system from auth.login.
"""

import streamlit as st
from auth.login import require_auth, get_auth_role, is_authenticated

ROLES = ("technician", "manager", "engineer")


def get_role():
    """Get current user role from auth system or fallback to session state."""
    # Try new auth system first
    if is_authenticated():
        return get_auth_role()
    # Fallback to old system for backward compatibility
    return st.session_state.get("role", "technician")


def get_current_role() -> str:
    """Alias for get_role() for backward compatibility."""
    return get_role()


def gate(allowed_roles):
    """
    Gate page access by role. Requires authentication and checks role.
    
    Args:
        allowed_roles: List of allowed roles (e.g., ["manager", "technician"])
    """
    # Require authentication first
    require_auth()
    
    # Check role
    role = get_role()
    if role not in allowed_roles:
        st.error(f"❌ Access Denied")
        st.info(f"You are logged in as **{role}**, but this page requires: {', '.join(allowed_roles)}")
        st.info("Please log out and switch to an authorized account.")
        st.stop()

