"""Tests for candidate profile and fact-bank models and loaders."""

from pathlib import Path

import pytest
from pydantic import ValidationError

from app.profile.loader import (
    FactBankLoadError,
    ProfileLoadError,
    load_fact_bank,
    load_profile,
)
from app.profile.models import (
    CandidateProfile,
    CertificationFact,
    EducationFact,
    ExperienceFact,
    FactBank,
    FactCategory,
    FactItem,
    ProjectFact,
    SkillFact,
)


def test_valid_candidate_profile():
    data = {
        "candidate": {
            "target_roles": ["Design Verification Engineer", "RTL Design Engineer"],
            "graduation_year": 2025,
            "experience_level": "Fresher / Entry-Level",
            "locations": {
                "india_priority": ["Bengaluru", "Hyderabad"],
                "overseas_enabled": True,
                "overseas_require_sponsorship": True,
            },
            "work_authorization": {
                "citizen_of": "India",
                "requires_sponsorship_overseas": True,
            },
        }
    }
    profile = CandidateProfile.model_validate(data)
    assert profile.candidate.graduation_year == 2025
    assert len(profile.candidate.target_roles) == 2
    assert profile.candidate.locations.india_priority[0] == "Bengaluru"


def test_invalid_graduation_year():
    data = {
        "candidate": {
            "target_roles": ["Design Verification Engineer"],
            "graduation_year": 1850,  # Invalid graduation year
            "experience_level": "Fresher / Entry-Level",
        }
    }
    with pytest.raises(ValidationError) as excinfo:
        CandidateProfile.model_validate(data)
    assert "Graduation year 1850 is invalid" in str(excinfo.value)

    # Also test future boundary
    data["candidate"]["graduation_year"] = 2050
    with pytest.raises(ValidationError) as excinfo:
        CandidateProfile.model_validate(data)
    assert "Graduation year 2050 is invalid" in str(excinfo.value)


def test_valid_skill_fact():
    fact = SkillFact(
        fact_id="SKILL-SV-01",
        subject="SystemVerilog",
        value={"proficiency": "Academic & Project", "topics": ["Assertions", "OOP", "Randomization"]},
        source="Coursework & Lab verification",
        verified=True,
    )
    assert fact.fact_id == "SKILL-SV-01"
    assert fact.category == FactCategory.SKILL
    assert fact.verified is True
    assert fact.subject == "SystemVerilog"


def test_unverified_fact():
    fact = FactItem(
        fact_id="SKILL-UVM-01",
        category=FactCategory.SKILL,
        subject="UVM",
        value="Basic understanding of UVM testbench structure",
        verified=False,
    )
    assert fact.verified is False

    bank = FactBank(facts=[fact])
    assert len(bank.get_verified_facts()) == 0
    assert len(bank.get_unverified_facts()) == 1
    assert bank.get_unverified_facts()[0].fact_id == "SKILL-UVM-01"


def test_specialized_fact_types():
    edu = EducationFact(
        fact_id="EDU-001",
        subject="B.Tech ECE",
        value={"degree": "B.Tech", "major": "ECE", "year": 2025},
        verified=True,
    )
    assert edu.category == FactCategory.EDUCATION

    proj = ProjectFact(
        fact_id="PROJ-001",
        subject="APB Bridge Verification",
        value={"technologies": ["SystemVerilog", "UVM"]},
        verified=True,
    )
    assert proj.category == FactCategory.PROJECT

    exp = ExperienceFact(
        fact_id="EXP-001",
        subject="VLSI Training Intern",
        value={"role": "Intern"},
        verified=False,
    )
    assert exp.category == FactCategory.EXPERIENCE

    cert = CertificationFact(
        fact_id="CERT-001",
        subject="Advanced Verilog Certificate",
        value={"issuer": "Online Institute"},
        verified=True,
    )
    assert cert.category == FactCategory.CERTIFICATION


def test_invalid_fact_structure():
    # Missing required field 'subject'
    with pytest.raises(ValidationError):
        FactItem.model_validate({
            "fact_id": "FACT-001",
            "category": "skill",
            "value": "Verilog",
        })

    # Empty fact_id
    with pytest.raises(ValidationError):
        FactItem(
            fact_id="   ",
            category=FactCategory.SKILL,
            subject="Verilog",
            value="HDL",
        )

    # Forbidden extra fields
    with pytest.raises(ValidationError):
        FactItem.model_validate({
            "fact_id": "FACT-001",
            "category": "skill",
            "subject": "Verilog",
            "value": "HDL",
            "random_extra_field": "disallowed",
        })


def test_missing_required_fields_in_candidate_profile():
    with pytest.raises(ValidationError):
        CandidateProfile.model_validate({"candidate": {}})


def test_duplicate_fact_ids():
    fact1 = FactItem(
        fact_id="DUP-001",
        category=FactCategory.SKILL,
        subject="Verilog",
        value="Level 1",
    )
    fact2 = FactItem(
        fact_id="DUP-001",
        category=FactCategory.EDUCATION,
        subject="B.Tech",
        value="Level 2",
    )
    with pytest.raises(ValidationError) as excinfo:
        FactBank(facts=[fact1, fact2])
    assert "Duplicate fact_id(s) found in FactBank: DUP-001" in str(excinfo.value)


def test_loading_yaml_files_successfully():
    profile = load_profile()
    assert profile.candidate.graduation_year == 2025
    assert len(profile.candidate.target_roles) > 0
    assert "Bengaluru" in profile.candidate.locations.india_priority

    fact_bank = load_fact_bank()
    assert fact_bank.version == "1.0"
    assert isinstance(fact_bank.facts, list)


def test_loader_error_handling(tmp_path: Path):
    # Non-existent file
    missing_file = tmp_path / "non_existent.yaml"
    with pytest.raises(ProfileLoadError, match="not found"):
        load_profile(missing_file)
    with pytest.raises(FactBankLoadError, match="not found"):
        load_fact_bank(missing_file)

    # Malformed YAML
    bad_yaml = tmp_path / "bad.yaml"
    bad_yaml.write_text("candidate: [unbalanced list", encoding="utf-8")
    with pytest.raises(ProfileLoadError, match="Malformed YAML"):
        load_profile(bad_yaml)

    # Invalid profile schema
    bad_schema = tmp_path / "bad_schema.yaml"
    bad_schema.write_text("candidate:\n  graduation_year: 1700\n", encoding="utf-8")
    with pytest.raises(ProfileLoadError, match="Candidate profile validation failed"):
        load_profile(bad_schema)
