import gradio as gr
import pandas as pd
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from backend.catalog.models import MigrationPlan, FileLocation

# Initialize database connection
DB_PATH = "sqlite:///software_catalog.db"
engine = create_engine(DB_PATH)

def fetch_migration_plans():
    """Fetches migration plans and source paths from the database."""
    try:
        with Session(engine) as session:
            results = session.query(
                FileLocation.current_full_path,
                MigrationPlan.proposed_relative_path,
                MigrationPlan.action_type,
                MigrationPlan.status,
                MigrationPlan.error_message
            ).join(
                MigrationPlan, FileLocation.id == MigrationPlan.location_id
            ).all()

            if not results:
                return pd.DataFrame(columns=[
                    "Source Path", "Proposed Target Path", "Action", "Status", "Error"
                ])

            df = pd.DataFrame(results, columns=[
                "Source Path", "Proposed Target Path", "Action", "Status", "Error"
            ])
            return df
    except Exception as e:
        return pd.DataFrame([{"Error": f"Database read failed: {str(e)}"}])

# Build the Gradio Interface
with gr.Blocks(title="Migration Plan Viewer") as demo:
    gr.Markdown("# 🗃️ Software Catalog Alchemist - Migration Viewer")
    gr.Markdown("Review the proposed folder restructuring and file operations before execution.")
    
    with gr.Row():
        refresh_btn = gr.Button("🔄 Refresh Data", variant="primary")
    
    plan_table = gr.Dataframe(
        value=fetch_migration_plans(),
        headers=["Source Path", "Proposed Target Path", "Action", "Status", "Error"],
        interactive=False,
        wrap=True
    )
    
    # Wire the refresh button
    refresh_btn.click(fn=fetch_migration_plans, outputs=plan_table)

if __name__ == "__main__":
    import os
    print("Launching Gradio Migration Viewer...")
    port = int(os.environ.get("GRADIO_SERVER_PORT", 7860))
    try:
        demo.launch(server_name="127.0.0.1", server_port=port, theme=gr.themes.Soft(), inbrowser=True)
    except OSError:
        demo.launch(server_name="127.0.0.1", theme=gr.themes.Soft(), inbrowser=True)