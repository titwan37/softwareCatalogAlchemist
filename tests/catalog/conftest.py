import pytest
from pathlib import Path
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from backend.catalog.models import Base, init_catalog_db
from backend.catalog.schemas import LLMClassificationResult, ArchitectureEnum


@pytest.fixture(scope="function")
def source_root(tmp_path):
    """Temporary messy directory fixture."""
    sr = tmp_path / "messy_source"
    sr.mkdir(parents=True, exist_ok=True)
    return str(sr)


@pytest.fixture(scope="function")
def target_root(tmp_path):
    """Temporary clean directory fixture."""
    tr = tmp_path / "clean_target"
    tr.mkdir(parents=True, exist_ok=True)
    return str(tr)


@pytest.fixture(scope="function")
def db_session(tmp_path):
    """Fresh SQLite database session fixture."""
    db_file = tmp_path / "test_catalog.db"
    engine = create_engine(f"sqlite:///{db_file}")
    init_catalog_db(engine)
    session = Session(bind=engine)
    yield session
    session.close()


@pytest.fixture(scope="function")
def mock_file_assets(source_root):
    """Mock file assets mapping with physical files created on disk."""
    sr = Path(source_root)

    file1 = sr / "tools" / "vscode_setup.exe"
    file1.parent.mkdir(parents=True, exist_ok=True)
    file1.write_bytes(b"SYNTHETIC_PE_VSCODE_BYTES_12345")

    file2 = sr / "old_backup" / "nested" / "vscode_duplicate.exe"
    file2.parent.mkdir(parents=True, exist_ok=True)
    file2.write_bytes(b"SYNTHETIC_PE_VSCODE_BYTES_12345")

    file3 = sr / "installers" / "package.msi"
    file3.parent.mkdir(parents=True, exist_ok=True)
    file3.write_bytes(b"SYNTHETIC_MSI_PACKAGE_BYTES_67890")

    file4 = sr / "temp" / "unknown.exe"
    file4.parent.mkdir(parents=True, exist_ok=True)
    file4.write_bytes(b"SYNTHETIC_UNKNOWN_EXE_BYTES_99999")

    return {
        "tools/vscode_setup.exe": 1,
        "old_backup/nested/vscode_duplicate.exe": 1,
        "installers/package.msi": 2,
        "temp/unknown.exe": 3
    }


@pytest.fixture(scope="function")
def mock_classifications():
    """Mock classifications for Tier 1/2 and Tier 3 resolution."""
    return {
        1: LLMClassificationResult(
            canonical_vendor="Microsoft",
            canonical_product="Visual Studio Code",
            detected_version="1.85.1",
            architecture=ArchitectureEnum.x64,
            primary_category="01_Development_Tools",
            subcategory="IDEs_and_Editors",
            license_model="FOSS",
            summary="Code editor developed by Microsoft",
            confidence_score=0.98,
            reasoning="Matched PE headers for VS Code"
        ),
        2: LLMClassificationResult(
            canonical_vendor="7-Zip",
            canonical_product="7-Zip Archiver",
            detected_version="23.01",
            architecture=ArchitectureEnum.x64,
            primary_category="03_System_Utilities",
            subcategory="Compression",
            license_model="Open Source",
            summary="File archiver with a high compression ratio",
            confidence_score=0.95,
            reasoning="Matched MSI product code and properties"
        ),
        3: LLMClassificationResult(
            canonical_vendor="Unknown",
            canonical_product="Unknown_Utility",
            detected_version="0.1.0",
            architecture=ArchitectureEnum.Unknown,
            primary_category="99_Unclassified_Orphan_Binaries",
            subcategory=None,
            license_model=None,
            summary="Unclassified or unrecognized binary asset",
            confidence_score=0.35,
            reasoning="No recognizable metadata found"
        )
    }