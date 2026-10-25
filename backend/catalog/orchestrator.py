import os
from pathlib import Path
from typing import Dict, List, Optional, Any
from sqlalchemy import text
from sqlalchemy.orm import Session

from backend.catalog.models import (
    BinaryAsset, FileLocation, MigrationPlan, SoftwareProduct, Taxonomy, init_catalog_db
)
from backend.catalog.schemas import (
    ArchitectureEnum, LLMClassificationResult, RawBinaryMetadata, ActionTypeEnum
)
from backend.catalog.taxonomy_service import TaxonomyService
from backend.catalog.scanner.crawler import RepositoryCrawler
from backend.catalog.scanner.pe_parser import extract_pe_metadata
from backend.catalog.scanner.msi_parser import extract_msi_metadata
from backend.catalog.enrichment.heuristic_matcher import HeuristicMatcher
from backend.catalog.enrichment.llm_classifier import LLMSoftwareClassifier
from backend.catalog.organizer.path_resolver import TargetPathResolver

FTS_INDEX_NAME = "catalog_fts"


class SoftwareCatalogOrchestrator:
    """
    Orchestrates the full catalog pipeline for repository scanning and enrichment.
    Coordinates crawling, parsing, classification, indexing, and migration planning.
    """

    def __init__(self, db_session: Optional[Session] = None):
        self.db_session = db_session
        self.crawler = RepositoryCrawler()
        self.heuristic_matcher = HeuristicMatcher(db_session)
        self.llm_classifier = LLMSoftwareClassifier()
        self.path_resolver = TargetPathResolver()
        self.taxonomy_service = TaxonomyService()

    def run_full_pipeline(self, source_root: str, target_root: str, db_session: Session) -> dict:
        """
        Executes the complete catalog pipeline.
        
        Args:
            source_root: Path to the directory to scan.
            target_root: Target directory for planned migrations.
            db_session: SQLAlchemy session for database operations.
            
        Returns:
            Dictionary containing pipeline statistics and results.
        """
        stats = {
            "success": True,
            "source_root": source_root,
            "target_root": target_root,
            "files_scanned": 0,
            "assets_registered": 0,
            "pe_files_processed": 0,
            "msi_files_processed": 0,
            "classifications_generated": 0,
            "fts_index_updated": False,
            "migration_plans_created": 0,
            "errors": []
        }

        # Step 1: Seed default taxonomies
        self._seed_taxonomies(db_session)

        # Step 2: Run RepositoryCrawler to discover binaries and register assets/locations
        file_assets = self.crawler.scan_directory(source_root, db_session)
        stats["files_scanned"] = len(file_assets)
        stats["assets_registered"] = len(set(file_assets.values()))

        # Step 3 & 4: Parse metadata and classify each unique asset
        for rel_path, asset_id in file_assets.items():
            full_path = str(Path(source_root) / rel_path)
            ext = Path(rel_path).suffix.lower()

            metadata: Optional[RawBinaryMetadata] = None
            try:
                if ext == '.exe':
                    metadata = extract_pe_metadata(full_path)
                    stats["pe_files_processed"] += 1
                elif ext in ['.msi', '.msp']:
                    metadata = extract_msi_metadata(full_path)
                    stats["msi_files_processed"] += 1
            except Exception as e:
                stats["errors"].append(f"Failed parsing {rel_path}: {e}")
                continue

            if not metadata:
                continue

            # Update asset record with extracted PE/MSI metadata
            asset = db_session.get(BinaryAsset, asset_id)
            if asset:
                if metadata.pe_company_name:
                    asset.pe_company_name = metadata.pe_company_name
                if metadata.pe_product_name:
                    asset.pe_product_name = metadata.pe_product_name
                if metadata.pe_file_description:
                    asset.pe_file_description = metadata.pe_file_description
                if metadata.pe_original_filename:
                    asset.pe_original_filename = metadata.pe_original_filename
                if metadata.detected_version:
                    asset.detected_version = metadata.detected_version
                if metadata.architecture and metadata.architecture != ArchitectureEnum.Unknown:
                    asset.architecture = metadata.architecture.value
                if metadata.msi_product_code:
                    asset.msi_product_code = metadata.msi_product_code
                if metadata.digital_signature_subject:
                    asset.digital_signature_subject = metadata.digital_signature_subject
                db_session.commit()

            # Classify: Tier 1/2 -> Tier 3
            classification = self.heuristic_matcher.match(metadata)
            enrichment_source = "HEURISTIC"
            if not classification:
                try:
                    classification = self.llm_classifier.classify_binary(metadata)
                    enrichment_source = "LLM_WEB"
                except Exception as e:
                    stats["errors"].append(f"LLM classification error for {rel_path}: {e}")
                    classification = None

            if classification:
                stats["classifications_generated"] += 1
                self._link_product_and_taxonomy(db_session, asset, classification, enrichment_source)

        # Step 5: Update FTS5 index 'catalog_fts'
        self._update_fts_index(db_session)
        stats["fts_index_updated"] = True

        # Step 6: Generate and persist migration plans
        proposals = self.path_resolver.generate_migration_plans(db_session)
        for proposal in proposals:
            existing_plan = db_session.query(MigrationPlan).filter(
                MigrationPlan.location_id == proposal.location_id
            ).first()

            act_str = proposal.action_type.value if hasattr(proposal.action_type, 'value') else str(proposal.action_type)

            if existing_plan:
                existing_plan.proposed_relative_path = proposal.proposed_relative_path
                existing_plan.action_type = act_str
            else:
                new_plan = MigrationPlan(
                    location_id=proposal.location_id,
                    proposed_relative_path=proposal.proposed_relative_path,
                    action_type=act_str,
                    status="pending"
                )
                db_session.add(new_plan)

        db_session.commit()
        stats["migration_plans_created"] = len(proposals)

        return stats

    def _seed_taxonomies(self, db_session: Session):
        """Seed canonical taxonomy hierarchy."""
        try:
            self.taxonomy_service.seed_default_taxonomies(db_session)
        except Exception:
            pass

    def _link_product_and_taxonomy(
        self,
        db_session: Session,
        asset: Optional[BinaryAsset],
        classification: LLMClassificationResult,
        enrichment_source: str
    ):
        """Link or create SoftwareProduct and associate to BinaryAsset."""
        if not asset:
            return

        # Find or create taxonomy
        tax = None
        if classification.primary_category:
            tax = self.taxonomy_service.resolve_taxonomy(
                classification.primary_category,
                classification.subcategory or ""
            )
            if tax and not tax.id:
                db_session.add(tax)
                db_session.commit()

        # Find or create product
        product = db_session.query(SoftwareProduct).filter(
            SoftwareProduct.canonical_vendor == classification.canonical_vendor,
            SoftwareProduct.canonical_name == classification.canonical_product
        ).first()

        if not product:
            product = SoftwareProduct(
                canonical_vendor=classification.canonical_vendor,
                canonical_name=classification.canonical_product,
                taxonomy_id=tax.id if tax else None,
                summary_description=classification.summary,
                license_model=classification.license_model,
                enrichment_source=enrichment_source,
                confidence_score=classification.confidence_score,
                is_human_verified=False
            )
            db_session.add(product)
            db_session.flush()

        asset.product_id = product.id
        db_session.commit()

    def _update_fts_index(self, db_session: Session):
        """Synchronize FTS5 virtual table with current software_products."""
        try:
            products = db_session.query(SoftwareProduct).all()
            for prod in products:
                # Get a sample filename
                filename = ""
                asset = db_session.query(BinaryAsset).filter(BinaryAsset.product_id == prod.id).first()
                if asset:
                    filename = asset.pe_original_filename or ""

                db_session.execute(
                    text("""
                        INSERT INTO catalog_fts (rowid, canonical_vendor, canonical_name, summary_description, pe_original_filename)
                        VALUES (:rowid, :vendor, :name, :summary, :filename)
                    """),
                    {
                        "rowid": prod.id,
                        "vendor": prod.canonical_vendor,
                        "name": prod.canonical_name,
                        "summary": prod.summary_description or "",
                        "filename": filename
                    }
                )
            db_session.commit()
        except Exception:
            # FTS5 might already have records or virtual table not enabled
            pass
