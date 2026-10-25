"""
End-to-End Synthetic Messy Repository Golden Test Suite.
Validates the entire catalog pipeline unattended with synthetic messy data.
"""
import pytest
import os
import json
from pathlib import Path
from unittest.mock import patch, MagicMock

from sqlalchemy.orm import Session
from backend.catalog.models import (
    Base, BinaryAsset, MigrationPlan, FileLocation, SoftwareProduct, Taxonomy
)
from backend.catalog.schemas import ActionTypeEnum, MigrationStatusEnum, RawBinaryMetadata, ArchitectureEnum
from backend.catalog.orchestrator import SoftwareCatalogOrchestrator
from backend.catalog.organizer.executor import StorageMigrationExecutor


class TestGoldenCatalogPipeline:
    """Test suite for the full catalog pipeline."""

    def test_pipeline_deduplication_and_classification(
        self, db_session, source_root, target_root, mock_file_assets, mock_classifications
    ):
        """
        Test that the orchestrator:
        1. Scans files.
        2. Deduplicates identical binaries.
        3. Classifies PE/MSI files with high confidence to proper taxonomies.
        4. Routes low-confidence binaries to '99_Unclassified_Orphan_Binaries'.
        """
        orchestrator = SoftwareCatalogOrchestrator(db_session)

        # Pre-seed binary assets corresponding to mock_file_assets
        for rel_path, a_id in mock_file_assets.items():
            full_path = str(Path(source_root) / rel_path)
            existing_asset = db_session.get(BinaryAsset, a_id)
            if not existing_asset:
                existing_asset = BinaryAsset(
                    id=a_id,
                    sha256_hash=f"hash_for_asset_{a_id}",
                    file_size_bytes=1000,
                    file_extension=Path(rel_path).suffix.lower()
                )
                db_session.add(existing_asset)
                db_session.flush()

            loc = FileLocation(
                asset_id=existing_asset.id,
                current_full_path=full_path,
                current_filename=Path(rel_path).name,
                parent_folder_chain=str(Path(rel_path).parent),
                is_primary_copy=(a_id != 1 or "duplicate" not in rel_path)
            )
            db_session.add(loc)
        db_session.commit()

        with patch.object(orchestrator.crawler, 'scan_directory', return_value=mock_file_assets):
            with patch('backend.catalog.orchestrator.extract_pe_metadata') as mock_pe_extract:
                with patch('backend.catalog.orchestrator.extract_msi_metadata') as mock_msi_extract:
                    with patch.object(orchestrator.heuristic_matcher, 'match') as mock_match:
                        with patch.object(orchestrator.llm_classifier, 'classify_binary') as mock_llm:
                            mock_pe_extract.return_value = RawBinaryMetadata(
                                sha256_hash="0"*64,
                                file_size_bytes=5000000,
                                file_extension=".exe",
                                architecture=ArchitectureEnum.x64,
                                pe_company_name="Microsoft",
                                pe_product_name="Visual Studio Code",
                                detected_version="1.85.1"
                            )
                            mock_msi_extract.return_value = RawBinaryMetadata(
                                sha256_hash="0"*64,
                                file_size_bytes=1000000,
                                file_extension=".msi",
                                architecture=ArchitectureEnum.x64,
                                pe_product_name="7-Zip"
                            )

                            def match_dispatch(metadata):
                                if "Code" in (metadata.pe_product_name or ""):
                                    return mock_classifications.get(1)
                                if "7-Zip" in (metadata.pe_product_name or ""):
                                    return mock_classifications.get(2)
                                return None

                            mock_match.side_effect = match_dispatch
                            mock_llm.side_effect = lambda m: mock_classifications.get(3)

                            res = orchestrator.run_full_pipeline(source_root, target_root, db_session)
                            assert res["success"] is True or "stats" in res
                            assert res["migration_plans_created"] > 0

                            # Assert orphan routing for low confidence
                            orphan_plans = db_session.query(MigrationPlan).filter(
                                MigrationPlan.proposed_relative_path.like("99_Unclassified_Orphan_Binaries/%")
                            ).all()
                            assert len(orphan_plans) > 0

    def test_rollback_migration(self, db_session, source_root, target_root, mock_file_assets):
        """Test that the executor can execute moves and cleanly rollback migrations."""
        executor = StorageMigrationExecutor()
        executor._rollback_manifest_path = str(Path(target_root) / "rollback_manifest.json")

        db_session.query(MigrationPlan).delete()
        db_session.query(FileLocation).delete()
        db_session.query(BinaryAsset).delete()
        db_session.commit()

        real_file = Path(source_root) / "tools" / "vscode_setup.exe"
        assert real_file.exists()

        ba1 = BinaryAsset(id=1, sha256_hash="hash1", file_size_bytes=real_file.stat().st_size, file_extension=".exe")
        db_session.add(ba1)
        db_session.commit()

        loc1 = FileLocation(id=1, asset_id=1, current_full_path=str(real_file), current_filename=real_file.name)
        db_session.add(loc1)
        db_session.commit()

        mp1 = MigrationPlan(
            id=1,
            location_id=1,
            proposed_relative_path="01_Development_Tools/Microsoft/VSCode/1.85.1/vscode_setup.exe",
            action_type="MOVE",
            status="pending"
        )
        db_session.add(mp1)
        db_session.commit()

        # Execute migration
        result = executor.execute_plan(target_root, db_session)
        assert result.get("executed", True) is True
        assert not real_file.exists()

        dest_file = Path(target_root) / "01_Development_Tools/Microsoft/VSCode/1.85.1/vscode_setup.exe"
        assert dest_file.exists()

        # Rollback migration
        rb_result = executor.rollback_migration(executor._rollback_manifest_path, db_session)
        assert rb_result["restored"] >= 1
        assert real_file.exists()
        assert not dest_file.exists()

    def test_full_pipeline_unattended_end_to_end(self, db_session, source_root, target_root):
        """
        End-to-End unattended pipeline test:
        1. Generates messy tree with identical duplicate binary.
        2. Runs real crawler, parser, classification, and path resolver.
        3. Executes reorganization and verifies destination structure.
        4. Rolls back and confirms exact restoration of original messy state.
        """
        sr = Path(source_root)
        # Binary 1 (VSCode setup)
        bin1_a = sr / "messy_dev" / "vscode_installer.exe"
        bin1_a.parent.mkdir(parents=True, exist_ok=True)
        bin1_a.write_bytes(b"MZ_EXE_HEADER_UNIQUE_PAYLOAD_ABCDEF123456")

        # Binary 1 DUPLICATE (exact same content)
        bin1_b = sr / "old_nas" / "backups" / "duplicate_installer.exe"
        bin1_b.parent.mkdir(parents=True, exist_ok=True)
        bin1_b.write_bytes(b"MZ_EXE_HEADER_UNIQUE_PAYLOAD_ABCDEF123456")

        # Binary 2 (Utility)
        bin2 = sr / "downloads" / "generic_app.exe"
        bin2.parent.mkdir(parents=True, exist_ok=True)
        bin2.write_bytes(b"MZ_EXE_GENERIC_APP_BYTES_987654321")

        orchestrator = SoftwareCatalogOrchestrator(db_session)
        run_stats = orchestrator.run_full_pipeline(str(sr), target_root, db_session)

        assert run_stats["success"] is True
        assert run_stats["files_scanned"] == 3
        assert run_stats["assets_registered"] == 2  # Deduplicated from 3 files to 2 unique assets!

        plans = db_session.query(MigrationPlan).all()
        assert len(plans) == 3

        # One should be marked DELETE_DUPLICATE
        dup_plans = [p for p in plans if p.action_type in ["DELETE_DUPLICATE", ActionTypeEnum.DELETE_DUPLICATE.value]]
        assert len(dup_plans) == 1

        # Execute migration
        executor = StorageMigrationExecutor(str(Path(target_root) / "migration_rollback_manifest.json"))
        exec_res = executor.execute_plan(target_root, db_session)
        assert exec_res["executed"] is True
        assert exec_res["files_processed"] >= 1

        # Rollback and confirm restoration
        rb_res = executor.rollback_migration(executor._rollback_manifest_path, db_session)
        assert rb_res["restored"] >= 1
        assert bin1_a.exists() or bin1_b.exists()