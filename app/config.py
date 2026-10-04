from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class AppSettings(BaseSettings):
    """Application configuration and file system paths."""

    model_config = SettingsConfigDict(
        env_prefix="JOB_AI_",
        env_file=".env",
        extra="ignore",
    )

    # Base Paths
    base_dir: Path = Field(default_factory=lambda: Path(__file__).resolve().parent.parent)
    data_dir: Path = Field(default_factory=lambda: Path(__file__).resolve().parent.parent / "data")
    profile_dir: Path = Field(default_factory=lambda: Path(__file__).resolve().parent.parent / "profile")

    # File locations
    profile_file: Path = Field(
        default_factory=lambda: Path(__file__).resolve().parent.parent / "profile" / "profile.yaml"
    )
    facts_file: Path = Field(
        default_factory=lambda: Path(__file__).resolve().parent.parent / "profile" / "facts.yaml"
    )
    database_url: str = "sqlite:///data/job_ai.db"

    # Default Target Roles
    target_roles: list[str] = [
        "Design Verification Engineer",
        "Functional Verification Engineer",
        "ASIC Verification Engineer",
        "SoC Verification Engineer",
        "RTL Design Engineer",
        "Verification Intern",
        "RTL Design Intern",
        "VLSI Intern",
        "Graduate Engineer Trainee",
    ]

    # Target Locations
    india_priority_locations: list[str] = [
        "Bengaluru",
        "Hyderabad",
        "Chennai",
        "Pune",
        "Noida",
    ]


settings = AppSettings()
