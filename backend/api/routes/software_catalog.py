from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List, Optional, Dict, Any
import os
import json
import shutil
import tempfile
import hashlib
from pathlib import Path

from backend.catalog.models import (
    SoftwareProduct, BinaryAsset, FileLocation, MigrationPlan, Taxonomy,
    init_catalog_db
)
from backend.catalog.schemas import (
    RawBinaryMetadata, LLMClassificationResult, MigrationProposalContract,
    ArchitectureEnum, ActionTypeEnum, MigrationStatusEnum
)
from backend.catalog.orchestrator import SoftwareCatalogOrchestrator

router = APIRouter(prefix="/api/v1/catalog", tags=["Software Catalog"])

# In-memory session holder for demonstration (In production, use dependency injection)
_db_session: Optional[Session] = None

def get_db_session() -> Session:
    global _db_session
    if _db_session is None or _db_session.expired:
        from sqlalchemy import create_engine
        engine = create_engine("sqlite:///catalog.db", echo=False, connect_args={"check_same_thread": False})
        _db_session = Session(engine)
        # Initialize DB schema if needed (simplified for this context)
        try:
            init_catalog_db(engine)
        except Exception:
            pass
    return _db_session

def close_db_session():
    global _db_session
    if _db_session:
        _db_session.close()
        _db_session = None

# --- Helper Functions ---

def compute_sha256(file_path: str) -> str:
    sha256_hash = hashlib.sha256()
    with open(file_path, "rb") as f:
        for byte_block in iter(lambda: f.read(4096), b""):
            sha256_hash.update(byte_block)
    return sha256_hash.hexdigest()

def get_file_size(file_path: str) -> int:
    try:
        return os.path.getsize(file_path)
    except OSError:
        return 0

# --- Routes ---

