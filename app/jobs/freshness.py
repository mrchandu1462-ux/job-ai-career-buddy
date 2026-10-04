"""Freshness calculation, 8-dimensional priority scoring, geography classification, and visa sponsorship extraction."""

import re
from datetime import UTC, datetime
from typing import Any

from app.db.models import (
    AlertPriority,
    FreshJobPriorityScore,
    FreshnessBucket,
    FreshnessConfidence,
    FreshnessStatus,
    JobPriorityCategory,
    VisaSponsorshipCategory,
    VisaSponsorshipStatus,
    WorkplaceType,
)

# Priority Semiconductor Hubs in India
INDIA_PRIORITY_HUBS = [
    "bengaluru",
    "bangalore",
    "hyderabad",
    "chennai",
    "pune",
    "noida",
    "gurugram",
    "gurgaon",
    "delhi",
    "ncr",
    "mumbai",
    "ahmedabad",
    "kochi",
    "mysuru",
    "mysore",
]

# Supported Overseas Semiconductor Markets
OVERSEAS_COUNTRIES = [
    "united states",
    "usa",
    "us",
    "canada",
    "united kingdom",
    "uk",
    "germany",
    "netherlands",
    "singapore",
    "australia",
    "united arab emirates",
    "uae",
    "dubai",
    "ireland",
    "japan",
    "taiwan",
    "south korea",
    "israel",
    "france",
    "sweden",
    "switzerland",
    "new zealand",
]


def calculate_granular_freshness(
    published_at: str | None,
    current_time: datetime | None = None,
    now: datetime | None = None,
    source_timestamp: str | None = None,
    timestamp_source: str = "official_listing",
) -> tuple[FreshnessBucket, float | None, FreshnessConfidence, str]:
    """
    Calculate granular 24-hour publication freshness bucket, age in hours, and confidence.
    Zero-fabrication: If posting date cannot be verified or parsed, confidence is LOW/UNKNOWN
    and the system will NEVER falsely classify the job as <= 24h.
    """
    effective_raw = published_at or source_timestamp
    if not effective_raw or not str(effective_raw).strip():
        return FreshnessBucket.UNKNOWN, None, FreshnessConfidence.LOW, "unverified"

    pub_str = str(effective_raw).strip()

    # Reject vague relative strings that cannot be objectively verified
    if re.search(r"\b(?:recently|just now|new opening|today|active)\b", pub_str, re.IGNORECASE) and not re.search(r"\d", pub_str):
        return FreshnessBucket.UNKNOWN, None, FreshnessConfidence.LOW, "unverified"

    ref_time = now or current_time or datetime.now(UTC)

    try:
        clean_iso = pub_str.replace("Z", "+00:00")
        if "T" in clean_iso:
            pub_dt = datetime.fromisoformat(clean_iso)
            if pub_dt.tzinfo is None:
                pub_dt = pub_dt.replace(tzinfo=UTC)
            age_hours = max(0.0, (ref_time - pub_dt).total_seconds() / 3600.0)
            confidence = FreshnessConfidence.HIGH
            source_type = timestamp_source or "official_listing"
        else:
            date_match = re.match(r"^(\d{4})-(\d{2})-(\d{2})", clean_iso)
            if date_match:
                year, month, day = map(int, date_match.groups())
                # Conservative: assume 12:00 UTC to prevent artificial <=1h claims
                pub_dt = datetime(year, month, day, 12, 0, 0, tzinfo=UTC)
                age_hours = max(0.0, (ref_time - pub_dt).total_seconds() / 3600.0)
                confidence = FreshnessConfidence.MEDIUM
                source_type = timestamp_source or "date_only_listing"
            else:
                return FreshnessBucket.UNKNOWN, None, FreshnessConfidence.LOW, "unverified"

    except (ValueError, TypeError, OverflowError):
        return FreshnessBucket.UNKNOWN, None, FreshnessConfidence.LOW, "unverified"

    # Map to granular freshness buckets
    if age_hours <= 1.0:
        bucket = FreshnessBucket.LE_1_HOUR
    elif age_hours <= 3.0:
        bucket = FreshnessBucket.LE_3_HOURS
    elif age_hours <= 6.0:
        bucket = FreshnessBucket.LE_6_HOURS
    elif age_hours <= 12.0:
        bucket = FreshnessBucket.LE_12_HOURS
    elif age_hours <= 24.0:
        bucket = FreshnessBucket.LE_24_HOURS
    elif age_hours <= 72.0:
        bucket = FreshnessBucket.DAYS_1_3
    elif age_hours <= 168.0:
        bucket = FreshnessBucket.DAYS_3_7
    else:
        bucket = FreshnessBucket.OLDER_7_DAYS

    return bucket, round(age_hours, 2), confidence, source_type


