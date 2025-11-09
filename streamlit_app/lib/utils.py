import streamlit as st


def badge(label: str, color: str = "blue"):
    st.markdown(
        f"<span style='background:{color};color:white;padding:2px 6px;border-radius:6px;font-size:12px'>{label}</span>",
        unsafe_allow_html=True,
    )

