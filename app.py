import gradio as gr
import pandas as pd
import json
from pathlib import Path
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from backend.catalog.models import MigrationPlan, FileLocation, init_catalog_db
from backend.catalog.orchestrator import SoftwareCatalogOrchestrator
from backend.catalog.organizer.executor import StorageMigrationExecutor

import threading
import queue
import time

DB_PATH = "sqlite:///software_catalog.db"

# Global scanning control state
_scan_thread: threading.Thread = None
_scan_stop_event = threading.Event()
_scan_log_queue = queue.Queue()


def run_scan_generator(source_dir, target_dir):
    """
    Generator that launches the catalog orchestrator in a separate thread,
    yielding live feedback and progress lines to the Gradio UI in real time,
    while allowing the operation to be cleanly cancelled.
    """
    global _scan_thread, _scan_stop_event, _scan_log_queue

    if not source_dir or not target_dir:
        yield "❌ Error: Please provide both source and target directories."
        return

    # If already running, prevent overlap
    if _scan_thread and _scan_thread.is_alive():
        yield "⚠️ A scan is already in progress. Click 'Stop Scan' or wait for it to finish."
        return

    _scan_stop_event.clear()
    while not _scan_log_queue.empty():
        try:
            _scan_log_queue.get_nowait()
        except queue.Empty:
            break

    log_history = []

    def _worker():
        try:
            engine = create_engine(DB_PATH)
            init_catalog_db(engine)
            with Session(engine) as session:
                def on_progress(msg: str):
                    _scan_log_queue.put(("LOG", msg))

                orchestrator = SoftwareCatalogOrchestrator()
                _scan_log_queue.put(("LOG", f"🚀 Starting pipeline scan...\nSource: {source_dir}\nTarget: {target_dir}\n"))
                
                results = orchestrator.run_full_pipeline(
                    source_dir,
                    target_dir,
                    session,
                    progress_callback=on_progress,
                    stop_event=_scan_stop_event
                )
                stats = results if "files_scanned" in results else results.get("stats", {})
                errors = stats.get("errors", [])
                
                if stats.get("cancelled"):
                    _scan_log_queue.put(("DONE", "🛑 Scan was cancelled by user."))
                    return

                # Generate local error report if needed
                if errors:
                    report_path = Path(target_dir) / "scan_errors_report.txt"
                    report_path.parent.mkdir(parents=True, exist_ok=True)
                    with open(report_path, "w", encoding="utf-8") as f:
                        f.write("=== SOFTWARE CATALOG ALCHEMIST - ERROR REPORT ===\n\n")
                        for err in errors:
                            f.write(f"{err}\n\n")

                summary = (
                    f"\n✅ Scan Complete!\n\n"
                    f"Summary Statistics:\n{json.dumps(stats, indent=2)}\n\n"
                    f"Errors encountered: {len(errors)}"
                )
                _scan_log_queue.put(("DONE", summary))
        except Exception as e:
            _scan_log_queue.put(("ERROR", f"\n❌ Scan failed with error: {str(e)}"))

    _scan_thread = threading.Thread(target=_worker, daemon=True)
    _scan_thread.start()

    yield "⏳ Initializing scan worker thread...\n"

    # Stream queue items back to Gradio UI until thread finishes and queue is drained
    while _scan_thread.is_alive() or not _scan_log_queue.empty():
        got_item = False
        try:
            kind, text = _scan_log_queue.get(timeout=0.2)
            got_item = True
            log_history.append(text)
            # Keep log buffer responsive (last 200 lines)
            if len(log_history) > 200:
                log_history = log_history[-200:]
            yield "\n".join(log_history)
        except queue.Empty:
            pass

        if not got_item and _scan_stop_event.is_set():
            break

    # Final drain
    while not _scan_log_queue.empty():
        try:
            _, text = _scan_log_queue.get_nowait()
            log_history.append(text)
        except queue.Empty:
            break

    yield "\n".join(log_history)


def stop_scan():
    """Signals the active scan thread to halt gracefully."""
    global _scan_stop_event, _scan_thread
    if _scan_thread and _scan_thread.is_alive():
        _scan_stop_event.set()
        return "🛑 Stop signal sent. Halting scanner thread..."
    return "ℹ️ No scan thread is currently running."

# --- Functions for Tab 2: Migration Viewer ---
def fetch_migration_plans():
    try:
        engine = create_engine(DB_PATH)
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
                return pd.DataFrame(columns=["Source Path", "Proposed Target Path", "Action", "Status", "Error"])

            df = pd.DataFrame(results, columns=["Source Path", "Proposed Target Path", "Action", "Status", "Error"])
            return df
    except Exception as e:
        return pd.DataFrame([{"Error": f"Database read failed: {str(e)}"}])

