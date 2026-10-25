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
    logging.info(f"Summary Stats: {results.get('stats', results)}")