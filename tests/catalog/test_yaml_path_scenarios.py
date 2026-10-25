"""
Pytest YAML Scenario Runner for Granular Progressive Taxonomy & Path Resolution.
Executes test scenarios defined in tests/catalog/scenarios/test_path_resolution_hierarchy.yaml.
"""
import os
import pytest
import yaml
from pathlib import Path

from backend.catalog.models import BinaryAsset, SoftwareProduct, FileLocation, Taxonomy
from backend.catalog.organizer.path_resolver import TargetPathResolver
from backend.catalog.taxonomy_service import TaxonomyService
from backend.catalog.schemas import ActionTypeEnum, RawBinaryMetadata, ArchitectureEnum


SCENARIOS_YAML_PATH = Path(__file__).parent / "scenarios" / "test_path_resolution_hierarchy.yaml"


def load_yaml_scenarios():
    """Load scenario list from YAML file."""
    with open(SCENARIOS_YAML_PATH, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return data.get("scenarios", [])


class TestPathResolutionYAMLScenarios:
    """Parametrized pytest test suite reading from the YAML scenarios file."""

    @pytest.mark.parametrize(
        "scenario",
        load_yaml_scenarios(),
        ids=lambda s: s["id"]
    )
    def test_yaml_path_resolution_scenario(self, db_session, scenario):
        """
        Validate that TargetPathResolver and TaxonomyService resolve the given asset,
        metadata, and category to the expected progressive, rational target path.
        """
        raw_meta = scenario.get("raw_metadata", {})
        classification = scenario.get("classification")
        expected = scenario.get("expected", {})
        current_full_path = scenario.get("current_full_path", "")
        source_root = scenario.get("source_root", "")

        # 1. Create or retrieve Taxonomy if classification provides category
        taxonomy_service = TaxonomyService(db_session)
        taxonomy = None
        if classification and classification.get("primary_category"):
            taxonomy = taxonomy_service.resolve_taxonomy(
                category_name=classification.get("primary_category"),
                subcategory_name=classification.get("subcategory"),
                db_session=db_session
            )

        # 2. Build SoftwareProduct if classified
        product = None
        if classification:
            product = SoftwareProduct(
                canonical_vendor=classification.get("canonical_vendor", "Unknown"),
                canonical_name=classification.get("canonical_product", "Unknown"),
                taxonomy_id=taxonomy.id if taxonomy else None,
                confidence_score=classification.get("confidence_score", 0.5)
            )
            if hasattr(product, "product_suite") and classification.get("product_suite"):
                setattr(product, "product_suite", classification.get("product_suite"))
            db_session.add(product)
            db_session.flush()

        # 3. Build BinaryAsset
        asset = BinaryAsset(
            sha256_hash=raw_meta.get("sha256_hash", "0" * 64),
            file_size_bytes=raw_meta.get("file_size_bytes", 1000),
            file_extension=raw_meta.get("file_extension", ".exe"),
            detected_version=raw_meta.get("detected_version"),
            architecture=raw_meta.get("architecture", "x64"),
            pe_company_name=raw_meta.get("pe_company_name"),
            pe_product_name=raw_meta.get("pe_product_name"),
            pe_original_filename=raw_meta.get("pe_original_filename"),
            product_id=product.id if product else None
        )
        db_session.add(asset)
        db_session.flush()

        # 4. Build FileLocation
        filename = Path(current_full_path.replace("\\", "/")).name
        location = FileLocation(
            asset_id=asset.id,
            current_full_path=current_full_path,
            current_filename=filename,
            parent_folder_chain=raw_meta.get("parent_folder_chain", ""),
            is_primary_copy=True
        )
        db_session.add(location)
        db_session.flush()

        # 5. Resolve Target Path
        resolver = TargetPathResolver(root_prefix=source_root)
        resolved_path, clean_filename, action = resolver.process_asset(
            asset=asset,
            product=product,
            taxonomy=taxonomy,
            location=location
        )

        # 6. Assertions against expected contract
        expected_action = ActionTypeEnum[expected["action_type"]]
        assert action == expected_action, f"Expected action {expected_action}, got {action}"

        expected_rel_path = expected.get("target_relative_path")
        if expected_rel_path:
            # Normalize forward slashes for cross-platform comparison
            norm_resolved = resolved_path.replace("\\", "/")
            norm_expected = expected_rel_path.replace("\\", "/")
            assert norm_resolved == norm_expected, (
                f"Resolved relative path mismatch for scenario '{scenario['id']}':\n"
                f"Expected: {norm_expected}\n"
                f"Got:      {norm_resolved}"
            )

        expected_full_path = expected.get("target_full_path")
        if expected_full_path:
            full_target = resolver.resolve_full_path(source_root, resolved_path)
            # Normalize backslashes for Windows UNC path check
            norm_full_target = full_target.replace("/", "\\").lower()
            norm_expected_full = expected_full_path.replace("/", "\\").lower()
            assert norm_full_target == norm_expected_full, (
                f"Resolved full path mismatch for scenario '{scenario['id']}':\n"
                f"Expected: {expected_full_path}\n"
                f"Got:      {full_target}"
            )
