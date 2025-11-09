from typing import Tuple, Mapping


def verify_asset(scanned: str, expected_asset_id: str) -> Tuple[bool, str]:
    """Verify scanned asset code matches expected asset ID."""
    if not scanned:
        return False, "No code entered"
    ok = scanned.strip().lower() == str(expected_asset_id).strip().lower()
    return (ok, "" if ok else f"Scanned '{scanned}' ≠ expected '{expected_asset_id}'")


def preflight_ok(ticket: Mapping) -> Tuple[bool, str]:
    """
    MVP: block if missing map coords (as a proxy for bad asset) or expired deadline.
    Returns (is_ok, error_message).
    """
    if ticket.get("x") is None or ticket.get("y") is None:
        return False, "Asset has no coordinates (inventory incomplete)."
    return True, ""

