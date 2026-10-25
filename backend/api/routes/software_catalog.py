import os
import json
import shutil
import tempfile
import hashlib
from typing import List, Optional, Dict, Any
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import text

from pydantic import BaseModel, Field

from backend.catalog.models import (
    SoftwareProduct, BinaryAsset, FileLocation, MigrationPlan, Taxonomy,
    init_catalog_db
)
from backend.catalog.schemas import (
    RawBinaryMetadata, LLMClassificationResult, MigrationProposalContract,
    ArchitectureEnum, ActionTypeEnum, MigrationStatusEnum
)
from backend.catalog.orchestrator import SoftwareCatalogOrchestrator
from backend.catalog.organizer.path_resolver import TargetPathResolver
from backend.catalog.organizer.executor import StorageMigrationExecutor

router = APIRouter(prefix="/api/v1/catalog", tags=["Software Catalog"])

_db_session: Optional[Session] = None


class ScanRequest(BaseModel):
    source_root: Optional[str] = None
    source_directory: Optional[str] = None
    target_root: Optional[str] = None


class MigrationExecuteRequest(BaseModel):
    plan_id: Optional[int] = None
    target_root: Optional[str] = None


class MigrationRollbackRequest(BaseModel):
    manifest_path: Optional[str] = None
    target_root: Optional[str] = None


def get_db_session() -> Session:
    global _db_session
    if _db_session is None:
        from sqlalchemy import create_engine
        engine = create_engine("sqlite:///catalog.db", echo=False, connect_args={"check_same_thread": False})
        init_catalog_db(engine)
        _db_session = Session(engine)
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
        for byte_block in iter(lambda: f.read(65536), b""):
            sha256_hash.update(byte_block)
    return sha256_hash.hexdigest()


def get_file_size(file_path: str) -> int:
    try:
        return os.path.getsize(file_path)
    except OSError:
        return 0


# --- Routes ---

@router.post("/scan", response_model=Dict[str, Any])
async def scan_directory(
    payload: Optional[ScanRequest] = None,
    source_root: Optional[str] = None,
    target_root: Optional[str] = None
):
    """
    Trigger full scan & enrichment pipeline on source directory.
    Supports either JSON body (source_directory or source_root) or query parameters.
    """
    effective_source = None
    effective_target = target_root

    if payload:
        effective_source = payload.source_root or payload.source_directory
        if payload.target_root:
            effective_target = payload.target_root

    if not effective_source:
        effective_source = source_root

    if not effective_source:
        raise HTTPException(status_code=400, detail="Missing required parameter: source_root or source_directory")

    try:
        db = get_db_session()
        orchestrator = SoftwareCatalogOrchestrator(db)
        out_root = effective_target or (str(Path(effective_source).parent / "clean_software_catalog"))
        
        stats = orchestrator.run_full_pipeline(effective_source, out_root, db)
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
    try:
        q = db_session.query(SoftwareProduct)

        if vendor:
            q = q.filter(SoftwareProduct.canonical_vendor.ilike(f"%{vendor}%"))

        if category:
            q = q.join(Taxonomy, SoftwareProduct.taxonomy_id == Taxonomy.id).filter(
                (Taxonomy.category_name.ilike(f"%{category}%")) |
                (Taxonomy.subcategory_name.ilike(f"%{category}%"))
            )

        if low_confidence:
            q = q.filter((SoftwareProduct.confidence_score < 0.70) | (SoftwareProduct.confidence_score == None))

        if query:
            # Attempt FTS5 query
            matched_ids = []
            try:
                fts_rows = db_session.execute(
                    text("SELECT rowid FROM catalog_fts WHERE catalog_fts MATCH :term"),
                    {"term": query}
                ).fetchall()
                matched_ids = [r[0] for r in fts_rows]
            except Exception:
                pass

            if matched_ids:
                q = q.filter(SoftwareProduct.id.in_(matched_ids))
            else:
                q = q.filter(
                    (SoftwareProduct.canonical_name.ilike(f"%{query}%")) |
                    (SoftwareProduct.canonical_vendor.ilike(f"%{query}%")) |
                    (SoftwareProduct.summary_description.ilike(f"%{query}%"))
                )

        results = q.all()

        items = []
        for product in results:
            assets = db_session.query(BinaryAsset).filter(BinaryAsset.product_id == product.id).all()
            if architecture:
                assets = [a for a in assets if (a.architecture or "").lower() == architecture.lower()]
                if not assets:
                    continue

            primary_asset = assets[0] if assets else None
            primary_category = product.taxonomy.category_name if product.taxonomy else "Uncategorized"

            items.append({
                "id": product.id,
                "canonical_vendor": product.canonical_vendor,
                "canonical_name": product.canonical_name,
                "taxonomy_id": product.taxonomy_id,
                "taxonomy": f"{product.taxonomy.category_name}/{product.taxonomy.subcategory_name}" if product.taxonomy else "Uncategorized",
                "primary_category": primary_category,
                "detected_version": primary_asset.detected_version if primary_asset else None,
                "architecture": primary_asset.architecture if primary_asset else "Unknown",
                "enrichment_source": product.enrichment_source,
                "confidence_score": product.confidence_score,
                "is_human_verified": product.is_human_verified,
                "assets_count": len(assets)
            })

        return {"items": items}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


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
        product = db_session.get(SoftwareProduct, product_id)
        if not product:
            raise HTTPException(status_code=404, detail="Product not found")

        if "canonical_vendor" in data:
            product.canonical_vendor = data["canonical_vendor"]
        if "canonical_name" in data:
            product.canonical_name = data["canonical_name"]
        if "taxonomy_id" in data:
            product.taxonomy_id = data["taxonomy_id"]

        product.is_human_verified = True
        product.confidence_score = 1.0  # User verified gives max confidence

        # Recompute migration plans for all locations associated with this product's assets
        resolver = TargetPathResolver()
        updated_plans = []

        assets = db_session.query(BinaryAsset).filter(BinaryAsset.product_id == product.id).all()
        for asset in assets:
            for loc in asset.file_locations:
                target_path, clean_filename, action_enum = resolver.process_asset(
                    asset, product, product.taxonomy, loc
                )
                
                plan = db_session.query(MigrationPlan).filter(MigrationPlan.location_id == loc.id).first()
                if plan:
                    plan.proposed_relative_path = target_path
                    plan.action_type = action_enum.value
                    plan.status = "pending"
                else:
                    plan = MigrationPlan(
                        location_id=loc.id,
                        proposed_relative_path=target_path,
                        action_type=action_enum.value,
                        status="pending"
                    )
                    db_session.add(plan)
                
                updated_plans.append({
                    "location_id": loc.id,
                    "source_path": loc.current_full_path,
                    "target_path": target_path,
                    "action": action_enum.value
                })

        db_session.commit()
        return {
            "status": "success",
            "message": "Product updated and migration plans recomputed",
            "updated_plans": updated_plans
        }
    except HTTPException:
        raise
    except Exception as e:
        db_session.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/migration/preview")
