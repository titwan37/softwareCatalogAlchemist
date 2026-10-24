import os
import sqlite3
from typing import Dict, List, Optional, Tuple
from pathlib import Path

from sqlalchemy.orm import Session

from backend.catalog.scanner.crawler import RepositoryCrawler
from backend.catalog.scanner.pe_parser import extract_pe_metadata
from backend.catalog.scanner.msi_parser import extract_msi_metadata
from backend.catalog.enrichment.heuristic_matcher import HeuristicMatcher
from backend.catalog.enrichment.llm_classifier import LLMSoftwareClassifier
from backend.catalog.organizer.path_resolver import TargetPathResolver

# FTS5 Index Table Name
FTS_INDEX_NAME = "catalog_fts"


class SoftwareCatalogOrchestrator:
    """
    Orchestrates the full catalog pipeline for repository scanning and enrichment.
    Coordinates crawling, parsing, classification, indexing, and migration planning.
    """

    def __init__(self):
        self.crawler = RepositoryCrawler()
        self.heuristic_matcher = HeuristicMatcher()
        self.llm_classifier = LLMSoftwareClassifier()
        self.path_resolver = TargetPathResolver()

    def run_full_pipeline(self, source_root: str, target_root: str, db_session: Session) -> dict:
        """
        Executes the complete catalog pipeline.
        
        Args:
            source_root: Path to the directory to scan.
            target_root: Path where migration plans will be stored (used for context).
            db_session: SQLAlchemy session for database operations.
            
        Returns:
            Dictionary containing pipeline statistics and results.
        """
        stats = {
            "source_root": source_root,
            "target_root": target_root,
            "files_scanned": 0,
            "assets_registered": 0,
            "pe_files_processed": 0,
            "msi_files_processed": 0,
            "classifications_generated": 0,
            "fts_index_updated": False,
            "migration_plans_created": 0
        }

        # Step 1: Seed default taxonomies (Simulated via HeuristicMatcher internal state or DB)
        # In a real implementation, this would populate the taxonomy tables.
        self._seed_taxonomies(db_session)

        # Step 2: Run RepositoryCrawler to find binaries and register assets
        print(f"Scanning directory: {source_root}")
        file_assets = self.crawler.scan_directory(source_root, db_session)
        
        stats["files_scanned"] = len(file_assets)
        stats["assets_registered"] = len(file_assets)

        # Step 3: Dispatch parsers based on extension
        pe_files = []
        msi_files = []

        for file_path in file_assets.keys():
            ext = Path(file_path).suffix.lower()
            if ext == '.exe':
                pe_files.append(file_path)
                stats["pe_files_processed"] += 1
            elif ext in ['.msi', '.msp']:
                msi_files.append(file_path)
                stats["msi_files_processed"] += 1

        # Step 4: Run HeuristicMatcher and LLMClassifier
        classifications = []
        
        for file_path in pe_files:
            metadata = extract_pe_metadata(file_path)
            classification = self.heuristic_matcher.match(metadata)
            if not classification:
                classification = self.llm_classifier.classify_binary(metadata)
            classifications.append(classification)
            stats["classifications_generated"] += 1

        for file_path in msi_files:
            metadata = extract_msi_metadata(file_path)
            # MSI files might be handled similarly or via a specific MSI matcher if available
            # For this pipeline, we apply the same enrichment logic
            classification = self.heuristic_matcher.match(metadata)
            if not classification:
                classification = self.llm_classifier.classify_binary(metadata)
            classifications.append(classification)
            stats["classifications_generated"] += 1

        # Step 5: Update FTS5 index 'catalog_fts' via SQL execution
        self._update_fts_index(db_session, file_assets.keys(), classifications)
        stats["fts_index_updated"] = True

        # Step 6: Call TargetPathResolver to populate 'migration_plans'
        migration_plans = []
        for asset_id in file_assets.values():
            # Retrieve asset details from DB (simulated retrieval logic)
            # In a real app, this would query BinaryAsset table by id
            binary_asset = self._get_binary_asset(db_session, asset_id)
            
            if binary_asset:
                product = self._get_software_product(db_session, binary_asset.id)
                taxonomy = self._get_taxonomy(db_session, binary_asset.id)
                
                target_path, clean_filename, action = self.path_resolver.process_asset(binary_asset, product, taxonomy)
                migration_plans.append({
                    "asset_id": asset_id,
                    "source_path": file_assets.keys()[list(file_assets.values()).index(asset_id)], # Map back to path for simplicity
                    "target_path": target_path,
                    "clean_filename": clean_filename,
                    "action": action
                })
        
        stats["migration_plans_created"] = len(migration_plans)

        return stats

    def _seed_taxonomies(self, db_session: Session):
        """
        Seeds default taxonomies into the database.
        This ensures the system has categories to classify software against.
        """
        # Example: Insert a default category if empty
        try:
            db_session.execute("""
                INSERT INTO taxonomies (category_prefix, category_name, subcategory_name)
                VALUES ('software', 'applications', 'misc')
                ON CONFLICT DO NOTHING
            """)
            db_session.commit()
        except Exception as e:
            # Handle potential DB errors gracefully
            pass

    def _update_fts_index(self, db_session: Session, file_paths: Dict[str, int], classifications: List):
        """
        Updates the FTS5 index 'catalog_fts' with new binary metadata.
        """
        try:
            # Clear existing index for this session to rebuild cleanly (optional optimization)
            # db_session.execute(f"DROP INDEX {FTS_INDEX_NAME}")
            
            # Rebuild index
            db_session.execute(f"CREATE VIRTUAL TABLE IF NOT EXISTS {FTS_INDEX_NAME} USING fts5(content, content='binary_assets', content_rowid=1)")
            
            # Insert data into FTS table
            for file_path in file_paths:
                asset_id = file_paths[file_path]
                # Extract text content from classification or metadata
                text_content = " ".join([
                    str(classification.canonical_vendor) if classification else "",
                    str(classification.canonical_product) if classification else "",
                    str(file_path)
                ])
                
                db_session.execute(f"""
                    INSERT INTO {FTS_INDEX_NAME} (content_rowid, content)
                    VALUES ({asset_id}, :text)
                """, {"text": text_content})
            
            # Create FTS5 virtual table if it doesn't exist and is not already created above
            # Note: The CREATE statement above handles creation.
            db_session.commit()
        except Exception as e:
            print(f"Error updating FTS index: {e}")

    def _get_binary_asset(self, db_session: Session, asset_id: int):
        """Helper to retrieve a BinaryAsset from the database."""
        # Assuming a binary_assets table exists with columns matching the schema used in crawler.py
        try:
            result = db_session.execute("""
                SELECT * FROM binary_assets WHERE id = :id
            """, {"id": asset_id}).first()
            return result
        except Exception:
            return None

    def _get_software_product(self, db_session: Session, asset_id: int):
        """Helper to retrieve a SoftwareProduct linked to an asset."""
        try:
            # Assuming software_products table has a foreign key or link to binary_assets
            result = db_session.execute("""
                SELECT * FROM software_products WHERE id = :id
            """, {"id": asset_id}).first()
            return result
        except Exception:
            return None

    def _get_taxonomy(self, db_session: Session, asset_id: int):
        """Helper to retrieve a Taxonomy linked to an asset."""
        try:
            # Assuming taxonomies table has a link or we query the default one
            result = db_session.execute("""
                SELECT * FROM taxonomies WHERE id = :id
            """, {"id": asset_id}).first()
            return result
        except Exception:
            # Return a default taxonomy if not found
            return None
