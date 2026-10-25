import json
import sys
from pathlib import Path
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from backend.catalog.models import MigrationPlan, FileLocation

def export_migration_plan(output_filename="migration_plan.json"):
    engine = create_engine("sqlite:///software_catalog.db")
    export_data = []
    
    with Session(engine) as session:
        # Join FileLocation and MigrationPlan to get source and destination data
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

    output_path = Path(output_filename)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(export_data, f, indent=4)
    
    print(f"Successfully exported {len(export_data)} migration plans to {output_path.resolve()}")

if __name__ == "__main__":
    # Accept an optional filename argument, defaulting to migration_plan.json
    output_file = sys.argv[1] if len(sys.argv) > 1 else "migration_plan.json"
    export_migration_plan(output_file)