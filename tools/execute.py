import sys
import logging
from pathlib import Path
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from backend.catalog.organizer.executor import StorageMigrationExecutor

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s", handlers=[logging.StreamHandler(sys.stdout)])

if len(sys.argv) < 2:
    print("Usage: python execute.py <target_directory>")
    sys.exit(1)

target_dir = sys.argv[1]
engine = create_engine("sqlite:///software_catalog.db")

with Session(engine) as session:
    logging.info(f"Executing approved migration plans into {target_dir}...")
    
    executor = StorageMigrationExecutor()
    # Explicitly set the rollback manifest path to avoid NoneType errors
    executor._rollback_manifest_path = str(Path(target_dir) / "migration_rollback_manifest.json")
    
    result = executor.execute_plan(target_dir, session)
    logging.info(f"Execution complete. Result: {result}")