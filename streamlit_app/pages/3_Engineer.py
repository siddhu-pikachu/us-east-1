import streamlit as st
import sys
import re
from pathlib import Path

# Add parent directory to path for imports
_root = Path(__file__).parent.parent.parent.resolve()
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

# Clear any cached auth modules
if "auth" in sys.modules:
    del sys.modules["auth"]
if "auth.session" in sys.modules:
    del sys.modules["auth.session"]

from lib.jira_adapter import create_issue
from lib.config import settings
from lib import data_access as da
from auth.session import gate
from auth.login import get_auth_user
import pandas as pd
from ops.estimate import estimate_minutes
from ops.sop import get_tools
from datetime import datetime
from pathlib import Path

st.set_page_config(page_title="Engineer Dashboard", layout="wide")

# Hide unauthorized pages from sidebar
from streamlit_app.lib.sidebar import hide_unauthorized_pages
hide_unauthorized_pages()

# Role gate
gate(["engineer"])

# Get logged-in engineer username
auth_user = get_auth_user()

st.title("Engineer — Create Ticket")

# Load inventory for TicketGuard
inventory = da.load_inventory()
known_assets = set(inventory["asset_id"].astype(str))

# Common task types
TASK_TYPES = [
    "recable_port",
    "install_server", 
    "swap_psu",
    "reseat_blade",
    "audit_label",
    "replace_sfp"
]

with st.form("create"):
    col1, col2 = st.columns(2)
    
    with col1:
        asset_id = st.text_input("Asset ID (required)", "", help="Enter the asset identifier (e.g., F-04)")
        task_type = st.selectbox("Task Type", [""] + TASK_TYPES, help="Select the type of work to be performed")
        priority = st.selectbox("Priority", ["Low", "Medium", "High", "Critical"], index=1)
        impact = st.selectbox("Impact", [1, 2, 3], index=1, help="1=Low, 2=Medium, 3=High impact")
    
    with col2:
        deadline = st.date_input("Deadline")
        estimated_min = st.number_input("Estimated Minutes", min_value=10, max_value=120, value=30, step=5, 
                                        help="Auto-filled based on task type, but editable")
        requires_tools = st.text_input("Required Tools", "", 
                                       help="Auto-filled based on task type, but editable (e.g., 'basic', 'ESD strap, Label printer')")
    
    summary = st.text_input("Summary", "", placeholder="e.g., recable_port on F-04", 
                           help="Brief description of the task")
    description = st.text_area("Description", "", placeholder="Detailed description of what needs to be done",
                              help="Provide context and any special instructions")
    
    issue_type = st.selectbox("Jira Issue Type", ["Task", "Bug", "Story"], help="Jira issue type")
    
    submitted = st.form_submit_button("Create Ticket", type="primary")

# Auto-fill suggestions (shown outside form since forms don't support dynamic updates)
if task_type and asset_id:
    # Calculate auto-estimated minutes
    ticket_dict = {"type": task_type, "priority": priority, "asset_id": asset_id}
    auto_estimated = estimate_minutes(ticket_dict)
    
    # Get auto-suggested tools
    auto_tools = get_tools(task_type)
    
    # Show auto-fill suggestions
    if auto_estimated != estimated_min or (auto_tools and not requires_tools):
        with st.expander("💡 Auto-fill Suggestions", expanded=False):
            if auto_estimated != estimated_min:
                st.info(f"💡 Suggested estimated minutes: **{auto_estimated}** (based on task type, priority, and location)")
            if auto_tools and not requires_tools:
                suggested_tools = ", ".join(auto_tools)
                st.info(f"💡 Suggested tools: **{suggested_tools}**")
            if not summary:
                suggested_summary = f"{task_type} on {asset_id}"
                st.info(f"💡 Suggested summary: **{suggested_summary}**")

# TicketGuard validation
st.subheader("🔍 TicketGuard Validation")

# Placeholder values that should be rejected
INVALID_PLACEHOLDERS = ["na", "n/a", "none", "null", "nil", "tbd", "tba", "todo", ""]

