"""Data models for candidate profile and fact bank."""

from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class FactCategory(str, Enum):
    """Supported categories for fact-bank claims."""

    EDUCATION = "education"
    SKILL = "skill"
    PROJECT = "project"
    EXPERIENCE = "experience"
    CERTIFICATION = "certification"
    COURSEWORK = "coursework"
    OTHER = "other"


class FactItem(BaseModel):
    """Base atomic claim in the Fact Bank with full provenance tracking."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    fact_id: str = Field(
        ...,
        min_length=1,
        description="Unique identifier for the fact (e.g., EDU-001, SKILL-001).",
    )
    category: FactCategory = Field(
        ...,
        description="Category classification of the fact.",
    )
    subject: str = Field(
        ...,
        min_length=1,
        description="Subject of the fact (e.g., 'SystemVerilog', 'B.Tech ECE', 'APB Bridge').",
    )
    value: Any = Field(
        ...,
        description="Value, details, or payload representing the factual statement.",
    )
    source: str | None = Field(
        default=None,
        description="Verification source or document proof (e.g. 'Degree Certificate', 'GitHub').",
    )
    verified: bool = Field(
        default=False,
        description="Flag indicating whether this fact is independently verified.",
    )
    notes: str | None = Field(
        default=None,
        description="Additional context, constraints, or caveats for this fact.",
    )

    @field_validator("fact_id")
    @classmethod
    def validate_fact_id(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("fact_id cannot be empty or whitespace only")
        return v.strip()


class EducationFact(FactItem):
    """Fact item specialized for educational qualifications."""

    category: FactCategory = Field(default=FactCategory.EDUCATION)


class SkillFact(FactItem):
    """Fact item specialized for verified technical or domain skills."""

    category: FactCategory = Field(default=FactCategory.SKILL)


class ProjectFact(FactItem):
    """Fact item specialized for academic or personal projects."""

    category: FactCategory = Field(default=FactCategory.PROJECT)


class ExperienceFact(FactItem):
    """Fact item specialized for prior work, internship, or training experience."""

    category: FactCategory = Field(default=FactCategory.EXPERIENCE)


class CertificationFact(FactItem):
    """Fact item specialized for verified certifications."""

    category: FactCategory = Field(default=FactCategory.CERTIFICATION)


class FactBank(BaseModel):
    """Collection of facts with uniqueness constraints and query helpers."""

    model_config = ConfigDict(extra="forbid")

    version: str = Field(default="1.0", description="Schema version of the fact bank.")
    facts: list[FactItem] = Field(
        default_factory=list,
        description="List of atomic facts about the candidate.",
    )

    @model_validator(mode="after")
    def check_unique_fact_ids(self) -> "FactBank":
        seen_ids = set()
        duplicates = []
        for fact in self.facts:
            if fact.fact_id in seen_ids:
                duplicates.append(fact.fact_id)
            seen_ids.add(fact.fact_id)
        if duplicates:
            raise ValueError(f"Duplicate fact_id(s) found in FactBank: {', '.join(duplicates)}")
        return self

    def get_fact(self, fact_id: str) -> FactItem | None:
        """Retrieve a fact by its unique fact_id."""
        for fact in self.facts:
            if fact.fact_id == fact_id:
                return fact
        return None

    def get_verified_facts(self) -> list[FactItem]:
        """Retrieve all verified facts."""
        return [f for f in self.facts if f.verified]

    def get_unverified_facts(self) -> list[FactItem]:
        """Retrieve all unverified facts."""
        return [f for f in self.facts if not f.verified]

    def get_facts_by_category(self, category: FactCategory | str) -> list[FactItem]:
        """Retrieve all facts belonging to a specific category."""
        cat = FactCategory(category) if isinstance(category, str) else category
        return [f for f in self.facts if f.category == cat]


class CandidateLocations(BaseModel):
    """Location preferences for job filtering."""

    model_config = ConfigDict(extra="forbid")

    india_priority: list[str] = Field(
        default_factory=lambda: [
            "Bengaluru",
            "Hyderabad",
            "Chennai",
            "Pune",
            "Noida",
            "Gurugram",
            "Ahmedabad",
            "Mysuru",
            "Kochi",
            "Mumbai",
        ],
        description="Prioritized Indian tech hubs for job discovery.",
    )
    india_tier1: list[str] = Field(
        default_factory=lambda: ["Bengaluru", "Hyderabad", "Chennai"],
        description="Top-priority Tier 1 domestic semiconductor hubs.",
    )
    india_tier2: list[str] = Field(
        default_factory=lambda: [
            "Pune",
            "Noida",
            "Gurugram",
            "Ahmedabad",
            "Mysuru",
            "Kochi",
            "Mumbai",
        ],
        description="Tier 2 domestic semiconductor development centers.",
    )
    overseas_enabled: bool = Field(
        default=True,
        description="Whether to search for overseas roles.",
    )
    overseas_require_sponsorship: bool = Field(
        default=True,
        description="Whether overseas applications require visa sponsorship.",
    )
    overseas_priority_countries: list[str] = Field(
        default_factory=lambda: [
            "USA",
            "Canada",
            "UK",
            "Germany",
            "Netherlands",
            "Singapore",
            "Taiwan",
            "Japan",
            "South Korea",
            "Ireland",
            "Australia",
            "UAE",
            "France",
            "Sweden",
            "Switzerland",
        ],
        description="Target international semiconductor markets.",
    )


class WorkAuthorization(BaseModel):
    """Candidate work authorization and citizenship status."""

    model_config = ConfigDict(extra="forbid")

    citizen_of: str = Field(
        default="India",
        description="Country of citizenship.",
    )
    requires_sponsorship_overseas: bool = Field(
        default=True,
        description="Whether visa sponsorship is required for non-domestic roles.",
    )


class CandidateDetails(BaseModel):
    """Detailed candidate profile preferences and hard eligibility attributes."""

    model_config = ConfigDict(extra="forbid")

    target_roles: list[str] = Field(
        ...,
        min_length=1,
        description="List of target job titles (e.g. Design Verification Engineer).",
    )
    tier1_target_roles: list[str] = Field(
        default_factory=lambda: [
            "Design Verification Engineer",
            "Functional Verification Engineer",
            "ASIC Verification Engineer",
            "SoC Verification Engineer",
        ],
        description="Primary Tier 1 target roles (highest scoring priority).",
    )
    tier2_target_roles: list[str] = Field(
        default_factory=lambda: [
            "RTL Design Engineer",
            "Verification Intern",
            "RTL Design Intern",
            "VLSI Intern",
        ],
        description="Secondary Tier 2 target roles.",
    )
    tier3_target_roles: list[str] = Field(
        default_factory=lambda: [
            "Graduate Engineer Trainee",
            "Semiconductor Graduate Engineer",
        ],
        description="Tier 3 entry-level / trainee roles.",
    )
    tier4_target_roles: list[str] = Field(
        default_factory=lambda: [
            "Hardware Engineer",
            "Digital Design Engineer",
            "FPGA Engineer",
        ],
        description="Tier 4 general semiconductor engineering roles.",
    )
    graduation_year: int = Field(
        ...,
        description="Year of graduation (must be realistic).",
    )
    experience_level: str = Field(
        default="Fresher / Entry-Level",
        description="Experience classification (e.g. Fresher / Entry-Level).",
    )
    locations: CandidateLocations = Field(
        default_factory=CandidateLocations,
        description="Geographic preferences.",
    )
    work_authorization: WorkAuthorization = Field(
        default_factory=WorkAuthorization,
        description="Work authorization status.",
    )

    @field_validator("graduation_year")
    @classmethod
    def validate_graduation_year(cls, year: int) -> int:
        if year < 1990 or year > 2035:
            raise ValueError(
                f"Graduation year {year} is invalid. Must be between 1990 and 2035."
            )
        return year


class CandidateProfile(BaseModel):
    """Top-level container for candidate configuration."""

    model_config = ConfigDict(extra="forbid")

    candidate: CandidateDetails
