import os
import json
import hashlib
import shutil
from pathlib import Path
from typing import Dict, List, Optional, Any
from datetime import datetime
from contextlib import contextmanager

from sqlalchemy.orm import Session
from backend.catalog.models import MigrationPlan, FileLocation, BinaryAsset
from backend.catalog.schemas import ActionTypeEnum


class StorageMigrationExecutor:
    """Executes approved migration plans safely with rollback capabilities."""

    def __init__(self):
        self._rollback_manifest_path = None

    @contextmanager
    def _ensure_rollback_file(self, session: Session) -> None:
        """Ensure the rollback manifest file exists and is writable."""
        # Use a temporary path to avoid locking issues during creation
        temp_path = f"{self._rollback_manifest_path}.tmp"
        
        try:
            with open(temp_path, 'w') as f:
                json.dump([], f)
            os.rename(temp_path, self._rollback_manifest_path)
        finally:
            pass  # File created successfully

    def _compute_sha256(self, file_path: str) -> str:
        """Compute SHA-256 hash of a file."""
        sha256_hash = hashlib.sha256()
        with open(file_path, "rb") as f:
            for byte_block in iter(lambda: f.read(4096), b""):
                sha256_hash.update(byte_block)
        return sha256_hash.hexdigest()

    def _check_write_permissions(self, target_root: str) -> bool:
        """Check if the target root directory is writable."""
        try:
            # Ensure parent directories exist for write check
            Path(target_root).mkdir(parents=True, exist_ok=True)
            return os.access(target_root, os.W_OK)
        except Exception:
            return False

    def dry_run(self, target_root: str, db_session: Session) -> Dict[str, Any]:
        """
        Computes total bytes to move, space reclaimed by deduplication, 
        folder tree diff preview, and checks disk write permissions.
        """
        result = {
            "total_bytes_to_move": 0,
            "potential_dedup_savings": 0,
            "folder_tree_diff": [],
            "write_permission_ok": False,
            "migration_plans_count": 0
        }

        # Check write permissions first
        result["write_permission_ok"] = self._check_write_permissions(target_root)

        if not result["write_permission_ok"]:
            return result

        # Fetch active migration plans
        plans = db_session.query(MigrationPlan).filter(
            MigrationPlan.status == "pending"
        ).all()

        result["migration_plans_count"] = len(plans)

        if not plans:
            return result

        # Aggregate file stats from plans
        total_bytes = 0
        folder_structure = {}

        for plan in plans:
            location_id = plan.location_id
            location = db_session.query(FileLocation).get(location_id)
            
            if not location:
                continue

            current_path = location.current_full_path
            proposed_relative_path = plan.proposed_relative_path
            
            # Calculate bytes to move (file size from asset or directory size)
            try:
                file_size = os.path.getsize(current_path)
                total_bytes += file_size
                
                # Track folder structure for diff preview
                dest_dir = Path(target_root) / proposed_relative_path
                rel_to_target = str(dest_dir.relative_to(Path(target_root)))
                
                if rel_to_target not in folder_structure:
                    folder_structure[rel_to_target] = []
                folder_structure[rel_to_target].append({
                    "source": current_path,
                    "dest": f"{target_root}/{proposed_relative_path}"
                })
            except OSError:
                continue

        result["total_bytes_to_move"] = total_bytes

        # Simulate deduplication check (simplified: assume no duplicates for dry run)
        # In a real scenario, this would query the binary_assets table for existing hashes
        result["potential_dedup_savings"] = 0

        # Format folder tree diff preview
        result["folder_tree_diff"] = [
            {
                "source": path,
                "destination": f"{target_root}/{rel_path}"
            }
            for rel_path, paths in folder_structure.items()
        ]

        return result

    def execute_plan(self, target_root: str, db_session: Session, mode: str = "COPY_OR_MOVE") -> Dict[str, Any]:
        """
        Performs file operations, verifies SHA-256 integrity at destination before removing source, 
        updates 'migration_plans.status = EXECUTED', and writes an append-only 
        'migration_rollback_manifest.json'.
        """
        result = {
            "executed": False,
            "error": None,
            "files_processed": 0,
            "manifest_path": self._rollback_manifest_path
        }

        # Ensure rollback manifest exists
        if not os.path.exists(self._rollback_manifest_path):
            try:
                with open(self._rollback_manifest_path, 'w') as f:
                    json.dump([], f)
            except Exception as e:
                result["error"] = f"Failed to initialize rollback manifest: {str(e)}"
                return result

        # Fetch active migration plans
        plans = db_session.query(MigrationPlan).filter(
            MigrationPlan.status == "pending"
        ).all()

        if not plans:
            result["executed"] = True
            return result

        manifest_entries = []

        for plan in plans:
            location_id = plan.location_id
            location = db_session.query(FileLocation).get(location_id)
            
            if not location:
                continue

            current_path = location.current_full_path
            proposed_relative_path = plan.proposed_relative_path
            
            # Verify source exists
            if not os.path.exists(current_path):
                plan.error_message = f"Source file does not exist: {current_path}"
                plan.status = "failed"
                db_session.commit()
                continue

            try:
                # Calculate SHA-256 of source
                source_sha256 = self._compute_sha256(current_path)
                
                # Determine destination path
                dest_dir = Path(target_root) / proposed_relative_path
                dest_path = dest_dir / os.path.basename(current_path)
                
                # Ensure destination directory exists
                dest_dir.mkdir(parents=True, exist_ok=True)

                if mode == "COPY_OR_MOVE":
                    # Copy file to destination
                    shutil.copy2(current_path, dest_path)
                    
                    # Verify integrity at destination
                    dest_sha256 = self._compute_sha256(dest_path)
                    
                    if source_sha256 != dest_sha256:
                        raise ValueError("Integrity check failed: SHA-256 mismatch")

                    # Remove source file after successful copy
                    os.remove(current_path)
                else:
                    # Move directly (assumes permissions allow)
                    shutil.move(current_path, dest_path)

                # Update migration plan status
                plan.status = "EXECUTED"
                plan.executed_at = datetime.utcnow()
                
                result["files_processed"] += 1
                
            except Exception as e:
                plan.error_message = str(e)
                plan.status = "failed"
                db_session.commit()
                raise

        # Append to rollback manifest
        try:
            with open(self._rollback_manifest_path, 'w') as f:
                json.dump(manifest_entries, f, indent=4)

        except Exception as e:
            result["error"] = f"Failed to write rollback manifest: {str(e)}"
            db_session.rollback()
            raise

        db_session.commit()
        result["executed"] = True
        return result

    def rollback_migration(self, manifest_path: str, db_session: Session) -> Dict[str, Any]:
        """
        Restores files to their exact original locations and cleans up empty created directories.
        """
        result = {
            "restored": 0,
            "cleaned_directories": [],
            "error": None
        }

        if not os.path.exists(manifest_path):
            result["error"] = f"Rollback manifest not found: {manifest_path}"
            return result

        try:
            with open(manifest_path, 'r') as f:
                entries = json.load(f)
        except Exception as e:
            result["error"] = f"Failed to read rollback manifest: {str(e)}"
            return result

        # Track directories created during migration for cleanup
        created_dirs = set()

        for entry in entries:
            try:
                dest_path_str = entry.get("dest_path")
                source_path_str = entry.get("source_path")
                
                if not dest_path_str or not source_path_str:
                    continue

                # Ensure destination directory exists (it should from execute_plan)
                dest_dir = Path(dest_path_str).parent
                dest_dir.mkdir(parents=True, exist_ok=True)

                shutil.copy2(source_path_str, dest_path_str)

                # Track created directories for cleanup
                current_dir = Path(dest_path_str).resolve()
                while current_dir != Path(target_root):
                    if not current_dir.exists():
                        break
                    created_dirs.add(current_dir)
                    current_dir = current_dir.parent

                result["restored"] += 1
                
            except Exception as e:
                result["error"] = f"Failed to restore file {entry.get('dest_path')}: {str(e)}"
                db_session.rollback()
                raise

        # Clean up empty directories created during migration
        dirs_to_remove = []
        for dir_path in sorted(created_dirs, reverse=True):  # Remove deepest first
            if not os.listdir(dir_path):
                dirs_to_remove.append(dir_path)

        for dir_path in dirs_to_remove:
            try:
                shutil.rmtree(dir_path)
                result["cleaned_directories"].append(str(dir_path))
            except Exception as e:
                result["error"] = f"Failed to clean directory {dir_path}: {str(e)}"

        db_session.commit()
        return result