def calculate_job_freshness(
    published_at: str | None,
    current_time: datetime | None = None,
    now: datetime | None = None,
) -> tuple[FreshnessStatus, float | None, float]:
    """
    Backward-compatible job freshness tier calculation.
    """
    bucket, age_hours, conf_enum, _ = calculate_granular_freshness(
        published_at=published_at,
        current_time=current_time,
        now=now,
    )
    conf_float = 1.0 if conf_enum == FreshnessConfidence.HIGH else (0.85 if conf_enum == FreshnessConfidence.MEDIUM else 0.0)

    if bucket == FreshnessBucket.UNKNOWN or age_hours is None:
        return FreshnessStatus.UNKNOWN, None, 0.0

    if age_hours < 6.0:
        return FreshnessStatus.FRESH_0_6_HOURS, age_hours, conf_float
    if age_hours <= 24.0:
        return FreshnessStatus.FRESH_6_24_HOURS, age_hours, conf_float
    if age_hours <= 72.0:
        return FreshnessStatus.RECENT_1_3_DAYS, age_hours, conf_float

    return FreshnessStatus.OLDER, age_hours, conf_float


def calculate_fresh_job_priority_score(
    match_score: float,
    freshness_bucket: FreshnessBucket,
    freshness_confidence: FreshnessConfidence,
    role_score: float = 85.0,
    project_score: float = 80.0,
    fresher_fit: bool = True,
    is_watchlist: bool = False,
    has_direct_url: bool = True,
    is_india: bool = True,
    visa_supported: bool = False,
) -> FreshJobPriorityScore:
    """
    Calculate explainable 8-dimensional fresh job priority score (0–100):
    1. Freshness: 25%
    2. Technical match: 25%
    3. Role match: 15%
    4. Project relevance: 10%
    5. Experience/fresher fit: 10%
    6. Location/eligibility: 5%
    7. Company/source confidence: 5%
    8. Application accessibility: 5%
    """
    # 1. Freshness Score (max 25)
    if freshness_confidence == FreshnessConfidence.LOW or freshness_bucket == FreshnessBucket.UNKNOWN:
        freshness_pts = 5.0
    elif freshness_bucket == FreshnessBucket.LE_1_HOUR:
        freshness_pts = 25.0
    elif freshness_bucket == FreshnessBucket.LE_3_HOURS:
        freshness_pts = 24.0
    elif freshness_bucket == FreshnessBucket.LE_6_HOURS:
        freshness_pts = 22.0
    elif freshness_bucket == FreshnessBucket.LE_12_HOURS:
        freshness_pts = 20.0
    elif freshness_bucket == FreshnessBucket.LE_24_HOURS:
        freshness_pts = 18.0
    elif freshness_bucket == FreshnessBucket.DAYS_1_3:
        freshness_pts = 12.0
    elif freshness_bucket == FreshnessBucket.DAYS_3_7:
        freshness_pts = 6.0
    else:
        freshness_pts = 0.0

    # 2. Technical Match (max 25)
    tech_pts = round(min(25.0, max(0.0, (match_score / 100.0) * 25.0)), 2)

    # 3. Role Match (max 15)
    role_pts = round(min(15.0, max(0.0, (role_score / 100.0) * 15.0)), 2)

    # 4. Project Relevance (max 10)
    project_pts = round(min(10.0, max(0.0, (project_score / 100.0) * 10.0)), 2)

    # 5. Fresher / Experience Fit (max 10)
    fresher_pts = 10.0 if fresher_fit else 3.0

    # 6. Location / Eligibility (max 5)
    if is_india or visa_supported:
        location_pts = 5.0
    else:
        location_pts = 2.0

    # 7. Company Confidence / Watchlist (max 5)
    company_pts = 5.0 if is_watchlist else 4.0

    # 8. Application Accessibility (max 5)
    accessibility_pts = 5.0 if has_direct_url else 2.0

    total = round(
        freshness_pts
        + tech_pts
        + role_pts
        + project_pts
        + fresher_pts
        + location_pts
        + company_pts
        + accessibility_pts,
        1,
    )
    total = min(100.0, max(0.0, total))

    is_fresh_24h = freshness_bucket in (
        FreshnessBucket.LE_1_HOUR,
        FreshnessBucket.LE_3_HOURS,
        FreshnessBucket.LE_6_HOURS,
        FreshnessBucket.LE_12_HOURS,
        FreshnessBucket.LE_24_HOURS,
    ) and freshness_confidence in (FreshnessConfidence.HIGH, FreshnessConfidence.MEDIUM)

    # Priority category mapping
    if freshness_bucket == FreshnessBucket.OLDER_7_DAYS:
        category = JobPriorityCategory.EXPIRED_STALE
    elif is_fresh_24h and total >= 88.0:
        category = JobPriorityCategory.CRITICAL
    elif is_fresh_24h and total >= 75.0:
        category = JobPriorityCategory.HIGH
    elif total >= 60.0:
        category = JobPriorityCategory.MEDIUM
    else:
        category = JobPriorityCategory.LOW

    is_fresh_24h_match = is_fresh_24h and total >= 75.0

    return FreshJobPriorityScore(
        freshness=freshness_pts,
        technical_match=tech_pts,
        role_match=role_pts,
        project_relevance=project_pts,
        fresher_fit=fresher_pts,
        location_eligibility=location_pts,
        company_confidence=company_pts,
        application_accessibility=accessibility_pts,
        total_score=total,
        category=category,
        is_fresh_24h_match=is_fresh_24h_match,
    )


