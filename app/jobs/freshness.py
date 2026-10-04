"""Freshness calculation, alert priority scoring, geography classification, and workplace extraction."""

import re
from datetime import UTC, datetime
from typing import Any

from app.jobs.models import (
    AlertPriority,
    FreshnessStatus,
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
]


def calculate_job_freshness(
    published_at: str | None,
    current_time: datetime | None = None,
    now: datetime | None = None,
) -> tuple[FreshnessStatus, float | None, float]:
    """
    Calculate verifiable job freshness tier, age in hours, and confidence.
    Never fabricates publication time if unknown or vague.
    """
    if not published_at or not str(published_at).strip():
        return FreshnessStatus.UNKNOWN, None, 0.0

    pub_str = str(published_at).strip()

    # Reject vague relative strings that cannot be objectively verified
    if re.search(r"\b(?:recently|just now|new opening|today|active)\b", pub_str, re.IGNORECASE) and not re.search(r"\d", pub_str):
        return FreshnessStatus.UNKNOWN, None, 0.0

    ref_time = now or current_time or datetime.now(UTC)

    try:
        # 1. Try full ISO-8601 parsing
        clean_iso = pub_str.replace("Z", "+00:00")
        if "T" in clean_iso:
            pub_dt = datetime.fromisoformat(clean_iso)
            if pub_dt.tzinfo is None:
                pub_dt = pub_dt.replace(tzinfo=UTC)
            age_hours = max(0.0, (ref_time - pub_dt).total_seconds() / 3600.0)
            confidence = 1.0
        else:
            # 2. Date-only format (e.g. 2026-10-04) - calculate conservatively
            date_match = re.match(r"^(\d{4})-(\d{2})-(\d{2})", clean_iso)
            if date_match:
                year, month, day = map(int, date_match.groups())
                # Conservative: assume end of day to not artificially inflate freshness
                pub_dt = datetime(year, month, day, 12, 0, 0, tzinfo=UTC)
                age_hours = max(0.0, (ref_time - pub_dt).total_seconds() / 3600.0)
                confidence = 0.85
            else:
                return FreshnessStatus.UNKNOWN, None, 0.0

    except (ValueError, TypeError, OverflowError):
        return FreshnessStatus.UNKNOWN, None, 0.0

    # Categorize into deterministic freshness tiers
    if age_hours < 6.0:
        return FreshnessStatus.FRESH_0_6_HOURS, round(age_hours, 2), confidence
    if age_hours <= 24.0:
        return FreshnessStatus.FRESH_6_24_HOURS, round(age_hours, 2), confidence
    if age_hours <= 72.0:
        return FreshnessStatus.RECENT_1_3_DAYS, round(age_hours, 2), confidence

    return FreshnessStatus.OLDER, round(age_hours, 2), confidence


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


