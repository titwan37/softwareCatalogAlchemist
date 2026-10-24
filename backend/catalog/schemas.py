from enum import Enum
from typing import Optional, List
import re

from pydantic import BaseModel, Field, field_validator


class ArchitectureEnum(str, Enum):
    x86 = "x86"
    x64 = "x64"
    ARM64 = "ARM64"
    Universal = "Universal"
    Unknown = "Unknown"


class ActionTypeEnum(str, Enum):
    MOVE = "MOVE"
    COPY = "COPY"
    DELETE_DUPLICATE = "DELETE_DUPLICATE"
    SKIP_LOW_CONFIDENCE = "SKIP_LOW_CONFIDENCE"


class MigrationStatusEnum(str, Enum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    EXECUTED = "EXECUTED"
    FAILED = "FAILED"
    ROLLED_BACK = "ROLLED_BACK"


class RawBinaryMetadata(BaseModel):
    sha256_hash: str
    file_size_bytes: int
    file_extension: str
    architecture: ArchitectureEnum
    pe_company_name: Optional[str] = None
    pe_product_name: Optional[str] = None
    pe_file_description: Optional[str] = None
    pe_original_filename: Optional[str] = None
    detected_version: Optional[str] = None
    msi_product_code: Optional[str] = None
    digital_signature_subject: Optional[str] = None
    parent_folder_chain: Optional[str] = None

    @field_validator('file_extension')
    def validate_extension(cls, v):
        if not v.endswith('.'):
            return v + '.'
        return v


class LLMClassificationResult(BaseModel):
    canonical_vendor: str
    canonical_product: str
    detected_version: Optional[str] = None
    architecture: ArchitectureEnum
    primary_category: str
    subcategory: Optional[str] = None
    license_model: Optional[str] = None
    summary: str
    confidence_score: float
    reasoning: str

    @field_validator('confidence_score')
    def validate_confidence(cls, v):
        if not (0 <= v <= 1):
            raise ValueError('Confidence score must be between 0 and 1')
        return v


class MigrationProposalContract(BaseModel):
    location_id: int
    current_full_path: str
    proposed_relative_path: str
    action_type: ActionTypeEnum
    confidence_score: float

    @field_validator('current_full_path', 'proposed_relative_path')
    def validate_path_characters(cls, v):
        illegal_chars = [':', '*', '?', '"', '<', '>', '|']
        for char in illegal_chars:
            if char in v:
                raise ValueError(f"Path contains illegal character: {char}")
        return v