def calculate_alert_priority(
    match_score: float,
    is_eligible: bool,
    freshness: FreshnessStatus,
    role_category: str = "",
) -> AlertPriority:
    """
    Determine notification alert priority based on freshness, 7D match score, and fresher eligibility.
    """
    if not is_eligible:
        return AlertPriority.UNKNOWN

    # P0: < 24 Hours & Strong candidate match
    if freshness in (FreshnessStatus.FRESH_0_6_HOURS, FreshnessStatus.FRESH_6_24_HOURS):
        if match_score >= 75.0:
            return AlertPriority.P0
        if match_score >= 60.0:
            return AlertPriority.P1
        return AlertPriority.P3

    # P2: 1-3 Days & Strong candidate match
    if freshness == FreshnessStatus.RECENT_1_3_DAYS:
        if match_score >= 78.0:
            return AlertPriority.P2
        return AlertPriority.P3

    # UNKNOWN Freshness handling
    if freshness == FreshnessStatus.UNKNOWN:
        if match_score >= 82.0:
            return AlertPriority.P2
        return AlertPriority.UNKNOWN

    return AlertPriority.P3


def classify_geography(
    location: str | None,
    country: str | None = None,
) -> dict[str, Any]:
    """
    Classify geographic market into India vs Overseas, identify tech hubs, and state details.
    """
    loc_str = (location or "").lower()
    country_str = (country or "").lower()
    combined = f"{loc_str} {country_str}".strip()

    is_india = False
    is_overseas = False
    detected_hub = None
    market_region = "India"

    # 1. Check India Priority Hubs
    for hub in INDIA_PRIORITY_HUBS:
        if re.search(rf"\b{hub}\b", combined):
            is_india = True
            detected_hub = hub.capitalize()
            break

    if "india" in combined or "in" == country_str or "blr" in combined or "hyd" in combined:
        is_india = True

    # 2. Check Overseas
    if not is_india:
        for c in OVERSEAS_COUNTRIES:
            if re.search(rf"\b{c}\b", combined):
                is_overseas = True
                market_region = c.title()
                break

    if not is_india and not is_overseas:
        if any(w in combined for w in ["remote", "worldwide", "global", "anywhere"]):
            market_region = "Global / Remote"
        else:
            market_region = "India"  # Default fallback if unstated
            is_india = True

    return {
        "is_india": is_india,
        "is_overseas": is_overseas,
        "market_region": market_region,
        "priority_hub": detected_hub,
        "country": country or ("India" if is_india else market_region),
    }


