"""Job normalizer: extracts structured attributes, skills, experience, and fingerprints."""

import re
from datetime import UTC, datetime

from app.db.models import JobStatus, NormalizedJob
from app.jobs.freshness import (
    calculate_job_freshness,
    extract_visa_sponsorship,
    extract_workplace_type,
)
from app.jobs.models import FreshnessStatus

# Standard VLSI/Semiconductor skill dictionary
VLSI_SKILL_KEYWORDS = [
    ("SystemVerilog", r"\b(?:system\s*verilog|sv)\b"),
    ("Verilog", r"\bverilog\b"),
    ("UVM", r"\buvm\b"),
    ("OVM", r"\bovm\b"),
    ("SVA", r"\b(?:sva|system\s*verilog\s*assertions|assertions)\b"),
    ("Functional Coverage", r"\b(?:functional\s*coverage|covergroups?|coverpoints?)\b"),
    ("Constrained Random", r"\b(?:constrained\s*random(?:ization)?|crv)\b"),
    ("AXI", r"\baxi(?:3|4)?(?:-lite|-stream)?\b"),
    ("AHB", r"\bahb\b"),
    ("APB", r"\bapb\b"),
    ("FIFO", r"\bfifo\b"),
    ("CDC", r"\b(?:cdc|clock\s*domain\s*crossing)\b"),
    ("VCS", r"\bvcs\b"),
    ("Questa", r"\b(?:questa(?:sim)?|modelsim)\b"),
    ("Incisive/Xcelium", r"\b(?:xcelium|incisive)\b"),
    ("Digital Design", r"\b(?:digital\s*design|digital\s*logic)\b"),
    ("RTL", r"\brtl(?:\s*design)?\b"),
    ("Python", r"\bpython\b"),
    ("Perl", r"\bperl\b"),
    ("Tcl", r"\btcl\b"),
    ("Linux", r"\blinux\b"),
    ("C/C++", r"\b(?:c\+\+|c)\b"),
    ("Formal Verification", r"\bformal\s*verification\b"),
    ("UVM RAL", r"\b(?:uvm\s*ral|ral|register\s*abstraction\s*layer)\b"),
    ("Gate Level Simulation", r"\b(?:gls|gate\s*level\s*sim(?:ulation)?)\b"),
    ("Synthesis", r"\bsynthesis\b"),
    ("Static Timing Analysis", r"\b(?:sta|static\s*timing\s*analysis)\b"),
]


def generate_job_fingerprint(company: str, title: str, location: str | None = None) -> str:
    """Generate a deterministic, lowercase slug fingerprint for job deduplication."""
    comp_clean = re.sub(r"[^\w]", "", company.lower())
    title_clean = re.sub(r"[^\w]", "", title.lower())
    loc_clean = re.sub(r"[^\w]", "", (location or "remote").lower())
    return f"{comp_clean}-{title_clean}-{loc_clean}"


def extract_vlsi_skills(text: str) -> list[str]:
    """Scan text against standard VLSI skill patterns and return unique matched skills."""
    matched = []
    for skill_name, pattern in VLSI_SKILL_KEYWORDS:
        if re.search(pattern, text, re.IGNORECASE):
            matched.append(skill_name)
    return matched


def extract_experience_requirements(text: str) -> tuple[float | None, float | None]:
    """Extract minimum and maximum years of experience from job text."""
    # Pattern: "0-2 years", "0 to 1 year", "1-3 yrs"
    range_match = re.search(
        r"(\d+(?:\.\d+)?)\s*(?:-|to)\s*(\d+(?:\.\d+)?)\s*(?:years?|yrs?)",
        text,
        re.IGNORECASE,
    )
    if range_match:
        return float(range_match.group(1)), float(range_match.group(2))

    # Pattern: "2+ years", "at least 3 years", "minimum 1 year"
    min_match = re.search(
        r"(?:minimum|at least|min\.?)\s*(\d+(?:\.\d+)?)\s*(?:years?|yrs?)",
        text,
        re.IGNORECASE,
    )
    if min_match:
        return float(min_match.group(1)), None

    plus_match = re.search(r"(\d+(?:\.\d+)?)\+\s*(?:years?|yrs?)", text, re.IGNORECASE)
    if plus_match:
        return float(plus_match.group(1)), None

    # Fresher keywords
    if re.search(r"\b(?:fresher|entry[\s-]level|intern(?:ship)?|trainee|college\s*grad(?:uate)?|recent\s*grad(?:uate)?|new\s*grad)\b", text, re.IGNORECASE):
        return 0.0, 1.0

    return None, None


