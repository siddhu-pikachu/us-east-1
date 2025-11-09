import streamlit as st
import pandas as pd
import sys
from pathlib import Path
from datetime import datetime, timedelta

# Add parent directory to path for imports
_root = Path(__file__).parent.parent.parent.resolve()
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

# Clear any cached modules
if "ops.models" in sys.modules:
    del sys.modules["ops.models"]
if "ops.synth_history" in sys.modules:
    del sys.modules["ops.synth_history"]
if "lib.data_access" in sys.modules:
    del sys.modules["lib.data_access"]
if "streamlit_app.lib.data_access" in sys.modules:
    del sys.modules["streamlit_app.lib.data_access"]
if "ops" in sys.modules:
    del sys.modules["ops"]

from auth.session import gate
from lib import data_access as da
from ops.models import train_predictive_maintenance_model
from ops.synth_history import synth_history, build_training_tables
from ops.ai_agent import ai_agent_create_maintenance_tickets
from ops.agent_config import load_agent_config, save_agent_config, should_run_agent, mark_agent_run, is_agent_enabled
from streamlit_app.lib.jira_adapter import create_issue

st.set_page_config(page_title="Predictive Maintenance Agent", layout="wide")

# Hide unauthorized pages from sidebar
from streamlit_app.lib.sidebar import hide_unauthorized_pages
hide_unauthorized_pages()

# Role gate
gate(["manager"])

st.title("🔮 Predictive Maintenance Approval")

st.markdown("""
Review predicted maintenance tickets based on failure risk analysis. Approve tickets with a single click to create them in the system.
""")

# Load failure events and training data
FAIL_CSV = Path("data") / "failure_events.csv"
TRAIN_PDM_CSV = Path("data") / "train_predictive_maint.csv"
HIST_CSV = Path("data") / "history_tickets.csv"
TICKETS_CSV = Path("data") / "tickets.csv"

# Auto-generate data if missing
if not FAIL_CSV.exists() or not TRAIN_PDM_CSV.exists() or not HIST_CSV.exists():
    with st.spinner("🔄 Generating historical data (this may take a moment)..."):
        try:
            hist_df, fail_df = synth_history(n_days=240, avg_tickets_per_day=12, write_files=True)
            build_training_tables(hist_df, fail_df)
            st.success(f"✅ Generated {len(hist_df)} history rows and {len(fail_df)} failure rows.")
            st.rerun()  # Reload page to show the data
        except Exception as e:
            st.error(f"❌ Error generating data: {e}")
            import traceback
            st.code(traceback.format_exc())
            st.stop()

