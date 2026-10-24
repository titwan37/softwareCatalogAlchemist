import re
import hashlib
import sqlite3
from typing import List, Optional, Tuple
from sqlalchemy.orm import Session
from backend.catalog.models import BinaryAsset, SoftwareProduct, FileLocation, Taxonomy
from backend.catalog.schemas import ActionTypeEnum, MigrationProposalContract

class TargetPathResolver:
    """Resolves enriched binary assets to clean target paths based on taxonomy and confidence."""
    
    def __init__(self):
        self._collision_tracker: dict[str, int] = {}  # Maps canonical path -> collision count
    
    def _sanitize_segment(self, segment: str) -> str:
        """Sanitize a single path segment by removing illegal characters and normalizing spaces."""
        if not segment:
            return ""
        
        # Replace spaces with underscores
        sanitized = segment.replace(" ", "_")
        
        # Remove or replace illegal OS characters (except underscore)
        illegal_chars = [':', '*', '?', '"', '<', '>', '|', '/', '\\']
        for char in illegal_chars:
            sanitized = sanitized.replace(char, "_")
        
        # Strip leading/trailing whitespace and underscores
        sanitized = sanitized.strip("_")
        
        return sanitized
    
    def _generate_clean_filename(self, original_name: str) -> str:
        """Generate a clean filename from the original name."""
        if not original_name:
            return "unknown"
        
        # Extract base name without extension for collision handling logic
        parts = original_name.rsplit('.', 1)
        if len(parts) == 2:
            base, ext = parts
        else:
            base = original_name
            ext = ""
        
        clean_base = self._sanitize_segment(base)
        clean_ext = self._sanitize_segment(ext)
        
        return f"{clean_base}{clean_ext}" if clean_ext else clean_base
    
    def _resolve_path_segments(self, taxonomy: Taxonomy, vendor: str, name: str, version: str, filename: str) -> Tuple[str, str]:
        """Resolve the category and subcategory segments."""
        # Sanitize taxonomy parts
        cat_prefix = self._sanitize_segment(taxonomy.category_prefix) if taxonomy.category_prefix else "misc"
        cat_name = self._sanitize_segment(taxonomy.category_name) if taxonomy.category_name else "uncategorized"
        subcat_name = self._sanitize_segment(taxonomy.subcategory_name) if taxonomy.subcategory_name else ""
        
        # Build path segments
        segments = [cat_prefix, cat_name]
        if subcat_name:
            segments.append(subcat_name)
        
        # Sanitize vendor and name parts
        clean_vendor = self._sanitize_segment(vendor)
        clean_name = self._sanitize_segment(name)
        clean_version = self._sanitize_segment(version) if version else "unknown"
        clean_filename = self._generate_clean_filename(filename)
        
        return "/".join(segments), f"{clean_vendor}/{clean_name}/{clean_version}/{clean_filename}"
    
    def _resolve_target_path(self, asset: BinaryAsset, product: SoftwareProduct, taxonomy: Taxonomy) -> Tuple[str, str]:
        """Resolve the full target path for an asset."""
        # Determine category prefix and name from taxonomy
        cat_prefix = taxonomy.category_prefix if taxonomy.category_prefix else "misc"
        cat_name = taxonomy.category_name if taxonomy.category_name else "uncategorized"
        
        # Resolve vendor/name/version parts
        clean_vendor = self._sanitize_segment(product.canonical_vendor)
        clean_name = self._sanitize_segment(product.canonical_name)
        clean_version = self._sanitize_segment(asset.detected_version) if asset.detected_version else "unknown"
        clean_filename = self._generate_clean_filename(asset.pe_original_filename or product.canonical_name)
        
        # Construct the full path string
        category_path = f"{cat_prefix}_{cat_name}"
        vendor_name_path = f"{clean_vendor}/{clean_name}/{clean_version}/{clean_filename}"
        
        return f"{category_path}/{vendor_name_path}", clean_filename
    
    def _handle_confidence_and_dups(self, asset: BinaryAsset, product: SoftwareProduct, taxonomy: Taxonomy) -> Tuple[str, str, Optional[ActionTypeEnum]]:
        """Handle low confidence scores and duplicate detection."""
        action = None
        
        # Rule 1: Low confidence check (confidence_score < 0.70)
        if asset.confidence_score is not None and asset.confidence_score < 0.70:
            return "99_Unclassified_Orphan_Binaries", f"{self._sanitize_segment(asset.pe_original_filename or product.canonical_name)}", action
        
        # Rule 2: Duplicate check (is_primary_copy == 0)
        if asset.is_primary_copy is not None and not asset.is_primary_copy:
            return "99_Unclassified_Orphan_Binaries", f"{self._sanitize_segment(asset.pe_original_filename or product.canonical_name)}", action
        
        # Default action for valid assets
        return "main_catalog", f"{self._sanitize_segment(asset.pe_original_filename or product.canonical_name)}", None
    
    def _resolve_collision(self, canonical_path: str, filename: str) -> Tuple[str, str]:
        """Resolve filename collisions by appending a hash suffix."""
        # Check if this path already exists in our tracker
        if canonical_path not in self._collision_tracker:
            self._collision_tracker[canonical_path] = 0
        
        count = self._collision_tracker[canonical_path]
        
        # Generate unique filename using short hash suffix
        base, ext = filename.rsplit('.', 1) if '.' in filename else (filename, "")
        suffix = f"_{count + 1}"
        new_filename = f"{base}{suffix}.{ext}" if ext else f"{base}{suffix}"
        
        self._collision_tracker[canonical_path] += 1
        
        return canonical_path, new_filename
    
    def process_asset(self, asset: BinaryAsset, product: SoftwareProduct, taxonomy: Taxonomy) -> Tuple[str, str, Optional[ActionTypeEnum]]:
        """Process a single asset to determine target path and action."""
        # Step 1: Resolve base path segments
        category_path, vendor_name_path = self._resolve_target_path(asset, product, taxonomy)
        
        # Step 2: Handle confidence and duplicates
        low_conf_path, clean_filename, default_action = self._handle_confidence_and_dups(asset, product, taxonomy)
        
        # If low confidence or duplicate, return early with specific path
        if default_action:
            return low_conf_path, clean_filename, default_action
        
        # Step 3: Resolve collision for main catalog
        canonical_path = f"{category_path}/{vendor_name_path}"
        resolved_path, final_filename = self._resolve_collision(canonical_path, clean_filename)
        
        return resolved_path, final_filename, None
    
    def generate_migration_plans(self, db_session: Session) -> List[MigrationProposalContract]:
        """Generate migration plans for all assets in the database."""
        proposals = []
        
        # Query all assets with their related products and taxonomies
        query = db_session.query(BinaryAsset).join(SoftwareProduct).join(Taxonomy)
        results = query.all()
        
        for asset, product, taxonomy in results:
            target_path, clean_filename, action_enum = self.process_asset(asset, product, taxonomy)
            
            # Determine action type string
            if action_enum is None:
                action_type_str = "MOVE"  # Default to MOVE for valid assets
            else:
                action_type_str = action_enum.value
            
            proposal = MigrationProposalContract(
                location_id=asset.id,
                current_full_path=f"/assets/{asset.id}",  # Placeholder for actual path logic if needed
                proposed_relative_path=target_path,
                action_type=action_type_str,
                confidence_score=asset.confidence_score or 0.5
            )
            
            proposals.append(proposal)
        
        return proposals


def generate_migration_plans(db_session: Session) -> List[MigrationProposalContract]:
    """Factory function to generate migration plans using the resolver."""
    resolver = TargetPathResolver()
    return resolver.generate_migration_plans(db_session)
