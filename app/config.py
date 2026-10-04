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

    # Email & Notification Settings
    email_enabled: bool = False
    email_provider: str = "console"  # "console", "smtp", "sendgrid", "resend"
    email_from: str = "alerts@job-ai.local"
    email_to: str = "candidate@vlsi-career.internal"
    email_api_key: str | None = None
    email_smtp_host: str | None = None
    email_smtp_port: int = 587
    email_username: str | None = None
    email_password: str | None = None
    email_use_tls: bool = True
    email_use_ssl: bool = False
    email_timeout_seconds: int = 30
    email_max_retries: int = 3

    # Digest Settings
    digest_enabled: bool = True
    digest_hour: int = 19  # 7 PM local/configured
    dashboard_url: str = "http://localhost:8501"


settings = AppSettings()


def get_settings() -> AppSettings:
    """Return the global application settings instance."""
    return settings