# Now load the data
try:
    fail_df = pd.read_csv(FAIL_CSV)
    train_df = pd.read_csv(TRAIN_PDM_CSV)
    existing_tickets = da.load_tickets()
    
    if fail_df.empty:
        st.warning("⚠️ No failure events found in historical data.")
    else:
        # Filter to recent failures or high-risk predictions
        # For demo, we'll use failures that are predicted to happen soon (<=3 days)
        # In production, this would use the trained model to predict on current assets
        
        # Get recent failure events (last 30 days worth)
        recent_failures = fail_df.copy()
        
        # Add prediction score (simplified - in production use actual model)
        # For now, prioritize by: days_to_fail <= 3, redundancy_risk, priority
        recent_failures["risk_score"] = (
            (recent_failures["days_to_fail"] <= 3).astype(int) * 0.5 +
            (recent_failures["redundancy_risk"] / 2.0) * 0.3 +
            recent_failures["priority"].map({"Critical": 0.2, "High": 0.15, "Medium": 0.1, "Low": 0.05})
        )
        
        # Sort by risk score
        recent_failures = recent_failures.sort_values("risk_score", ascending=False)
        
        # Filter to high-risk items (top 20 or risk_score > 0.3)
        high_risk = recent_failures[recent_failures["risk_score"] > 0.3].head(20)
        
        if high_risk.empty:
            st.success("✅ No high-risk predictive maintenance items at this time.")
        else:
            st.subheader(f"⚠️ High-Risk Predictive Maintenance Tickets ({len(high_risk)} items)")
            
            # Display summary
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("High-Risk Items", len(high_risk))
            with col2:
                critical_count = (high_risk["priority"] == "Critical").sum()
                st.metric("Critical Priority", critical_count)
            with col3:
                single_homed = (high_risk["redundancy_risk"] == 2).sum()
                st.metric("Single-Homed Assets", single_homed)
            
            st.markdown("---")
            
            # Create display table
            display_data = []
            for idx, row in high_risk.iterrows():
                # Check if ticket already exists for this asset
                asset_tag = row["asset_tag"]
                existing = existing_tickets[
                    (existing_tickets["asset_id"] == asset_tag) & 
                    (existing_tickets["status"].isin(["queued", "in-progress"]))
                ]
                already_exists = len(existing) > 0
                
                display_data.append({
                    "Asset": asset_tag,
                    "Failure Tag": row["failure_tag"],
                    "Type": row["type"],
                    "Priority": row["priority"],
                    "Redundancy Risk": "High" if row["redundancy_risk"] == 2 else "Medium" if row["redundancy_risk"] == 1 else "Low",
                    "Days to Fail": row["days_to_fail"],
                    "Risk Score": f"{row['risk_score']:.2f}",
                    "Status": "⚠️ Already exists" if already_exists else "✅ Ready to approve",
                })
            
            display_df = pd.DataFrame(display_data)
            st.dataframe(
                display_df,
                use_container_width=True,
                hide_index=True,
            )
            
            st.markdown("---")
            st.subheader("✅ Approve Tickets")
            
            # Batch approval
            if st.button("🚀 Approve All High-Risk Tickets", type="primary"):
                approved_count = 0
                skipped_count = 0
                errors = []
                
                with st.spinner("Creating tickets..."):
                    for idx, row in high_risk.iterrows():
                        asset_tag = row["asset_tag"]
                        
                        # Check if already exists
                        existing = existing_tickets[
                            (existing_tickets["asset_id"] == asset_tag) & 
                            (existing_tickets["status"].isin(["queued", "in-progress"]))
                        ]
                        if len(existing) > 0:
                            skipped_count += 1
                            continue
                        
                        try:
                            # Generate ticket
                            max_ticket_num = 0
                            for ticket_id in existing_tickets["ticket_id"]:
                                if ticket_id.startswith("TICK-"):
                                    try:
                                        num = int(ticket_id.split("-")[1])
                                        max_ticket_num = max(max_ticket_num, num)
                                    except:
                                        pass
                            new_ticket_id = f"TICK-{max_ticket_num + 1}"
                            
                            # Get asset location if available
                            inventory = da.load_inventory()
                            x, y, row_loc, rack, u = None, None, None, None, None
                            if asset_tag in inventory["asset_id"].values:
                                asset_row = inventory[inventory["asset_id"] == asset_tag].iloc[0]
                                x = asset_row.get("x")
                                y = asset_row.get("y")
                                row_loc = asset_row.get("row")
                                rack = asset_row.get("rack")
                                u = asset_row.get("u")
                            
                            # Determine priority (escalate if high risk)
                            priority_map = {
                                "Critical": "Critical",
                                "High": "High",
                                "Medium": "Medium",
                                "Low": "Low"
                            }
                            final_priority = priority_map.get(row["priority"], "Medium")
                            if row["redundancy_risk"] == 2 and final_priority != "Critical":
                                final_priority = "High"  # Escalate single-homed
                            
                            # Create ticket
                            summary = f"Predictive maintenance: {row['type']} on {asset_tag}"
                            description = f"""Predictive maintenance ticket generated based on failure risk analysis.

**Details:**
* Asset: {asset_tag}
* Failure Tag: {row['failure_tag']}
* Type: {row['type']}
* Predicted Days to Fail: {row['days_to_fail']}
* Redundancy Risk: {'High (single-homed)' if row['redundancy_risk'] == 2 else 'Medium' if row['redundancy_risk'] == 1 else 'Low'}
* Priority: {final_priority}

This ticket was automatically generated based on predictive maintenance analysis."""
                            
                            # Create Jira issue
                            try:
                                issue = create_issue(
                                    summary=summary,
                                    description=description,
                                    issue_type="Task",
                                    extra_fields={"priority": {"name": final_priority}}
                                )
                                jira_key = issue['key']
                            except Exception as e:
                                jira_key = None
                                st.warning(f"Could not create Jira issue for {new_ticket_id}: {e}")
                            
                            # Create ticket row
                            new_ticket = {
                                "ticket_id": new_ticket_id,
                                "summary": summary,
                                "description": description,
                                "asset_id": asset_tag,
                                "type": row["type"],
                                "priority": final_priority,
                                "impact": 3.0 if row["redundancy_risk"] == 2 else 2.0,
                                "deadline": (datetime.now() + timedelta(days=7)).strftime("%Y-%m-%d"),
                                "status": "queued",
                                "created_by": "manager",
                                "assigned_to": "",
                                "estimated_minutes": 30,  # Default estimate
                                "requires_tools": "basic",
                                "change_window_start": datetime.now().strftime("%Y-%m-%dT00:00:00"),
                                "change_window_end": (datetime.now() + timedelta(days=30)).strftime("%Y-%m-%dT23:59:59"),
                                "x": x if pd.notna(x) else None,
                                "y": y if pd.notna(y) else None,
                                "row": row_loc if pd.notna(row_loc) else None,
                                "rack": rack if pd.notna(rack) else None,
                                "u": u if pd.notna(u) else None,
                                "tags": row["failure_tag"],
                                "created": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S.%fZ")
                            }
                            
                            # Add to tickets
                            new_ticket_df = pd.DataFrame([new_ticket])
                            existing_tickets = pd.concat([existing_tickets, new_ticket_df], ignore_index=True)
                            da.save_tickets(existing_tickets)
                            
                            # Save Jira mapping if created
                            if jira_key:
                                jira_mapping_file = Path("data") / "jira_ticket_mapping.csv"
                                if jira_mapping_file.exists():
                                    jira_mapping_df = pd.read_csv(jira_mapping_file)
                                else:
                                    jira_mapping_df = pd.DataFrame(columns=["ticket_id", "jira_key"])
                                
                                new_mapping = pd.DataFrame([{"ticket_id": new_ticket_id, "jira_key": jira_key}])
                                jira_mapping_df = pd.concat([jira_mapping_df, new_mapping], ignore_index=True)
                                jira_mapping_df.to_csv(jira_mapping_file, index=False)
                            
                            approved_count += 1
                            
                        except Exception as e:
                            errors.append(f"{asset_tag}: {str(e)}")
                    
                    # Clear cache
                    if "all_tickets_df" in st.session_state:
                        del st.session_state["all_tickets_df"]
                    
                    # Show results
                    if approved_count > 0:
                        st.success(f"✅ Approved and created {approved_count} tickets!")
                    if skipped_count > 0:
                        st.info(f"⏭️ Skipped {skipped_count} tickets (already exist)")
                    if errors:
                        st.error(f"❌ Errors: {len(errors)} tickets failed")
                        for err in errors[:5]:  # Show first 5 errors
                            st.code(err)
                    
                    st.rerun()
            
            # Individual approval (optional - can add later if needed)
            st.markdown("---")
            st.caption("💡 Use the 'Approve All' button above to create all high-risk tickets at once.")
            
            # AI Agent Section
            st.markdown("---")
            st.subheader("🤖 AI Agent — Automated Maintenance Ticket Creation")
            
            st.markdown("""
            The AI agent acts as a manager/datacenter operator to intelligently create maintenance tickets
            based on high-confidence model predictions. Only the top predictions are converted to tickets
            to minimize false alarms. When enabled, the agent automatically runs once per day.
            """)
            
            # Load agent config
            agent_config = load_agent_config()
            
            # Toggle to enable/disable agent
            agent_enabled = st.toggle(
                "🤖 Enable Auto-Run Agent",
                value=agent_config.get("enabled", False),
                help="When enabled, the agent will automatically create maintenance tickets once per day"
            )
            
            # Save enabled state if changed
            if agent_enabled != agent_config.get("enabled", False):
                agent_config["enabled"] = agent_enabled
                save_agent_config(agent_config)
                if agent_enabled:
                    st.success("✅ AI Agent enabled - will run automatically once per day")
                else:
                    st.info("ℹ️ AI Agent disabled")
                st.rerun()
            
            # Show last run status
            last_run_str = agent_config.get("last_run")
            if last_run_str:
                try:
                    from datetime import datetime
                    last_run = datetime.fromisoformat(last_run_str)
                    hours_ago = (datetime.now() - last_run).total_seconds() / 3600
                    if hours_ago < 24:
                        st.info(f"⏰ Last run: {hours_ago:.1f} hours ago (next run in {24 - hours_ago:.1f} hours)")
                    else:
                        st.warning(f"⏰ Last run: {hours_ago:.1f} hours ago (agent will run automatically on next page load)")
                except:
                    pass
            
            col1, col2 = st.columns(2)
            with col1:
                confidence_threshold = st.slider(
                    "Confidence Threshold",
                    0.70,
                    0.95,
                    float(agent_config.get("confidence_threshold", 0.75)),
                    0.05,
                    help="Minimum prediction confidence to create a ticket (higher = fewer false alarms)"
                )
            with col2:
                max_tickets = st.number_input(
                    "Max Tickets to Create",
                    min_value=1,
                    max_value=5,
                    value=int(agent_config.get("max_tickets", 2)),
                    help="Maximum number of tickets the AI agent will create (demo: 2)"
                )
            
            # Save config if settings changed
            if (confidence_threshold != agent_config.get("confidence_threshold", 0.75) or 
                max_tickets != agent_config.get("max_tickets", 2)):
                agent_config["confidence_threshold"] = confidence_threshold
                agent_config["max_tickets"] = max_tickets
                save_agent_config(agent_config)
            
            # Auto-run agent if enabled and 24+ hours have passed
            if agent_enabled and should_run_agent():
                st.info("🤖 AI Agent is running automatically (24+ hours since last run)...")
                try:
                    inventory = da.load_inventory()
                    existing_tickets = da.load_tickets()
                    
                    predictions = ai_agent_create_maintenance_tickets(
                        max_tickets=max_tickets,
                        confidence_threshold=confidence_threshold,
                        inventory_df=inventory,
                        existing_tickets_df=existing_tickets
                    )
                    
                    if predictions:
                        # Create tickets automatically
                        created_count = 0
                        for pred in predictions:
                            try:
                                # Generate ticket ID
                                max_ticket_num = 0
                                for ticket_id in existing_tickets["ticket_id"]:
                                    if ticket_id.startswith("TICK-"):
                                        try:
                                            num = int(ticket_id.split("-")[1])
                                            max_ticket_num = max(max_ticket_num, num)
                                        except:
                                            pass
                                new_ticket_id = f"TICK-{max_ticket_num + 1}"
                                
                                # Create ticket (same logic as manual run)
                                summary = f"Preventive maintenance: {pred['asset_id']} ({pred['asset_type']})"
                                description = f"""AI Agent Generated Preventive Maintenance Ticket

**Asset Information:**
* Asset ID: {pred['asset_id']}
* Asset Type: {pred['asset_type']}
* Location: Row {pred.get('row', 'N/A')}, Rack {pred.get('rack', 'N/A')}, U {pred.get('u', 'N/A')}

**Prediction Details:**
* Failure Risk Tag: {pred['failure_tag']}
* Predicted Days to Failure: {pred['days_to_fail']}
* Model Confidence: {pred['confidence']*100:.1f}%
* Redundancy Risk: {'High' if pred['redundancy_risk'] == 2 else 'Medium' if pred['redundancy_risk'] == 1 else 'Low'}

**AI Agent Reasoning:**
This ticket was automatically generated by the AI agent based on predictive maintenance analysis.
The model predicted a {pred['confidence']*100:.1f}% probability that this asset will require maintenance
within the next {pred['days_to_fail']} days. This is a preventive maintenance action to avoid
potential failures.

**Priority:** Low (preventive maintenance, not urgent)
**Action:** Schedule routine maintenance check for this asset."""
                                
                                # Create Jira issue
                                try:
                                    issue = create_issue(
                                        summary=summary,
                                        description=description,
                                        issue_type="Task",
                                        extra_fields={"priority": {"name": "Low"}}
                                    )
                                    jira_key = issue['key']
                                except Exception as e:
                                    jira_key = None
                                
                                # Create ticket row
                                new_ticket = {
                                    "ticket_id": new_ticket_id,
                                    "summary": summary,
                                    "description": description,
                                    "asset_id": pred["asset_id"],
                                    "type": "maintenance_check",
                                    "priority": "Low",
                                    "impact": 1.0,
                                    "deadline": (datetime.now() + timedelta(days=14)).strftime("%Y-%m-%d"),
                                    "status": "queued",
                                    "created_by": "ai_agent",
                                    "assigned_to": "",
                                    "estimated_minutes": 30,
                                    "requires_tools": "basic",
                                    "change_window_start": datetime.now().strftime("%Y-%m-%dT00:00:00"),
                                    "change_window_end": (datetime.now() + timedelta(days=30)).strftime("%Y-%m-%dT23:59:59"),
                                    "x": pred.get("x"),
                                    "y": pred.get("y"),
                                    "row": pred.get("row"),
                                    "rack": pred.get("rack"),
                                    "u": pred.get("u"),
                                    "tags": f"maintenance,{pred['failure_tag']},ai_generated",
                                    "created": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S.%fZ")
                                }
                                
                                # Add to tickets
                                new_ticket_df = pd.DataFrame([new_ticket])
                                existing_tickets = pd.concat([existing_tickets, new_ticket_df], ignore_index=True)
                                da.save_tickets(existing_tickets)
                                
                                # Save Jira mapping if created
                                if jira_key:
                                    jira_mapping_file = Path("data") / "jira_ticket_mapping.csv"
                                    if jira_mapping_file.exists():
                                        jira_mapping_df = pd.read_csv(jira_mapping_file)
                                    else:
                                        jira_mapping_df = pd.DataFrame(columns=["ticket_id", "jira_key"])
                                    
                                    new_mapping = pd.DataFrame([{"ticket_id": new_ticket_id, "jira_key": jira_key}])
                                    jira_mapping_df = pd.concat([jira_mapping_df, new_mapping], ignore_index=True)
                                    jira_mapping_df.to_csv(jira_mapping_file, index=False)
                                
                                created_count += 1
                            except Exception as e:
                                pass
                        
                        # Mark agent as run
                        mark_agent_run()
                        
                        # Clear cache
                        if "all_tickets_df" in st.session_state:
                            del st.session_state["all_tickets_df"]
                        
                        st.success(f"✅ AI Agent auto-created {created_count} maintenance ticket(s)!")
                        st.rerun()
                    else:
                        # No predictions, but mark as run anyway
                        mark_agent_run()
                        st.info("🤖 AI Agent ran but found no high-confidence predictions")
                except Exception as e:
                    st.warning(f"⚠️ AI Agent auto-run encountered an error: {e}")
            
            st.markdown("---")
            
            st.markdown("#### Manual Run")
            if st.button("🤖 Run AI Agent Now — Create Maintenance Tickets", type="primary"):
                with st.spinner("🤖 AI Agent analyzing assets and making predictions..."):
                    try:
                        inventory = da.load_inventory()
                        existing_tickets = da.load_tickets()
                        
                        # Run AI agent
                        predictions = ai_agent_create_maintenance_tickets(
                            max_tickets=max_tickets,
                            confidence_threshold=confidence_threshold,
                            inventory_df=inventory,
                            existing_tickets_df=existing_tickets
                        )
                        
                        if not predictions:
                            st.info("🤖 AI Agent: No high-confidence predictions found. All assets appear healthy or already have active tickets.")
                        else:
                            st.success(f"🤖 AI Agent identified {len(predictions)} high-confidence maintenance opportunities")
                            
                            # Create tickets
                            created_count = 0
                            for pred in predictions:
                                try:
                                    # Generate ticket ID
                                    max_ticket_num = 0
                                    for ticket_id in existing_tickets["ticket_id"]:
                                        if ticket_id.startswith("TICK-"):
                                            try:
                                                num = int(ticket_id.split("-")[1])
                                                max_ticket_num = max(max_ticket_num, num)
                                            except:
                                                pass
                                    new_ticket_id = f"TICK-{max_ticket_num + 1}"
                                    
                                    # Create ticket summary and description
                                    summary = f"Preventive maintenance: {pred['asset_id']} ({pred['asset_type']})"
                                    description = f"""AI Agent Generated Preventive Maintenance Ticket

**Asset Information:**
* Asset ID: {pred['asset_id']}
* Asset Type: {pred['asset_type']}
* Location: Row {pred.get('row', 'N/A')}, Rack {pred.get('rack', 'N/A')}, U {pred.get('u', 'N/A')}

**Prediction Details:**
* Failure Risk Tag: {pred['failure_tag']}
* Predicted Days to Failure: {pred['days_to_fail']}
* Model Confidence: {pred['confidence']*100:.1f}%
* Redundancy Risk: {'High' if pred['redundancy_risk'] == 2 else 'Medium' if pred['redundancy_risk'] == 1 else 'Low'}

**AI Agent Reasoning:**
This ticket was automatically generated by the AI agent based on predictive maintenance analysis.
The model predicted a {pred['confidence']*100:.1f}% probability that this asset will require maintenance
within the next {pred['days_to_fail']} days. This is a preventive maintenance action to avoid
potential failures.

**Priority:** Low (preventive maintenance, not urgent)
**Action:** Schedule routine maintenance check for this asset."""
                                    
                                    # Create Jira issue
                                    try:
                                        issue = create_issue(
                                            summary=summary,
                                            description=description,
                                            issue_type="Task",
                                            extra_fields={"priority": {"name": "Low"}}
                                        )
                                        jira_key = issue['key']
                                    except Exception as e:
                                        jira_key = None
                                        st.warning(f"Could not create Jira issue for {new_ticket_id}: {e}")
                                    
                                    # Create ticket row
                                    new_ticket = {
                                        "ticket_id": new_ticket_id,
                                        "summary": summary,
                                        "description": description,
                                        "asset_id": pred["asset_id"],
                                        "type": "maintenance_check",
                                        "priority": "Low",
                                        "impact": 1.0,  # Low impact for preventive maintenance
                                        "deadline": (datetime.now() + timedelta(days=14)).strftime("%Y-%m-%d"),
                                        "status": "queued",
                                        "created_by": "ai_agent",
                                        "assigned_to": "",
                                        "estimated_minutes": 30,
                                        "requires_tools": "basic",
                                        "change_window_start": datetime.now().strftime("%Y-%m-%dT00:00:00"),
                                        "change_window_end": (datetime.now() + timedelta(days=30)).strftime("%Y-%m-%dT23:59:59"),
                                        "x": pred.get("x"),
                                        "y": pred.get("y"),
                                        "row": pred.get("row"),
                                        "rack": pred.get("rack"),
                                        "u": pred.get("u"),
                                        "tags": f"maintenance,{pred['failure_tag']},ai_generated",
                                        "created": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S.%fZ")
                                    }
                                    
                                    # Add to tickets
                                    new_ticket_df = pd.DataFrame([new_ticket])
                                    existing_tickets = pd.concat([existing_tickets, new_ticket_df], ignore_index=True)
                                    da.save_tickets(existing_tickets)
                                    
                                    # Save Jira mapping if created
                                    if jira_key:
                                        jira_mapping_file = Path("data") / "jira_ticket_mapping.csv"
                                        if jira_mapping_file.exists():
                                            jira_mapping_df = pd.read_csv(jira_mapping_file)
                                        else:
                                            jira_mapping_df = pd.DataFrame(columns=["ticket_id", "jira_key"])
                                        
                                        new_mapping = pd.DataFrame([{"ticket_id": new_ticket_id, "jira_key": jira_key}])
                                        jira_mapping_df = pd.concat([jira_mapping_df, new_mapping], ignore_index=True)
                                        jira_mapping_df.to_csv(jira_mapping_file, index=False)
                                    
                                    created_count += 1
                                    
                                except Exception as e:
                                    st.error(f"Error creating ticket for {pred['asset_id']}: {e}")
                            
                            # Clear cache
                            if "all_tickets_df" in st.session_state:
                                del st.session_state["all_tickets_df"]
                            
                            # Mark agent as run (for auto-run tracking)
                            mark_agent_run()
                            
                            # Show results
                            st.success(f"✅ AI Agent created {created_count} maintenance ticket(s)!")
                            
                            # Show created tickets
                            if created_count > 0:
                                st.markdown("**Created Tickets:**")
                                for pred in predictions[:created_count]:
                                    st.info(f"📋 **{pred['asset_id']}** - Confidence: {pred['confidence']*100:.1f}% - {pred['failure_tag']} risk")
                            
                            st.rerun()
                            
                    except Exception as e:
                        st.error(f"❌ AI Agent error: {e}")
                        import traceback
                        st.code(traceback.format_exc())
            
            # Optional: Model performance
            with st.expander("🔮 Model Performance (Optional)"):
                try:
                    clf, metrics = train_predictive_maintenance_model(str(TRAIN_PDM_CSV))
                    if clf is not None:
                        st.success(f"✅ Model trained successfully")
                        if metrics.get("auc") is not None:
                            st.metric("AUC Score", f"{metrics['auc']:.3f}")
                        else:
                            st.info("ℹ️ AUC not available: test set contains only one class (common with small/imbalanced datasets)")
                        if metrics.get("train_size"):
                            st.caption(f"📊 Data split: {metrics['train_size']} train ({metrics['train_pct']:.1f}%), {metrics['test_size']} test ({metrics['test_pct']:.1f}%), {metrics['held_out_size']} held out ({metrics['held_out_pct']:.1f}%)")
                        st.caption("💡 The model is ready to use for predictions even if evaluation metrics aren't available.")
                    else:
                        st.info("Model training skipped (insufficient data)")
                except Exception as e:
                    st.warning(f"Could not train model: {e}")

except Exception as e:
    st.error(f"Error loading predictive maintenance data: {e}")
    import traceback
    st.code(traceback.format_exc())

