import sqlite3
from typing import Optional, List
from datetime import datetime, timezone

from sqlalchemy import (
    Column, Integer, String, Text, DateTime, JSON, ForeignKey, 
    create_engine, Table as SqlTable, MetaData, text, Float, Boolean
)
from sqlalchemy.orm import declarative_base, relationship, Session

Base = declarative_base()


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Taxonomy(Base):
    __tablename__ = "taxonomies"
    
    id = Column(Integer, primary_key=True)
    category_prefix = Column(String(50), nullable=False)
    category_name = Column(String(100), nullable=False)
    subcategory_name = Column(String(200), nullable=True)
    description = Column(Text, nullable=True)


class SoftwareProduct(Base):
    __tablename__ = "software_products"
    
    id = Column(Integer, primary_key=True)
    canonical_vendor = Column(String(100), nullable=False)
    canonical_name = Column(String(200), nullable=False)
    taxonomy_id = Column(Integer, ForeignKey("taxonomies.id"))
    summary_description = Column(Text, nullable=True)
    official_website = Column(String(255), nullable=True)
    license_model = Column(String(100), nullable=True)
    enrichment_source = Column(String(100), nullable=True)
    confidence_score = Column(Float, nullable=True)
    is_human_verified = Column(Boolean, default=False)
    created_at = Column(DateTime, default=utc_now)

    taxonomy = relationship("Taxonomy", back_populates="software_products")


class BinaryAsset(Base):
    __tablename__ = "binary_assets"
    
    id = Column(Integer, primary_key=True)
    product_id = Column(Integer, ForeignKey("software_products.id"))
    sha256_hash = Column(String(64), nullable=False)
    file_size_bytes = Column(Integer, nullable=True)
    file_extension = Column(String(10), nullable=True)
    detected_version = Column(String(50), nullable=True)
    architecture = Column(String(30), nullable=True)
    pe_company_name = Column(String(100), nullable=True)
    pe_product_name = Column(String(200), nullable=True)
    pe_file_description = Column(Text, nullable=True)
    pe_original_filename = Column(String(255), nullable=True)
    msi_product_code = Column(String(100), nullable=True)
    digital_signature_subject = Column(String(255), nullable=True)
    raw_metadata_json = Column(JSON, nullable=True)
    first_seen_at = Column(DateTime, default=utc_now)

    product = relationship("SoftwareProduct", back_populates="binary_assets")


class FileLocation(Base):
    __tablename__ = "file_locations"
    
    id = Column(Integer, primary_key=True)
    asset_id = Column(Integer, ForeignKey("binary_assets.id"))
    current_full_path = Column(String(500), nullable=False)
    current_filename = Column(String(255), nullable=False)
    parent_folder_chain = Column(Text, nullable=True)
    file_modified_at = Column(DateTime, default=utc_now)
    is_primary_copy = Column(Boolean, default=True)

    asset = relationship("BinaryAsset", back_populates="file_locations")


class MigrationPlan(Base):
    __tablename__ = "migration_plans"
    
    id = Column(Integer, primary_key=True)
    location_id = Column(Integer, ForeignKey("file_locations.id"))
    proposed_relative_path = Column(String(500), nullable=False)
    action_type = Column(String(50), nullable=False)
    status = Column(String(20), default="pending")
    error_message = Column(Text, nullable=True)
    executed_at = Column(DateTime, nullable=True)

    location = relationship("FileLocation", back_populates="migration_plans")


# Relationships
Taxonomy.software_products = relationship("SoftwareProduct", back_populates="taxonomy", cascade="all, delete-orphan")
SoftwareProduct.binary_assets = relationship("BinaryAsset", back_populates="product", cascade="all, delete-orphan")
BinaryAsset.file_locations = relationship("FileLocation", back_populates="asset", cascade="all, delete-orphan")
FileLocation.migration_plans = relationship("MigrationPlan", back_populates="location", cascade="all, delete-orphan")


def init_catalog_db(engine):
    """Initialize the catalog database with WAL mode and FTS5 schema."""
    Base.metadata.create_all(engine)
    
    if engine.dialect.name == "sqlite":
        with engine.connect() as conn:
            with conn.begin():
                conn.execute(text("PRAGMA journal_mode=WAL"))
                conn.execute(text("""
                    CREATE VIRTUAL TABLE IF NOT EXISTS catalog_fts USING fts5(
                        canonical_vendor, 
                        canonical_name, 
                        summary_description, 
                        pe_original_filename,
                        content='software_products',
                        content_rowid='id'
                    )
                """))
                conn.execute(text("CREATE INDEX IF NOT EXISTS idx_assets_hash ON binary_assets(sha256_hash)"))
                conn.execute(text("CREATE INDEX IF NOT EXISTS idx_assets_product ON binary_assets(product_id)"))
                conn.execute(text("CREATE INDEX IF NOT EXISTS idx_locations_asset ON file_locations(asset_id)"))
                conn.execute(text("CREATE INDEX IF NOT EXISTS idx_migration_status ON migration_plans(status)"))