async def get_migration_preview(
    product_id: Optional[int] = None,
    target_root: Optional[str] = None,
    db_session: Session = Depends(get_db_session)
):
    """
    Return before/after directory tree structure and duplicate savings metrics.
    """
    try:
        executor = StorageMigrationExecutor()
        tgt_root = target_root or "clean_software_catalog"

        if product_id:
            product = db_session.get(SoftwareProduct, product_id)
            if not product:
                raise HTTPException(status_code=404, detail="Product not found")

            before_paths = []
            after_paths = []
            assets = db_session.query(BinaryAsset).filter(BinaryAsset.product_id == product_id).all()

            for asset in assets:
                for loc in asset.file_locations:
                    before_paths.append(loc.current_full_path)
                    plan = db_session.query(MigrationPlan).filter(MigrationPlan.location_id == loc.id).first()
                    if plan:
                        after_paths.append(str(Path(tgt_root) / plan.proposed_relative_path))

            return {
                "product_id": product_id,
                "before_structure": before_paths,
                "after_structure": after_paths,
                "estimated_savings_bytes": sum(os.path.getsize(p) for p in before_paths if os.path.exists(p))
            }
        else:
            dry_run_stats = executor.dry_run(tgt_root, db_session)
            return {
                "status": "global",
                "preview": dry_run_stats
            }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/migration/execute")
async def execute_migration(
    payload: Optional[MigrationExecuteRequest] = None,
    plan_id: Optional[int] = None,
    target_root: Optional[str] = None,
    db_session: Session = Depends(get_db_session)
):
    """
    Execute approved moves/copies. Supports JSON body or query parameters.
    """
    effective_plan_id = plan_id
    effective_target_root = target_root

    if payload:
        if payload.plan_id is not None:
            effective_plan_id = payload.plan_id
        if payload.target_root is not None:
            effective_target_root = payload.target_root

    try:
        executor = StorageMigrationExecutor()
        tgt_root = effective_target_root or "clean_software_catalog"

        if effective_plan_id:
            plan = db_session.get(MigrationPlan, effective_plan_id)
            if not plan:
                raise HTTPException(status_code=404, detail="Migration plan not found")
            plan.status = "APPROVED"
            db_session.commit()

        exec_stats = executor.execute_plan(tgt_root, db_session)
        return {
            "status": "success",
            "message": "Migration executed successfully",
            "stats": exec_stats
        }
    except HTTPException:
        raise
    except Exception as e:
        db_session.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/migration/rollback")
async def rollback_migration(
    payload: Optional[MigrationRollbackRequest] = None,
    manifest_path: Optional[str] = None,
    db_session: Session = Depends(get_db_session)
):
    """
    Revert executed migration via manifest. Defaults to standard rollback manifest if not specified.
    """
    effective_manifest = manifest_path
    if payload and payload.manifest_path:
        effective_manifest = payload.manifest_path
    elif payload and payload.target_root:
        effective_manifest = str(Path(payload.target_root) / "migration_rollback_manifest.json")

    if not effective_manifest:
        effective_manifest = "clean_software_catalog/migration_rollback_manifest.json"

    try:
        executor = StorageMigrationExecutor()
        result = executor.rollback_migration(effective_manifest, db_session)
        if result.get("error"):
            raise HTTPException(status_code=400, detail=result["error"])

        return {
            "status": "success",
            "message": "Migration rolled back successfully",
            "stats": result
        }
    except HTTPException:
        raise
    except Exception as e:
        db_session.rollback()
        raise HTTPException(status_code=500, detail=str(e))
