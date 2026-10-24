import os
import hashlib
import sqlite3
from typing import Dict, List, Optional, Tuple
from pathlib import Path

from sqlalchemy.orm import Session


class RepositoryCrawler:
    """
    Recursively scans a directory for binary files (.exe, .msi, .msp),
    computes SHA-256 hashes using chunked reads, and registers them in the database.
    Handles deduplication by tracking primary copies based on path length.
    """

    SUPPORTED_EXTENSIONS = {'.exe', '.msi', '.msp'}
    CHUNK_SIZE = 1024 * 1024  # 1MB chunks for memory efficiency

    def __init__(self):
        self._seen_hashes: set[str] = set()

    def scan_directory(self, root_path: str, db_session: Session) -> Dict[str, int]:
        """
        Recursively scans the directory tree starting at root_path.
        
        Args:
            root_path: The absolute path to the root directory to scan.
            db_session: SQLAlchemy session for database operations.
            
        Returns:
            Dictionary mapping file paths (relative to root) to their asset IDs.
        """
        results = {}

        # Ensure root exists and is a directory
        if not os.path.exists(root_path):
            return results

        root_dir = Path(root_path).resolve()

        def _walk(current_path: Path, relative_prefix: str) -> None:
            """Recursive helper to walk the directory tree."""
            try:
                entries = sorted(current_path.iterdir())
            except PermissionError:
                return

            for entry in entries:
                if entry.is_dir():
                    # Construct breadcrumb chain without drive letter or root path
                    rel_part = str(entry.relative_to(root_dir))
                    new_breadcrumb = f"{relative_prefix}/{rel_part}" if relative_prefix else rel_part
                    
                    _walk(entry, new_breadcrumb)
                elif entry.is_file() and entry.suffix.lower() in self.SUPPORTED_EXTENSIONS:
                    file_hash = self._compute_sha256(entry)
                    
                    # Check for existing hash
                    asset_id = self._handle_duplicate(file_hash, db_session)
                    
                    if asset_id is not None:
                        results[str(entry.relative_to(root_dir))] = asset_id

        _walk(root_dir, "")
        return results

    def _compute_sha256(self, file_path: Path) -> str:
        """
        Compute SHA-256 hash of a file using 1MB chunked reads.
        
        Args:
            file_path: Path to the file.
            
        Returns:
            Hexadecimal SHA-256 string.
        """
        sha256_hash = hashlib.sha256()
        
        with open(file_path, 'rb') as f:
            while chunk := f.read(self.CHUNK_SIZE):
                sha256_hash.update(chunk)
        
        return sha256_hash.hexdigest()

    def _handle_duplicate(self, file_hash: str, db_session: Session) -> Optional[int]:
        """
        Check if the hash already exists in the database.
        If found, returns the existing asset ID (marking it as primary if not already).
        If new, creates a new record and returns the new asset ID.
        
        Args:
            file_hash: The computed SHA-256 hash.
            db_session: SQLAlchemy session.
            
        Returns:
            Asset ID if found or created, None otherwise.
        """
        # Check existing records for this hash
        existing = db_session.query("binary_assets").filter(
            "binary_assets.sha256_hash" == file_hash
        ).first()

        if existing:
            # If a record exists, ensure the primary copy is marked correctly.
            # We assume the first occurrence found during scan (shortest path) is primary.
            # However, to be safe against re-scans of same files, we check file_locations.
            locations = db_session.query("file_locations").filter(
                "file_locations.asset_id" == existing.id,
                "file_locations.is_primary_copy" == True
            ).first()

            if not locations:
                # No primary copy found for this asset yet, promote the current one
                db_session.execute("""
                    UPDATE file_locations 
                    SET is_primary_copy = 1 
                    WHERE asset_id = :asset_id
                """, {"asset_id": existing.id})
            
            return existing.id

        # New hash, create record
        new_asset = db_session.execute("""
            INSERT INTO binary_assets (sha256_hash) VALUES (:hash)
        """, {"hash": file_hash}).fetchone()[0]

        # Register the physical path in file_locations
        # Extract filename and parent folder chain
        rel_path = str(Path(file_path).relative_to(root_dir)) if 'root_dir' in dir() else str(file_path.relative_to(root_dir))
        filename = Path(file_path).name
        parent_chain = str(Path(file_path).parent.relative_to(root_dir))

        db_session.execute("""
            INSERT INTO file_locations (asset_id, current_full_path, current_filename, parent_folder_chain)
            VALUES (:asset_id, :full_path, :filename, :chain)
        """, {
            "asset_id": new_asset,
            "full_path": str(file_path),
            "filename": filename,
            "chain": parent_chain
        })

        return new_asset