def is_valid_field(value) -> bool:
    """Check if a field contains valid data (not a placeholder)."""
    if value is None or pd.isna(value):
        return False
    value_str = str(value).strip()
    if not value_str:
        return False
    value_lower = value_str.lower()
    # Check if it's a placeholder value
    if value_lower in INVALID_PLACEHOLDERS:
        return False
    # Must be at least 3 characters (to avoid "na", "no", etc.)
    return len(value_str) >= 3

# Compute completeness score
complete = 0
req = 4  # asset_id, task_type, summary, description
validation_errors = []

if asset_id and asset_id in known_assets:
    complete += 1
elif not asset_id:
    validation_errors.append("Asset ID is required")
elif asset_id not in known_assets:
    validation_errors.append(f"Asset ID '{asset_id}' not found in inventory")

if task_type and is_valid_field(task_type):
    complete += 1
elif not task_type:
    validation_errors.append("Task Type is required")

if summary and is_valid_field(summary):
    complete += 1
elif not summary:
    validation_errors.append("Summary is required")
elif not is_valid_field(summary):
    validation_errors.append("Summary must contain meaningful data (not 'na', 'n/a', etc.)")

if description and is_valid_field(description):
    complete += 1
elif not description:
    validation_errors.append("Description is required")
elif not is_valid_field(description):
    validation_errors.append("Description must contain meaningful data (not 'na', 'n/a', etc.)")

# Check for placeholder values in optional but filled fields
# Only validate if the field has been filled (not empty)
if requires_tools:
    requires_tools_str = str(requires_tools).strip() if requires_tools else ""
    if requires_tools_str and not is_valid_field(requires_tools_str):
        validation_errors.append("Required Tools must contain valid data (not 'na', 'n/a', 'none', etc.)")

pct = int(100 * complete / req)
st.progress(pct / 100.0, text=f"Completeness {pct}%")

# Block if incomplete OR if placeholder values detected
block = pct < 80 or len(validation_errors) > 0

# Check for risky words in description
risk_words = ("outage", "single-homed", "production")
final_priority = priority
priority_note = ""

if description and any(w in description.lower() for w in risk_words):
    final_priority = "High"
    priority_note = f"⚠️ Priority auto-raised to **High** (risky words detected: {', '.join([w for w in risk_words if w in description.lower()])})"

if priority_note:
    st.warning(priority_note)

# Auto-fill hidden fields if asset exists in inventory
auto_filled = {}
if asset_id and asset_id in known_assets:
    asset_row = inventory[inventory["asset_id"] == asset_id].iloc[0]
    if "row" in asset_row and pd.notna(asset_row["row"]):
        auto_filled["row"] = asset_row["row"]
    if "rack" in asset_row and pd.notna(asset_row["rack"]):
        auto_filled["rack"] = asset_row["rack"]
    if "u" in asset_row and pd.notna(asset_row["u"]):
        auto_filled["u"] = asset_row["u"]

if auto_filled:
    st.info(f"Auto-filled from inventory: {', '.join([f'{k}={v}' for k, v in auto_filled.items()])}")

# Display validation errors
if block:
    if validation_errors:
        st.error(f"**TicketGuard blocked:** {' | '.join(validation_errors)}")
    elif pct < 80:
        st.error(f"**TicketGuard blocked:** Ticket is incomplete ({pct}% complete, need 80%+)")
else:
    st.success("✅ TicketGuard: All checks passed")

