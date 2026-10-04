"""Pydantic models for resume export validation reports and formats."""

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class ExportFormat(str, Enum):
    """Supported ATS-safe resume export formats."""

    DOCX = "docx"
    PDF = "pdf"
    PLAINTEXT = "plaintext"
    MARKDOWN = "markdown"


class ExportValidationReport(BaseModel):
    """Audit report verifying that an exported resume file matches validated facts without corruption."""

    model_config = ConfigDict(extra="forbid")

    status: str = Field(..., description="'PASS' or 'FAIL'")
    format: ExportFormat = Field(..., description="Format of the validated export.")
    resume_id: str = Field(..., description="Target tailored resume identifier.")
    resume_version: int = Field(..., ge=1, description="Version number of the tailored resume.")
    output_path: str = Field(..., description="Filesystem path of the exported artifact.")
    extracted_text_length: int = Field(..., ge=0, description="Character count of extractable text.")
    missing_sections: list[str] = Field(default_factory=list, description="Any expected sections absent in exported file.")
    content_mismatches: list[str] = Field(default_factory=list, description="Discrepancies between validated model and export.")
    parser_warnings: list[str] = Field(default_factory=list, description="ATS parser-safety warnings.")
    errors: list[str] = Field(default_factory=list, description="Fatal export validation errors.")
    is_export_validated: bool = Field(..., description="True only if status is PASS and errors is empty.")