# --- Functions for Tab 3: Executor ---
def run_execute(target_dir):
    if not target_dir:
        return "Error: Please provide the target directory."
    try:
        engine = create_engine(DB_PATH)
        with Session(engine) as session:
            executor = StorageMigrationExecutor()
            executor._rollback_manifest_path = str(Path(target_dir) / "migration_rollback_manifest.json")
            result = executor.execute_plan(target_dir, session)
            return f"Execution Complete!\n\nResult:\n{json.dumps(result, indent=2)}"
    except Exception as e:
        return f"Execution failed: {str(e)}"

# --- Functions for Tab 4: JSON Export ---
def export_json(filename):
    if not filename:
        filename = "migration_plan.json"
    try:
        engine = create_engine(DB_PATH)
        export_data = []
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

            for row in results:
                export_data.append({
                    "source_path": row.current_full_path,
                    "proposed_target_path": row.proposed_relative_path,
                    "action": row.action_type,
                    "status": row.status,
                    "error": row.error_message
                })

        output_path = Path(filename).resolve()
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(export_data, f, indent=4)
        
        return f"Successfully exported {len(export_data)} records.", str(output_path)
    except Exception as e:
        return f"Export failed: {str(e)}", None

# --- Gradio UI Assembly ---
with gr.Blocks(title="Software Catalog Alchemist") as demo:
    gr.Markdown("# 🗃️ Software Catalog Alchemist")
    gr.Markdown("Unified dashboard for scanning, reviewing, executing, and exporting your software catalog operations.")

    with gr.Tabs():
        # Tab 1: Scanner
        with gr.TabItem("1. Scanner"):
            gr.Markdown("### Run Pipeline Scan")
            with gr.Row():
                src_input = gr.Textbox(label="Source Directory", value="S:\\")
                tgt_input = gr.Textbox(label="Target Directory", value="S:\\CleanRepo")
            with gr.Row():
                scan_btn = gr.Button("🚀 Run Full Scan", variant="primary")
                stop_btn = gr.Button("🛑 Stop Scan", variant="stop")
            scan_out = gr.Textbox(label="Live Scanner Feedback", lines=14, autoscroll=True)
            
            # Start scan streaming generator
            scan_event = scan_btn.click(fn=run_scan_generator, inputs=[src_input, tgt_input], outputs=scan_out)
            # Stop scan signal
            stop_btn.click(fn=stop_scan, outputs=scan_out, cancels=[scan_event])

        # Tab 2: Migration Viewer
        with gr.TabItem("2. Migration Viewer"):
            gr.Markdown("### Review Proposed Restructuring")
            refresh_btn = gr.Button("🔄 Refresh Data", variant="primary")
            plan_table = gr.Dataframe(
                value=fetch_migration_plans(),
                headers=["Source Path", "Proposed Target Path", "Action", "Status", "Error"],
                interactive=False,
                wrap=True
            )
            refresh_btn.click(fn=fetch_migration_plans, outputs=plan_table)

        # Tab 3: Executor
        with gr.TabItem("3. Executor"):
            gr.Markdown("### Execute Migration Plans")
            exec_tgt_input = gr.Textbox(label="Target Directory (must match scanner target)", value="S:\\CleanRepo")
            exec_btn = gr.Button("⚡ Execute Reorganization", variant="primary")
            exec_out = gr.Textbox(label="Execution Output", lines=12)
            exec_btn.click(fn=run_execute, inputs=[exec_tgt_input], outputs=exec_out)

        # Tab 4: JSON Export
        with gr.TabItem("4. JSON Export"):
            gr.Markdown("### Export Database to JSON")
            filename_input = gr.Textbox(label="Output Filename", value="migration_plan.json")
            export_btn = gr.Button("💾 Export JSON", variant="primary")
            export_msg = gr.Textbox(label="Export Status")
            export_file = gr.File(label="Download File")
            export_btn.click(fn=export_json, inputs=[filename_input], outputs=[export_msg, export_file])

if __name__ == "__main__":
    import os
    port = int(os.environ.get("GRADIO_SERVER_PORT", 7860))
    try:
        demo.launch(server_name="127.0.0.1", server_port=port, theme=gr.themes.Soft(), inbrowser=True)
    except OSError:
        # Fallback to dynamic open port if 7860 is occupied
        print(f"Port {port} is occupied, launching on next available port...")
        demo.launch(server_name="127.0.0.1", theme=gr.themes.Soft(), inbrowser=True)