def extract_workplace_type(text: str) -> str:
    """Extract workplace setup (remote, hybrid, onsite, unknown) without hallucinating."""
    text_lower = text.lower()
    if re.search(r"\b(?:fully\s*remote|100%\s*remote|remote\s*work|work\s*from\s*home|wfh)\b", text_lower):
        return WorkplaceType.REMOTE.value
    if re.search(r"\b(?:hybrid|flexible\s*work|hybrid\s*work)\b", text_lower):
        return WorkplaceType.HYBRID.value
    if re.search(r"\b(?:on[\s-]site|in[\s-]office|work\s*from\s*office|wfo)\b", text_lower):
        return WorkplaceType.ONSITE.value
    return WorkplaceType.UNKNOWN.value


def extract_visa_sponsorship(text: str) -> str:
    """Extract verified visa sponsorship availability without fabrication."""
    text_lower = text.lower()
    if re.search(r"\b(?:visa\s*sponsorship\s*(?:is\s*)?(?:available|provided|offered)|will\s*sponsor\s*visa|sponsorship\s*(?:is\s*)?available)\b", text_lower):
        return VisaSponsorshipStatus.AVAILABLE.value
    if re.search(r"\b(?:no\s*(?:visa\s*)?sponsorship|cannot\s*sponsor|not\s*able\s*to\s*sponsor|unable\s*to\s*sponsor|sponsorship\s*(?:is\s*)?not\s*provided)\b", text_lower):
        return VisaSponsorshipStatus.NOT_AVAILABLE.value
    if re.search(r"\b(?:us\s*citizens?\s*or\s*green\s*card|citizenship\s*required|must\s*be\s*authorized\s*to\s*work)\b", text_lower):
        return VisaSponsorshipStatus.CITIZEN_OR_PR_ONLY.value
    return VisaSponsorshipStatus.UNKNOWN.value


def classify_visa_sponsorship_category(text: str | None) -> tuple[VisaSponsorshipCategory, FreshnessConfidence]:
    """
    Categorize overseas visa sponsorship explicitly.
    Zero-fabrication rule: If no clear visa evidence exists in the text,
    classify as SPONSORSHIP_UNKNOWN with LOW confidence.
    """
    if not text or not str(text).strip():
        return VisaSponsorshipCategory.SPONSORSHIP_UNKNOWN, FreshnessConfidence.LOW

    text_lower = str(text).lower()

    # 1. Negative / Restrictions take first precedence
    if re.search(
        r"\b(?:no\s*(?:visa\s*)?sponsorship|cannot\s*sponsor|not\s*able\s*to\s*sponsor|unable\s*to\s*sponsor|"
        r"sponsorship\s*(?:is\s*)?not\s*(?:available|provided|offered|supported)|without\s*sponsorship|"
        r"us\s*citizens?|permanent\s*residents?|green\s*card|citizenship\s*required|"
        r"must\s*be\s*authorized\s*to\s*work\s*without)\b",
        text_lower,
    ):
        return VisaSponsorshipCategory.SPONSORSHIP_NOT_SUPPORTED, FreshnessConfidence.HIGH

    # 2. Confirmed positive sponsorship
    if re.search(
        r"\b(?:visa\s*sponsorship\s*(?:is\s*)?(?:available|provided|offered|supported)|"
        r"(?:will|willing\s*to|can)\s*sponsor\s*(?:a\s*)?visa|"
        r"(?:offer|offers|providing|provides)\s*(?:full\s*)?visa\s*sponsorship|"
        r"sponsorship\s*(?:is\s*)?available)\b",
        text_lower,
    ):
        return VisaSponsorshipCategory.SPONSORSHIP_CONFIRMED, FreshnessConfidence.HIGH

    # 3. Possible / Relocation without explicit visa guarantee
    if re.search(r"\b(?:international\s*applicants\s*welcome|relocation\s*(?:assistance|provided)|global\s*mobility)\b", text_lower):
        return VisaSponsorshipCategory.SPONSORSHIP_POSSIBLE, FreshnessConfidence.MEDIUM

    return VisaSponsorshipCategory.SPONSORSHIP_UNKNOWN, FreshnessConfidence.LOW