if submitted:
    # TicketGuard blocking
    if block:
        st.error("Cannot create ticket: TicketGuard validation failed. Fix the issues above.")
    else:
        # Build enhanced description with all metadata for technicians
        enhanced_description = description
        enhanced_description += f"\n\n*Details:*\n"
        enhanced_description += f"* Asset ID: {asset_id}\n"
        enhanced_description += f"* Type: {task_type}\n"
        enhanced_description += f"* Impact: {impact}\n"
        enhanced_description += f"* Estimated Minutes: {estimated_min}\n"
        if requires_tools:
            enhanced_description += f"* Requires Tools: {requires_tools}\n"
        enhanced_description += f"* Deadline: {deadline}\n"
        if auto_filled:
            location_parts = []
            if "row" in auto_filled:
                location_parts.append(f"Row {auto_filled['row']}")
            if "rack" in auto_filled:
                location_parts.append(f"Rack {auto_filled['rack']}")
            if "u" in auto_filled:
                location_parts.append(f"U {auto_filled['u']}")
            if location_parts:
                enhanced_description += f"* Location: {', '.join(location_parts)}\n"
        
        # Create issue with priority only (no custom fields that don't exist)
        fields = {
            "priority": {"name": final_priority},
        }
        
        issue = create_issue(summary, enhanced_description, issue_type, fields)
        jira_key = issue['key']
        
        # Generate ticket_id
        existing_tickets = da.load_tickets()
        max_ticket_num = 0
        for ticket_id in existing_tickets["ticket_id"]:
            if ticket_id.startswith("TICK-"):
                try:
                    num = int(ticket_id.split("-")[1])
                    max_ticket_num = max(max_ticket_num, num)
                except:
                    pass
        new_ticket_id = f"TICK-{max_ticket_num + 1}"
        
        # Get location data from inventory
        x, y, row, rack, u = None, None, None, None, None
        if asset_id and asset_id in known_assets:
            asset_row = inventory[inventory["asset_id"] == asset_id].iloc[0]
            x = asset_row.get("x")
            y = asset_row.get("y")
            row = asset_row.get("row")
            rack = asset_row.get("rack")
            u = asset_row.get("u")
        
        # Create new ticket row
        new_ticket = {
            "ticket_id": new_ticket_id,
            "summary": summary,
            "description": description,  # Original description, not enhanced
            "asset_id": asset_id,
            "type": task_type,
            "priority": final_priority,
            "impact": float(impact),
            "deadline": str(deadline),
            "status": "queued",
            "created_by": auth_user if auth_user else "engineer",  # Use logged-in username
            "assigned_to": "",  # Not assigned yet
            "estimated_minutes": int(estimated_min),
            "requires_tools": requires_tools if requires_tools else "basic",
            "change_window_start": datetime.now().strftime("%Y-%m-%dT00:00:00"),
            "change_window_end": datetime.now().replace(year=datetime.now().year + 1).strftime("%Y-%m-%dT23:59:59"),
            "x": x if pd.notna(x) else None,
            "y": y if pd.notna(y) else None,
            "row": row if pd.notna(row) else None,
            "rack": rack if pd.notna(rack) else None,
            "u": u if pd.notna(u) else None,
            "tags": "",  # Can be populated later
            "created": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S.%fZ")
        }
        
        # Add new ticket to CSV
        new_ticket_df = pd.DataFrame([new_ticket])
        all_tickets = pd.concat([existing_tickets, new_ticket_df], ignore_index=True)
        da.save_tickets(all_tickets)
        
        # Save Jira mapping
        jira_mapping_file = Path("data") / "jira_ticket_mapping.csv"
        if jira_mapping_file.exists():
            jira_mapping_df = pd.read_csv(jira_mapping_file)
        else:
            jira_mapping_df = pd.DataFrame(columns=["ticket_id", "jira_key"])
        
        # Add new mapping
        new_mapping = pd.DataFrame([{"ticket_id": new_ticket_id, "jira_key": jira_key}])
        jira_mapping_df = pd.concat([jira_mapping_df, new_mapping], ignore_index=True)
        jira_mapping_df.to_csv(jira_mapping_file, index=False)
        
        st.success(
            f"✅ Ticket created: **{new_ticket_id}** → Jira: **{jira_key}** (priority: {final_priority})"
        )
        st.info(f"📝 Ticket saved to local CSV and will appear in Technician page")
        
        # Clear cache to force reload on other pages
        if "all_tickets_df" in st.session_state:
            del st.session_state["all_tickets_df"]
        
        # Rerun to show the ticket was created (optional - can remove if you want to keep form filled)
        # st.rerun()

