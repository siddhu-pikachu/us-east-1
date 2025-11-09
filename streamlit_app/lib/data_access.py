import pandas as pd
from pathlib import Path
import json

DATA_DIR = Path("data")


def load_assets() -> pd.DataFrame:
    return pd.read_csv(DATA_DIR / "assets.csv")


def load_technicians() -> pd.DataFrame:
    return pd.read_csv(DATA_DIR / "technicians.csv")


def load_tickets() -> pd.DataFrame:
    return pd.read_csv(DATA_DIR / "tickets.csv")


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