def extract_graduation_years(text: str) -> tuple[int | None, int | None]:
    """Extract graduation/passout year requirements (e.g. 2024, 2025 batch)."""
    # Pattern: "2024 - 2025 batch" or "2024 / 2025"
    batch_range = re.search(
        r"\b(202[0-9])\s*(?:-|/|to)\s*(202[0-9])\b\s*(?:batch|passouts?|graduates?)?",
        text,
        re.IGNORECASE,
    )
    if batch_range:
        return int(batch_range.group(1)), int(batch_range.group(2))

    # Single year: "2025 batch", "2025 passout"
    single_year = re.search(
        r"\b(202[0-9])\s*(?:batch|passout|graduate|pass-out|class of)\b",
        text,
        re.IGNORECASE,
    )
    if single_year:
        year = int(single_year.group(1))
        return year, year

    return None, None


def detect_seniority_flag(title: str, exp_min: float | None = None) -> bool:
    """Return True if the title or experience level indicates a senior/incompatible role."""
    senior_pattern = r"\b(?:sr\.?|senior|principal|staff|lead|manager|director|architect|head|vp)\b"
    return bool(
        re.search(senior_pattern, title, re.IGNORECASE)
        or (exp_min is not None and exp_min >= 2.5)
    )





def normalize_job_listing(
    company: str,
    title: str,
    raw_text: str,
    location: str | None = None,
    country: str | None = "India",
    employment_type: str | None = "Full-time",
    source: str = "manual",
    application_url: str | None = None,
    raw_job_id: int | None = None,
    published_at: str | None = None,
    workplace_type: str | None = None,
    visa_sponsorship: str | None = None,
    source_references: list[str] | None = None,
) -> NormalizedJob:
    """Convert raw job details into a fully validated NormalizedJob record."""
    now_iso = datetime.now(UTC).isoformat()
    exp_min, exp_max = extract_experience_requirements(raw_text)
    grad_min, grad_max = extract_graduation_years(raw_text)
    skills = extract_vlsi_skills(raw_text)

    # Infer employment type if not provided
    if not employment_type or employment_type == "Full-time":
        if re.search(r"\bintern(?:ship)?\b", title, re.IGNORECASE) or re.search(
            r"\bintern(?:ship)?\b", raw_text, re.IGNORECASE
        ):
            employment_type = "Internship"
        elif re.search(r"\btrainee\b", title, re.IGNORECASE) or re.search(
            r"\btrainee\b", raw_text, re.IGNORECASE
        ):
            employment_type = "Trainee"

    fingerprint = generate_job_fingerprint(company=company, title=title, location=location)

    # Freshness calculation
    freshness_status, age_hours, _ = calculate_job_freshness(published_at)

    # Workplace & visa extraction
    workplace = workplace_type or extract_workplace_type(raw_text)
    visa = visa_sponsorship or extract_visa_sponsorship(raw_text)

    return NormalizedJob(
        raw_job_id=raw_job_id,
        company=company.strip(),
        title=title.strip(),
        location=location.strip() if location else None,
        country=country.strip() if country else None,
        employment_type=employment_type,
        experience_min=exp_min,
        experience_max=exp_max,
        graduation_year_min=grad_min,
        graduation_year_max=grad_max,
        description=raw_text.strip(),
        requirements=None,
        skills=skills,
        application_url=application_url,
        source=source,
        status=JobStatus.ACTIVE,
        first_seen=now_iso,
        last_seen=now_iso,
        fingerprint=fingerprint,
        published_at=published_at,
        freshness_status=freshness_status.value if isinstance(freshness_status, FreshnessStatus) else str(freshness_status),
        freshness_age_hours=age_hours,
        workplace_type=workplace,
        visa_sponsorship=visa,
        source_references=source_references or [source],
    )

