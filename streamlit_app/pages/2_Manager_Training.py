import streamlit as st
import pandas as pd
import sys
from pathlib import Path

# Add parent directory to path for imports
_root = Path(__file__).parent.parent.parent.resolve()
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

# Clear any cached modules
if "ops.models" in sys.modules:
    del sys.modules["ops.models"]
if "ops.synth_history" in sys.modules:
    del sys.modules["ops.synth_history"]
if "ops" in sys.modules:
    del sys.modules["ops"]

from auth.session import gate
from ops.models import train_tech_training_model
from ops.synth_history import synth_history, build_training_tables

st.set_page_config(page_title="Technician Training", layout="wide")

# Hide unauthorized pages from sidebar
from streamlit_app.lib.sidebar import hide_unauthorized_pages
hide_unauthorized_pages()

# Role gate
gate(["manager"])

st.title("🎓 Tech Training Recommendations")

st.markdown("""
This page identifies technicians who may need additional training for specific task types based on historical performance metrics.
""")

# Load training data
TRAIN_TECH_CSV = Path("data") / "train_tech_training.csv"
HIST_CSV = Path("data") / "history_tickets.csv"
FAIL_CSV = Path("data") / "failure_events.csv"

# Auto-generate data if missing
if not TRAIN_TECH_CSV.exists() or not HIST_CSV.exists():
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
    df = pd.read_csv(TRAIN_TECH_CSV)
    
    if df.empty:
        st.warning("⚠️ No training data available. The generated dataset is empty.")
    else:
        # Filter to only show techs who need training
        needs_training_df = df[df["needs_training"] == True].copy()
        
        if needs_training_df.empty:
            st.success("✅ All technicians are performing well! No training recommendations at this time.")
        else:
            # Sort by priority (higher rework/overrun first)
            needs_training_df["priority_score"] = (
                needs_training_df["rework"] * 0.6 + 
                needs_training_df["overrun"] * 0.4
            )
            needs_training_df = needs_training_df.sort_values("priority_score", ascending=False)
            
            st.subheader(f"📋 Training Recommendations ({len(needs_training_df)} tech×tag pairs)")
            
            # Display summary metrics
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("Techs Needing Training", len(needs_training_df["tech"].unique()))
            with col2:
                st.metric("Total Recommendations", len(needs_training_df))
            with col3:
                avg_rework = needs_training_df["rework"].mean() * 100
                st.metric("Avg Rework Rate", f"{avg_rework:.1f}%")
            
            st.markdown("---")
            
            # Create display table with reasons
            display_data = []
            for _, row in needs_training_df.iterrows():
                reasons = []
                if row["rework"] > 0.18:
                    reasons.append(f"High rework rate ({row['rework']*100:.1f}%)")
                if row["overrun"] > 0.30:
                    reasons.append(f"High overrun rate ({row['overrun']*100:.1f}%)")
                
                reason_summary = " • ".join(reasons) if reasons else "Performance below threshold"
                
                display_data.append({
                    "Technician": row["tech"],
                    "Task Tag": row["task_tag"],
                    "Tickets Handled": int(row["n"]),
                    "Rework Rate": f"{row['rework']*100:.1f}%",
                    "Overrun Rate": f"{row['overrun']*100:.1f}%",
                    "Avg ETA (min)": f"{row['avg_eta']:.1f}",
                    "Avg Completed (min)": f"{row['avg_completed']:.1f}",
                    "Tech Skill Level": int(row["tech_skill"]),
                    "Reason": reason_summary,
                })
            
            display_df = pd.DataFrame(display_data)
            st.dataframe(
                display_df,
                use_container_width=True,
                hide_index=True,
            )
            
            # Group by technician for summary view
            st.markdown("---")
            st.subheader("👤 Summary by Technician")
            
            tech_summary = needs_training_df.groupby("tech").agg({
                "task_tag": lambda x: ", ".join(x),
                "n": "sum",
                "rework": "mean",
                "overrun": "mean",
            }).reset_index()
            tech_summary.columns = ["Technician", "Tags Needing Training", "Total Tickets", "Avg Rework Rate", "Avg Overrun Rate"]
            tech_summary["Avg Rework Rate"] = tech_summary["Avg Rework Rate"].apply(lambda x: f"{x*100:.1f}%")
            tech_summary["Avg Overrun Rate"] = tech_summary["Avg Overrun Rate"].apply(lambda x: f"{x*100:.1f}%")
            tech_summary = tech_summary.sort_values("Total Tickets", ascending=False)
            
            st.dataframe(
                tech_summary,
                use_container_width=True,
                hide_index=True,
            )
            
            # Optional: Train model and show predictions
            st.markdown("---")
            with st.expander("🔮 Model Performance (Optional)"):
                try:
                    clf, metrics = train_tech_training_model(str(TRAIN_TECH_CSV))
                    if clf is not None:
                        st.success(f"✅ Model trained successfully")
                        if metrics.get("auc") is not None:
                            st.metric("AUC Score", f"{metrics['auc']:.3f}")
                        else:
                            if metrics.get("note"):
                                st.info(f"ℹ️ {metrics['note']}")
                            else:
                                st.info("ℹ️ AUC not available: test set contains only one class (common with small/imbalanced datasets)")
                        if "report" in metrics:
                            if isinstance(metrics["report"], str):
                                # Extract split info if available
                                if "Train:" in metrics["report"]:
                                    lines = metrics["report"].split("\n")
                                    split_line = lines[0]
                                    st.info(split_line)
                                    if len(lines) > 2:
                                        st.text("Classification Report:")
                                        st.code("\n".join(lines[2:]))
                                else:
                                    st.info(metrics["report"])
                            else:
                                st.text("Classification Report:")
                                st.code(metrics["report"])
                        st.caption("💡 The model is ready to use for predictions even if evaluation metrics aren't available.")
                    else:
                        st.info("Model training skipped (insufficient positive examples)")
                except Exception as e:
                    st.warning(f"Could not train model: {e}")

except Exception as e:
    st.error(f"Error loading training data: {e}")
    import traceback
    st.code(traceback.format_exc())

