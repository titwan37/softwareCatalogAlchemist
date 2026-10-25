import sys
import logging
from pathlib import Path
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from backend.catalog.models import init_catalog_db
from backend.catalog.orchestrator import SoftwareCatalogOrchestrator

# Force logging to stream directly to the terminal
logging.basicConfig(
    level=logging.INFO, 
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)

if len(sys.argv) < 3:
    print("Usage: python scan.py <source_directory> <target_directory>")
    sys.exit(1)

source_dir = sys.argv[1]
target_dir = sys.argv[2]

# Initialize local SQLite database
db_path = Path("software_catalog.db").resolve()
engine = create_engine(f"sqlite:///{db_path}")
init_catalog_db(engine)

with Session(engine) as session:
    logging.info(f"Starting pipeline...\nSource: {source_dir}\nTarget: {target_dir}")
    
    # Execute the full pipeline without the UI
    orchestrator = SoftwareCatalogOrchestrator()
    results = orchestrator.run_full_pipeline(source_dir, target_dir, session)
    
    logging.info("Pipeline Complete!")
    logging.info(f"Summary Stats: {results.get('stats', {})}")

    # Write error report if failures occurred
    errors = results.get("stats", {}).get("errors", [])
    if errors:
        report_path = Path(target_dir) / "scan_errors_report.txt"
        
        # Ensure target directory exists
        report_path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(report_path, "w", encoding="utf-8") as f:
            f.write("=== SOFTWARE CATALOG ALCHEMIST - ERROR REPORT ===\n\n")
            for err in errors:
                if isinstance(err, dict):
                    f.write(f"FILE:  {err.get('path')}\n")
                    f.write(f"ERROR: {err.get('error')}\n\n")
                else:
                    f.write(f"ERROR: {err}\n\n")
                    
        logging.warning(f"Found {len(errors)} corrupted or locked files. Report saved to: {report_path}")