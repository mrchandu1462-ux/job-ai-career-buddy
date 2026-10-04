"""Loaders for profile.yaml and facts.yaml."""

from pathlib import Path

import yaml
from pydantic import ValidationError

from app.config import settings
from app.profile.models import CandidateProfile, FactBank


class ProfileLoadError(Exception):
    """Raised when profile configuration fails to load or validate."""


class FactBankLoadError(Exception):
    """Raised when fact bank fails to load or validate."""


def load_profile(path: Path | str | None = None) -> CandidateProfile:
    """Load and strictly validate the candidate profile from YAML."""
    target_path = Path(path) if path is not None else settings.profile_file

    if not target_path.exists():
        raise ProfileLoadError(f"Candidate profile file not found at: {target_path}")

    try:
        with open(target_path, "r", encoding="utf-8") as f:
            raw_data = yaml.safe_load(f)
    except yaml.YAMLError as exc:
        raise ProfileLoadError(f"Malformed YAML in profile file ({target_path}): {exc}") from exc

    if not isinstance(raw_data, dict):
        raise ProfileLoadError(
            f"Invalid structure in profile file ({target_path}): expected YAML mapping/dictionary"
        )

    try:
        return CandidateProfile.model_validate(raw_data)
    except ValidationError as exc:
        raise ProfileLoadError(
            f"Candidate profile validation failed for {target_path}:\n{exc}"
        ) from exc


def load_fact_bank(path: Path | str | None = None) -> FactBank:
    """Load and strictly validate the Fact Bank from YAML."""
    target_path = Path(path) if path is not None else settings.facts_file

    if not target_path.exists():
        raise FactBankLoadError(f"Fact bank file not found at: {target_path}")

    try:
        with open(target_path, "r", encoding="utf-8") as f:
            raw_data = yaml.safe_load(f)
    except yaml.YAMLError as exc:
        raise FactBankLoadError(f"Malformed YAML in facts file ({target_path}): {exc}") from exc

    if raw_data is None:
        raw_data = {"version": "1.0", "facts": []}

    if not isinstance(raw_data, dict):
        raise FactBankLoadError(
            f"Invalid structure in facts file ({target_path}): expected YAML mapping/dictionary"
        )

    try:
        return FactBank.model_validate(raw_data)
    except ValidationError as exc:
        raise FactBankLoadError(
            f"Fact bank validation failed for {target_path}:\n{exc}"
        ) from exc


load_candidate_profile = load_profile

