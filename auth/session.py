import streamlit as st

ROLES = ("technician", "manager", "engineer")


def get_role():
    """Get current user role from session state. Defaults to 'technician'."""
    return st.session_state.get("role", "technician")


def get_current_role() -> str:
    """Alias for get_role() for backward compatibility."""
    return get_role()


def gate(allowed):
    """Gate page access by role. Shows info message and stops if role not allowed."""
    if get_role() not in allowed:
        st.info("Switch role on Home to view this page.")
        st.stop()

