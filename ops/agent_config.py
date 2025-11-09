"""
AI Agent Configuration Management

Stores agent settings (enabled/disabled) and tracks last run time.
"""

import json
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, Optional

CONFIG_FILE = Path("data") / "ai_agent_config.json"


def load_agent_config() -> Dict:
    """Load agent configuration from file."""
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, 'r') as f:
                return json.load(f)
        except Exception:
            pass
    # Default config
    return {
        "enabled": False,
        "last_run": None,
        "confidence_threshold": 0.75,
        "max_tickets": 2,
    }


def save_agent_config(config: Dict) -> None:
    """Save agent configuration to file."""
    CONFIG_FILE.parent.mkdir(exist_ok=True)
    with open(CONFIG_FILE, 'w') as f:
        json.dump(config, f, indent=2)


def is_agent_enabled() -> bool:
    """Check if agent is enabled."""
    config = load_agent_config()
    return config.get("enabled", False)


def should_run_agent() -> bool:
    """Check if agent should run (enabled and 24+ hours since last run)."""
    config = load_agent_config()
    if not config.get("enabled", False):
        return False
    
    last_run_str = config.get("last_run")
    if not last_run_str:
        return True  # Never run before
    
    try:
        last_run = datetime.fromisoformat(last_run_str)
        hours_since_last_run = (datetime.now() - last_run).total_seconds() / 3600
        return hours_since_last_run >= 24
    except Exception:
        return True  # If we can't parse, run it


def mark_agent_run() -> None:
    """Mark that the agent has just run."""
    config = load_agent_config()
    config["last_run"] = datetime.now().isoformat()
    save_agent_config(config)

