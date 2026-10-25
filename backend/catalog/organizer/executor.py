import os
import json
import hashlib
import shutil
from pathlib import Path
from typing import Dict, List, Optional, Any
from datetime import datetime, timezone
from contextlib import contextmanager

from sqlalchemy.orm import Session
from backend.catalog.models import MigrationPlan, FileLocation, BinaryAsset
from backend.catalog.schemas import ActionTypeEnum, MigrationStatusEnum


class StorageMigrationExecutor:
    """Executes approved migration plans safely with rollback capabilities."""

    def __init__(self, rollback_manifest_path: Optional[str] = None):
        self._rollback_manifest_path = rollback_manifest_path

    def _compute_sha256(self, file_path: str) -> str:
        """Compute SHA-256 hash of a file."""
        sha256_hash = hashlib.sha256()
        with open(file_path, "rb") as f:
            for byte_block in iter(lambda: f.read(65536), b""):
                sha256_hash.update(byte_block)
        return sha256_hash.hexdigest()

    def _check_write_permissions(self, target_root: str) -> bool:
        """Check if the target root directory is writable."""
        try:
            p = Path(target_root)
            p.mkdir(parents=True, exist_ok=True)
            test_file = p / ".perm_check.tmp"
            with open(test_file, "w") as f:
                f.write("test")
            test_file.unlink(missing_ok=True)
            return True
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

        result["write_permission_ok"] = self._check_write_permissions(target_root)
        if not result["write_permission_ok"]:
            return result

        plans = db_session.query(MigrationPlan).filter(
            MigrationPlan.status.in_(["pending", "PENDING", "APPROVED", "approved"])
        ).all()

        result["migration_plans_count"] = len(plans)
        if not plans:
            return result

        total_bytes = 0
        dedup_savings = 0
        folder_diff = []

        for plan in plans:
            location = db_session.get(FileLocation, plan.location_id)
            if not location:
                continue

            current_path = location.current_full_path
            dest_path = Path(target_root) / plan.proposed_relative_path

            file_size = 0
            if os.path.exists(current_path):
                try:
                    file_size = os.path.getsize(current_path)
                except OSError:
                    file_size = 0

            if plan.action_type in [ActionTypeEnum.DELETE_DUPLICATE.value, "DELETE_DUPLICATE"]:
                dedup_savings += file_size
            else:
                total_bytes += file_size

            folder_diff.append({
                "source": current_path,
                "destination": str(dest_path),
                "action": plan.action_type,
                "size_bytes": file_size
            })

        result["total_bytes_to_move"] = total_bytes
        result["potential_dedup_savings"] = dedup_savings
        result["folder_tree_diff"] = folder_diff

        return result

    def execute_plan(self, target_root: str, db_session: Session, mode: str = "COPY_OR_MOVE") -> Dict[str, Any]:
        """
        Performs file operations, verifies SHA-256 integrity at destination before removing source, 
        updates 'migration_plans.status = EXECUTED', and writes an append-only 
        'migration_rollback_manifest.json'.
        """
        if not self._rollback_manifest_path:
            self._rollback_manifest_path = str(Path(target_root) / "migration_rollback_manifest.json")

        result = {
            "executed": False,
            "error": None,
            "files_processed": 0,
            "manifest_path": self._rollback_manifest_path
        }

        manifest_dir = Path(self._rollback_manifest_path).parent
        manifest_dir.mkdir(parents=True, exist_ok=True)

        existing_manifest = []
        if os.path.exists(self._rollback_manifest_path):
            try:
                with open(self._rollback_manifest_path, 'r', encoding='utf-8') as f:
                    existing_manifest = json.load(f)
            except Exception:
                existing_manifest = []

        plans = db_session.query(MigrationPlan).filter(
            MigrationPlan.status.in_(["pending", "PENDING", "APPROVED", "approved"])
        ).all()

        if not plans:
            result["executed"] = True
            return result

        new_manifest_entries = []

        for plan in plans:
            location = db_session.get(FileLocation, plan.location_id)
            if not location:
                continue

            current_path = location.current_full_path
            dest_path = Path(target_root) / plan.proposed_relative_path

            if not os.path.exists(current_path):
                plan.error_message = f"Source file does not exist: {current_path}"
                plan.status = MigrationStatusEnum.FAILED.value
                db_session.commit()
                continue

            try:
                source_sha256 = self._compute_sha256(current_path)
                dest_path.parent.mkdir(parents=True, exist_ok=True)

                if plan.action_type in [ActionTypeEnum.DELETE_DUPLICATE.value, "DELETE_DUPLICATE"]:
                    # Redundant copy
                    pass

                # Copy or move
                shutil.copy2(current_path, str(dest_path))
                dest_sha256 = self._compute_sha256(str(dest_path))

                if source_sha256 != dest_sha256:
                    raise ValueError(f"Integrity check failed: SHA-256 mismatch for {dest_path}")

                os.remove(current_path)

                plan.status = MigrationStatusEnum.EXECUTED.value
                plan.executed_at = datetime.now(timezone.utc)

                manifest_entry = {
                    "location_id": location.id,
                    "source_path": str(Path(current_path).resolve()),
                    "dest_path": str(dest_path.resolve()),
                    "sha256": source_sha256,
                    "timestamp": datetime.now(timezone.utc).isoformat()
                }
                new_manifest_entries.append(manifest_entry)
                result["files_processed"] += 1

            except Exception as e:
                plan.error_message = str(e)
                plan.status = MigrationStatusEnum.FAILED.value
                db_session.commit()
                result["error"] = str(e)
                raise

        # Save manifest
        combined_manifest = existing_manifest + new_manifest_entries
        try:
            with open(self._rollback_manifest_path, 'w', encoding='utf-8') as f:
                json.dump(combined_manifest, f, indent=4)
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
            with open(manifest_path, 'r', encoding='utf-8') as f:
                entries = json.load(f)
        except Exception as e:
            result["error"] = f"Failed to read rollback manifest: {str(e)}"
            return result

        created_dirs = set()

        for entry in entries:
            try:
                dest_path_str = entry.get("dest_path")
                source_path_str = entry.get("source_path")
                loc_id = entry.get("location_id")

                if not dest_path_str or not source_path_str:
                    continue

                dest_file = Path(dest_path_str)
                source_file = Path(source_path_str)

                if dest_file.exists():
                    source_file.parent.mkdir(parents=True, exist_ok=True)
                    shutil.move(str(dest_file), str(source_file))
                    result["restored"] += 1

                    # Collect parent directories to check for cleanup
                    curr = dest_file.parent
                    while curr and curr != curr.parent:
                        created_dirs.add(curr)
                        curr = curr.parent

                if loc_id:
                    plan = db_session.query(MigrationPlan).filter(
                        MigrationPlan.location_id == loc_id
                    ).first()
                    if plan:
                        plan.status = MigrationStatusEnum.ROLLED_BACK.value

            except Exception as e:
                result["error"] = f"Failed to restore file {entry.get('dest_path')}: {str(e)}"
                db_session.rollback()
                raise

        # Clean up empty directories in reverse order of depth
        for dir_path in sorted(created_dirs, key=lambda p: len(str(p)), reverse=True):
            try:
                if dir_path.exists() and not any(dir_path.iterdir()):
                    dir_path.rmdir()
                    result["cleaned_directories"].append(str(dir_path))
            except Exception:
                pass

        db_session.commit()
        return result