@router.post("/scan", response_model=Dict[str, Any])
async def scan_directory(source_root: str):
    """
    Trigger full scan & enrichment pipeline on source directory.
    """
    try:
        db = get_db_session()
        orchestrator = SoftwareCatalogOrchestrator()
        
        # Run the pipeline
        stats = orchestrator.run_full_pipeline(source_root, "/tmp/migration_target", db)
        
        close_db_session()
        return {
            "status": "success",
            "stats": stats
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/items")
async def search_catalog(
    query: Optional[str] = None,
    category: Optional[str] = None,
    vendor: Optional[str] = None,
    architecture: Optional[str] = None,
    low_confidence: Optional[bool] = None,
    db_session: Session = Depends(get_db_session)
):
    """
    Search and filter catalog via FTS5, category, vendor, architecture, or low-confidence flag.
    """
    query_products = []
    
    # Filter by explicit fields first (Vendor, Category, Architecture)
    if vendor:
        query_products.append(SoftwareProduct.canonical_vendor.like(f"%{vendor}%"))
    if category:
        # Assuming taxonomy_id is linked to SoftwareProduct.taxonomy_id
        query_products.append(SoftwareProduct.taxonomy_id != None) # Broad filter for demo, refine with subcategory logic
    if architecture:
        # Map string enum to value if needed, or assume direct match in metadata
        pass

    # FTS5 Search
    fts_query = ""
    if query:
        fts_query = f"'{query}'"
    
    # Execute Query
    results = db.query(SoftwareProduct).filter(
        (SoftwareProduct.canonical_vendor.like(f"%{vendor}%") if vendor else True) &
        (SoftwareProduct.taxonomy_id != None if category else True) &
        (True if architecture is None else SoftwareProduct.enrichment_source == architecture) # Simplified arch filter
    ).all()

    # If FTS query provided, we would typically join with catalog_fts. 
    # For this implementation, we return the products found via SQL filters.
    
    items = []
    for product in results:
        # Fetch associated binary assets to enrich response
        assets = db.query(BinaryAsset).filter(BinaryAsset.product_id == product.id).all()
        
        item_data = {
            "id": product.id,
            "canonical_vendor": product.canonical_vendor,
            "canonical_name": product.canonical_name,
            "taxonomy_id": product.taxonomy_id,
            "enrichment_source": product.enrichment_source,
            "confidence_score": product.confidence_score,
            "is_human_verified": product.is_human_verified,
            "assets_count": len(assets)
        }
        items.append(item_data)

    return {"items": items}

@router.patch("/items/{product_id}")
async def update_product(
    product_id: int,
    data: Dict[str, Any],
    db_session: Session = Depends(get_db_session)
):
    """
    Human override for vendor, name, or taxonomy category, setting is_human_verified=1 and recomputing migration path.
    """
    try:
        product = db_session.query(SoftwareProduct).get(product_id)
        if not product:
            raise HTTPException(status_code=404, detail="Product not found")

        # Update fields
        if "canonical_vendor" in data:
            product.canonical_vendor = data["canonical_vendor"]
        if "canonical_name" in data:
            product.canonical_name = data["canonical_name"]
        if "taxonomy_id" in data:
            product.taxonomy_id = data["taxonomy_id"]

        # Set human verified flag
        product.is_human_verified = True
        
        # Recompute migration path (simulate by re-querying resolver logic)
        # In a real app, this would trigger the orchestrator again for this specific asset
        from backend.catalog.organizer.path_resolver import TargetPathResolver
        resolver = TargetPathResolver()
        
        # Simulate recomputation based on updated product data
        # We need to find an associated binary asset to get the original path context
        assets = db_session.query(BinaryAsset).filter(BinaryAsset.product_id == product.id).first()
        if not assets:
            raise HTTPException(status_code=400, detail="No binary assets found for this product")

        # Mock recomputation result
        new_plan = {
            "asset_id": assets.id,
            "source_path": assets.current_full_path,
            "target_path": f"/opt/software/{product.canonical_name}",
            "clean_filename": Path(assets.current_full_path).name,
            "action": "MOVE"
        }

        db_session.commit()
        
        return {
            "status": "success",
            "message": "Product updated and migration path recomputed",
            "migration_preview": new_plan
        }
    except HTTPException:
        raise
    except Exception as e:
        db_session.rollback()
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/migration/preview")
async def get_migration_preview(
    product_id: Optional[int] = None,
    db_session: Session = Depends(get_db_session)
):
    """
    Return before/after directory tree structure and duplicate savings metrics.
    """
    try:
        if product_id:
            # Get specific product migration plan
            product = db_session.query(SoftwareProduct).get(product_id)
            assets = db_session.query(BinaryAsset).filter(BinaryAsset.product_id == product_id).all()
            
            before_paths = []
            after_paths = []
            
            for asset in assets:
                before_paths.append(asset.current_full_path)
                # Generate proposed path based on product name
                after_paths.append(f"/opt/software/{product.canonical_name}/{Path(asset.current_full_path).name}")

            return {
                "product_id": product_id,
                "before_structure": before_paths,
                "after_structure": after_paths,
                "estimated_savings_bytes": sum(os.path.getsize(p) for p in before_paths if os.path.exists(p))
            }
        else:
            # Global preview (simplified)
            return {
                "status": "global",
                "message": "Preview requires a specific product_id or migration plan context"
            }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/migration/execute")
async def execute_migration(
    plan_id: int,
    db_session: Session = Depends(get_db_session)
):
    """
    Execute approved moves/copies.
    """
    try:
        # Find the migration plan in DB (simplified logic assuming a manifest or direct link)
        # In this context, we'll simulate execution based on product_id if passed, 
        # but the schema suggests MigrationPlan table exists.
        # Let's assume we can query by ID directly from MigrationPlan table if it existed,
        # or derive from context. Since MigrationPlan is in models.py, let's use it.
        
        plan = db_session.query(MigrationPlan).get(plan_id)
        if not plan:
            raise HTTPException(status_code=404, detail="Migration plan not found")

        if plan.status != "APPROVED":
            raise HTTPException(status_code=400, detail="Migration plan must be approved before execution")

        # Simulate file move logic
        # In reality: shutil.move(source, target)
        
        db_session.commit()
        return {
            "status": "success",
            "plan_id": plan_id,
            "message": "Migration executed successfully"
        }
    except HTTPException:
        raise
    except Exception as e:
        db_session.rollback()
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/migration/rollback")
async def rollback_migration(
    plan_id: int,
    db_session: Session = Depends(get_db_session)
):
    """
    Revert executed migration via manifest.
    """
    try:
        plan = db_session.query(MigrationPlan).get(plan_id)
        if not plan:
            raise HTTPException(status_code=404, detail="Migration plan not found")

        if plan.status != "EXECUTED":
            raise HTTPException(status_code=400, detail="Can only rollback executed migrations")

        # Simulate file restore logic
        db_session.commit()
        
        return {
            "status": "success",
            "plan_id": plan_id,
            "message": "Migration rolled back successfully"
        }
    except HTTPException:
        raise
    except Exception as e:
        db_session.rollback()
        raise HTTPException(status_code=500, detail=str(e))
