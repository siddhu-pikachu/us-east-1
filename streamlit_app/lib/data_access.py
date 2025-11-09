import pandas as pd
from pathlib import Path
import json

DATA_DIR = Path("data")


def load_assets() -> pd.DataFrame:
    return pd.read_csv(DATA_DIR / "assets.csv")


def load_technicians() -> pd.DataFrame:
    return pd.read_csv(DATA_DIR / "technicians.csv")


def load_tickets() -> pd.DataFrame:
    """Load tickets and normalize tags, estimate minutes if missing."""
    tickets = pd.read_csv(DATA_DIR / "tickets.csv")
    
    # Normalize tags: convert comma-separated string to list
    if "tags" not in tickets.columns:
        tickets["tags"] = ""
    tickets["tags"] = tickets["tags"].fillna("").apply(
        lambda s: [t.strip().lower() for t in str(s).split(",") if t.strip()]
    )
    
    # Estimate minutes if missing or invalid
    try:
        from ops.estimate import estimate_minutes
        
        if "estimated_minutes" not in tickets.columns or tickets["estimated_minutes"].isna().any():
            tickets["estimated_minutes"] = tickets.apply(
                lambda r: estimate_minutes(r.to_dict()), axis=1
            )
        # Also update any that are too low (< 10 minutes) or too high (> 60 minutes)
        mask = (tickets["estimated_minutes"] < 10) | (tickets["estimated_minutes"] > 60) | tickets["estimated_minutes"].isna()
        if mask.any():
            tickets.loc[mask, "estimated_minutes"] = tickets.loc[mask].apply(
                lambda r: estimate_minutes(r.to_dict()), axis=1
            )
    except Exception:
        # Fallback if estimate module not available
        if "estimated_minutes" not in tickets.columns:
            tickets["estimated_minutes"] = 30
    
    return tickets


def save_tickets(df: pd.DataFrame) -> None:
    df.to_csv(DATA_DIR / "tickets.csv", index=False)


def load_inventory() -> pd.DataFrame:
    """Load inventory CSV with asset coordinates."""
    if (DATA_DIR / "inventory.csv").exists():
        return pd.read_csv(DATA_DIR / "inventory.csv")
    # Fallback to assets.csv if inventory.csv doesn't exist
    return load_assets()


def load_coords() -> dict:
    """Load coordinates mapping from JSON."""
    coords_path = DATA_DIR / "coords.json"
    if coords_path.exists():
        return json.loads(coords_path.read_text())
    return {}

