from dataclasses import dataclass
from typing import List, Dict


@dataclass
class SopStep:
    id: str
    label: str
    requires_scan: bool = False
    min_seconds: int = 0  # cosmetic for ETA


SOP: Dict[str, List[SopStep]] = {
    "recable_port": [
        SopStep("preflight", "Preflight window + redundancy check", True),
        SopStep("locate", "Locate rack/asset/port", True),
        SopStep("esd", "PPE + ESD on"),
        SopStep("decable", "Remove old cable", min_seconds=60),
        SopStep("recable", "Attach new cable & label", min_seconds=120),
        SopStep("verify", "Verify link & light", min_seconds=60),
    ],
    "install_server": [
        SopStep("preflight", "Preflight window + redundancy check", True),
        SopStep("unbox", "Unbox & inspect", min_seconds=120),
        SopStep("rack", "Rack at correct U position", True, min_seconds=180),
        SopStep("power", "Connect dual power feeds", min_seconds=120),
        SopStep("network", "Connect NIC uplinks", min_seconds=120),
        SopStep("post", "Power on & verify POST", min_seconds=120),
    ],
}

TOOLS = {
    "recable_port": ["ESD strap", "Label printer", "Cable tester", "LC cleaner"],
    "install_server": ["Torque driver", "Rails kit", "Labels", "ESD strap"],
}


def get_sop(task_type: str) -> List[SopStep]:
    """Get SOP steps for a task type."""
    return SOP.get(task_type, [SopStep("preflight", "Preflight", True)])


def get_tools(task_type: str) -> List[str]:
    """Get required tools for a task type."""
    return TOOLS.get(task_type, [])

