import os
import hashlib
import sqlite3
import logging
from typing import Dict, List, Optional, Tuple
from pathlib import Path

from sqlalchemy.orm import Session
from backend.catalog.models import BinaryAsset, FileLocation


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
        self.failed_files: List[Dict[str, str]] = []  # Add this list to track bad files        

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
        logging.info(f"Discovered: {root_dir}")

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
                    logging.info(f"Scanning: {entry}") # Add this line to stream active files
                    file_hash = self._compute_sha256(entry)

                    # If the file couldn't be read (hash is None), skip to the next file
                    if file_hash is None:
                        continue
                    
                    # Check for existing hash
                    asset_id = self._handle_duplicate(entry, file_hash, db_session, root_dir)
                    
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
        
        try:
            with open(file_path, 'rb') as f:
                while chunk := f.read(self.CHUNK_SIZE):
                    sha256_hash.update(chunk)
            return sha256_hash.hexdigest()
        except OSError as e:
            err_msg = f"[Errno {e.errno}] {e.strerror}"
            logging.error(f"Unreadable file skipped (Quarantined/Corrupt): {file_path} - {e}")
            self.failed_files.append({"path": str(file_path), "error": err_msg})
            return None
        except Exception as e:
            err_msg = str(e)
            logging.error(f"Unexpected error reading {file_path}: {e}")
            self.failed_files.append({"path": str(file_path), "error": err_msg})
            return None

    def _handle_duplicate(self, file_path: Path, file_hash: str, db_session: Session, root_dir: Path) -> Optional[int]:
        """
        Check if the hash already exists in the database.
        If found, returns the existing asset ID (marking it as primary if not already).
        If new, creates a new record and returns the new asset ID.
        
        Args:
            file_path: Path to the current file.
            file_hash: The computed SHA-256 hash.
            db_session: SQLAlchemy session.
            root_dir: The root directory used for relative path calculation.
            
        Returns:
            Asset ID if found or created, None otherwise.
        """
        existing = db_session.query(BinaryAsset).filter(
            BinaryAsset.sha256_hash == file_hash
        ).first()

        try:
            parent_chain = str(file_path.parent.relative_to(root_dir))
            if parent_chain == ".":
                parent_chain = ""
        except Exception:
            parent_chain = str(file_path.parent)

        if existing:
            logging.info(f"Duplicate skipped: {file_path.name}") # Add this line
            existing_loc = db_session.query(FileLocation).filter(
                FileLocation.current_full_path == str(file_path)
            ).first()

            if not existing_loc:
                duplicate_loc = FileLocation(
                    asset_id=existing.id,
                    current_full_path=str(file_path),
                    current_filename=file_path.name,
                    parent_folder_chain=parent_chain,
                    is_primary_copy=False
                )
                db_session.add(duplicate_loc)
                db_session.commit()

            return existing.id

        # New unique hash
        try:
            file_size = file_path.stat().st_size
        except Exception:
            file_size = 0

        logging.info(f"New asset registered: {file_path.name}") # Add this line
        new_asset = BinaryAsset(
            sha256_hash=file_hash,
            file_size_bytes=file_size,
            file_extension=file_path.suffix.lower()
        )
        db_session.add(new_asset)
        db_session.flush()

        primary_loc = FileLocation(
            asset_id=new_asset.id,
            current_full_path=str(file_path),
            current_filename=file_path.name,
            parent_folder_chain=parent_chain,
            is_primary_copy=True
        )
        db_session.add(primary_loc)
        db_session.commit()

        return new_asset.id
