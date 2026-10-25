import re
import hashlib
from typing import List, Optional, Tuple, Dict
from sqlalchemy.orm import Session
from backend.catalog.models import BinaryAsset, SoftwareProduct, FileLocation, Taxonomy
from backend.catalog.schemas import ActionTypeEnum, MigrationProposalContract


class TargetPathResolver:
    """Resolves enriched binary assets to clean target paths based on taxonomy and confidence."""
    
    def __init__(self, root_prefix: Optional[str] = None):
        self._collision_tracker: Dict[str, int] = {}  # Maps canonical path -> collision count
        self.root_prefix = root_prefix
    
    def _sanitize_segment(self, segment: Optional[str]) -> str:
        """Sanitize a single path segment by removing illegal characters and normalizing spaces."""
        if not segment:
            return ""
        
        # Replace spaces with underscores
        sanitized = segment.replace(" ", "_")
        illegal_chars = [':', '*', '?', '"', '<', '>', '|', '/', '\\']
        for char in illegal_chars:
            sanitized = sanitized.replace(char, "_")
        
        # Collapse repeated underscores and strip ends
        sanitized = re.sub(r'_+', '_', sanitized).strip("_")
        return sanitized
    
    def _sanitize_folder_chain(self, chain: Optional[str]) -> str:
        """Sanitize a multi-level folder chain while preserving its progressive directory depth."""
        if not chain:
            return ""
        # Normalize separators
        normalized = chain.replace("\\", "/").strip("/")
        segments = [self._sanitize_segment(s) for s in normalized.split("/") if s]
        return "/".join([s for s in segments if s])
    
    def _generate_clean_filename(self, original_name: Optional[str]) -> str:
        """Generate a clean filename with extension preserved."""
        if not original_name:
            return "unknown.bin"
        
        parts = original_name.rsplit('.', 1)
        if len(parts) == 2:
            base, ext = parts
        else:
            base = original_name
            ext = ""
        
        clean_base = self._sanitize_segment(base) or "file"
        clean_ext = self._sanitize_segment(ext).lower()
        
        return f"{clean_base}.{clean_ext}" if clean_ext else clean_base
    
    def _resolve_collision(self, canonical_path: str, filename: str) -> Tuple[str, str]:
        """Resolve filename collisions by appending an index suffix."""
        if canonical_path not in self._collision_tracker:
            self._collision_tracker[canonical_path] = 0
            return canonical_path, filename
        
        self._collision_tracker[canonical_path] += 1
        count = self._collision_tracker[canonical_path]
        
        base, ext = filename.rsplit('.', 1) if '.' in filename else (filename, "")
        suffix = f"_{count}"
        new_filename = f"{base}{suffix}.{ext}" if ext else f"{base}{suffix}"
        
        if '/' in canonical_path:
            parent_path, _ = canonical_path.rsplit('/', 1)
            new_path = f"{parent_path}/{new_filename}"
        else:
            new_path = new_filename
            
        return new_path, new_filename

    def resolve_full_path(self, root_prefix: Optional[str], relative_path: str) -> str:
        """Combine a root prefix (UNC or local path) with relative path respecting OS conventions."""
        root = root_prefix or self.root_prefix or ""
        if not root:
            return relative_path

        # If root uses backslashes (like \\Synas or C:\), return formatted with backslashes
        if "\\" in root or root.startswith("//"):
            clean_root = root.rstrip("\\/")
            clean_rel = relative_path.replace("/", "\\").lstrip("\\")
            return f"{clean_root}\\{clean_rel}"
        else:
            clean_root = root.rstrip("/")
            clean_rel = relative_path.replace("\\", "/").lstrip("/")
            return f"{clean_root}/{clean_rel}"
    
    def process_asset(
        self,
        asset: BinaryAsset,
        product: Optional[SoftwareProduct] = None,
        taxonomy: Optional[Taxonomy] = None,
        location: Optional[FileLocation] = None
    ) -> Tuple[str, str, ActionTypeEnum]:
        """Process a single asset to determine progressive target path and action."""
        confidence = product.confidence_score if product and product.confidence_score is not None else 0.5
        is_primary = location.is_primary_copy if location and location.is_primary_copy is not None else True
        
        filename = (
            (asset.pe_original_filename if asset and asset.pe_original_filename else None)
            or (location.current_filename if location else None)
            or (product.canonical_name if product else "binary.exe")
        )
        clean_filename = self._generate_clean_filename(filename)

        # Rule: Duplicate check
        if not is_primary:
            parent_chain = self._sanitize_folder_chain(location.parent_folder_chain) if location and location.parent_folder_chain else "duplicates"
            target_path = f"99_Unclassified_Orphan_Binaries/{parent_chain}/{clean_filename}" if parent_chain else f"99_Unclassified_Orphan_Binaries/{clean_filename}"
            return target_path, clean_filename, ActionTypeEnum.DELETE_DUPLICATE

        # Rule: Low confidence check (< 0.70)
        if confidence < 0.70 or product is None or taxonomy is None:
            # Flatten parent folder chain with underscores for orphan folder names (e.g. SoftwareTools_Tools)
            parent_chain = self._sanitize_segment(location.parent_folder_chain) if location and location.parent_folder_chain else ""
            if parent_chain:
                target_path = f"99_Unclassified_Orphan_Binaries/{parent_chain}/{clean_filename}"
            else:
                target_path = f"99_Unclassified_Orphan_Binaries/{clean_filename}"
            return target_path, clean_filename, ActionTypeEnum.SKIP_LOW_CONFIDENCE

        # Rule: Progressive & Rational Taxonomy Hierarchy
        cat_prefix = taxonomy.category_prefix or ""
        cat_name = taxonomy.category_name or ""
        subcat_name = taxonomy.subcategory_name or ""

        # Progressive category path:
        # If prefix already contains the category name or starts with category code (e.g. "08_Gaming_and_Entertainment")
        # use cat_prefix directly
        if cat_prefix:
            category_segment = self._sanitize_segment(cat_prefix)
        else:
            category_segment = self._sanitize_segment(cat_name) or "misc"

        category_parts = [category_segment]
        if subcat_name:
            category_parts.append(self._sanitize_segment(subcat_name))
        category_hierarchy = "/".join(category_parts)

        clean_vendor = self._sanitize_segment(product.canonical_vendor) or "Unknown_Vendor"
        clean_name = self._sanitize_segment(product.canonical_name) or "Unknown_Product"
        clean_version = self._sanitize_segment(asset.detected_version) if asset and asset.detected_version else "1.0.0"

        canonical_path = f"{category_hierarchy}/{clean_vendor}/{clean_name}/{clean_version}/{clean_filename}"
        
        resolved_path, final_filename = self._resolve_collision(canonical_path, clean_filename)
        return resolved_path, final_filename, ActionTypeEnum.MOVE
    
    def generate_migration_plans(self, db_session: Session) -> List[MigrationProposalContract]:
        """Generate migration plans for all file locations in the database."""
        proposals = []
        locations = db_session.query(FileLocation).all()
        
        for loc in locations:
            asset = loc.asset or db_session.get(BinaryAsset, loc.asset_id)
            product = asset.product if asset and asset.product else (
                db_session.get(SoftwareProduct, asset.product_id) if asset and asset.product_id else None
            )
            taxonomy = product.taxonomy if product and product.taxonomy else (
                db_session.get(Taxonomy, product.taxonomy_id) if product and product.taxonomy_id else None
            )
            confidence = product.confidence_score if product and product.confidence_score is not None else 0.5
            
            target_path, clean_filename, action_enum = self.process_asset(asset, product, taxonomy, loc)
            
            proposal = MigrationProposalContract(
                location_id=loc.id,
                current_full_path=loc.current_full_path,
                proposed_relative_path=target_path,
                action_type=action_enum,
                confidence_score=confidence
            )
            proposals.append(proposal)
        
        return proposals


def generate_migration_plans(db_session: Session) -> List[MigrationProposalContract]:
    """Factory function to generate migration plans using the resolver."""
    resolver = TargetPathResolver()
    return resolver.generate_migration_plans(db_session)
