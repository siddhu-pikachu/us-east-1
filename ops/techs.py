import pandas as pd
import streamlit as st
from pathlib import Path
from typing import List, Dict


@st.cache_data
def load_technicians(path: str = "data/technicians.csv") -> pd.DataFrame:
    """
    Load technicians from CSV.
    
    CSV schema expected:
    name,team,skill_level,tags,capacity_min,start_x,start_y
    
    Or with defaults:
    name (required), skill_level (default 3), tags (default ""), 
    capacity_min (default 240), start_x (default 800), start_y (default 860)
    """
    df = pd.read_csv(path)
    df["name"] = df["name"].astype(str)
    
    # Set defaults for missing columns
    if "capacity_min" not in df.columns:
        df["capacity_min"] = 240
    if "start_x" not in df.columns:
        df["start_x"] = 800
    if "start_y" not in df.columns:
        df["start_y"] = 860
    if "skill_level" not in df.columns:
        df["skill_level"] = 3
    if "tags" not in df.columns:
        df["tags"] = ""
    
    # Ensure numeric types
    df["capacity_min"] = pd.to_numeric(df["capacity_min"], errors="coerce").fillna(240).astype(int)
    df["start_x"] = pd.to_numeric(df["start_x"], errors="coerce").fillna(800).astype(float)
    df["start_y"] = pd.to_numeric(df["start_y"], errors="coerce").fillna(860).astype(float)
    df["skill_level"] = pd.to_numeric(df["skill_level"], errors="coerce").fillna(3).astype(int)
    
    # Parse tags: convert comma-separated string to list of lowercase tags
    df["tags"] = df["tags"].fillna("").apply(
        lambda s: [t.strip().lower() for t in str(s).split(",") if t.strip()]
    )
    
    return df


def techs_as_list(df: pd.DataFrame) -> List[Dict]:
    """Convert technicians DataFrame to list of dicts for auto_assign."""
    return [
        {
            "name": str(r.name),
            "capacity_min": int(r.capacity_min),
            "start_xy": (float(r.start_x), float(r.start_y)),
            "skill_level": int(getattr(r, "skill_level", 3)),
            "tags": getattr(r, "tags", []),
            "team": str(getattr(r, "team", "")),
        }
        for r in df.itertuples()
    ]

