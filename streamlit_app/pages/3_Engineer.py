import streamlit as st
import sys
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

st.set_page_config(page_title="Engineer", layout="wide")

# Role gate
gate(["engineer"])

st.title("Engineer — Create Ticket")

with st.form("create"):
    summary = st.text_input("Summary", "")
    description = st.text_area("Description", "")
    issue_type = st.selectbox("Issue Type", ["Task", "Bug", "Story"])
    asset_id = st.text_input("Asset ID (required)", "")
    priority = st.selectbox("Priority", ["Low", "Medium", "High", "Critical"], index=1)
    deadline = st.date_input("Deadline")
    submitted = st.form_submit_button("Create")

# Lint badge area (stub for TicketGuard)
st.subheader("🔍 Validation")
lint_warnings = []
lint_errors = []

if not asset_id:
    lint_errors.append("❌ Asset ID is required")
elif submitted or asset_id:
    # Check if asset exists in inventory
    inventory = da.load_inventory()
    if asset_id not in inventory["asset_id"].values:
        lint_warnings.append("⚠️ Unknown asset; will require manual verification.")

if not summary:
    lint_errors.append("❌ Summary is required")

# Display lint results
if lint_errors:
    for err in lint_errors:
        st.error(err)
if lint_warnings:
    for warn in lint_warnings:
        st.warning(warn)
if not lint_errors and not lint_warnings and (submitted or asset_id or summary):
    st.success("✅ All validations passed")

if submitted:
    # Basic validation gate
    missing = []
    if not summary:
        missing.append("summary")
    if not asset_id:
        missing.append("asset_id")
    if missing:
        st.error(f"Missing required fields: {', '.join(missing)}")
    else:
        fields = {
            "customfield_assetId": asset_id,
            "customfield_deadline": str(deadline),
            "priority": {"name": priority},
        }
        issue = create_issue(summary, description, issue_type, fields)
        st.success(
            f"Issue created: {issue['key']} (mode: {'DEMO' if settings.demo_mode else 'LIVE'})"
        )
        st.json(issue)

