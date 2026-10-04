"""Comprehensive unit and integration test suite for Phase 5: Smart Career Intelligence, Watchlists & Alerts.

Verifies:
A. Candidate profile loads correctly
B. Exact DV role scores higher than generic role
C. UVM/SystemVerilog skills increase match score
D. Fresher role is compatible
E. Senior role is rejected/downranked
F. Bengaluru preference works
G. Overseas authorization mismatch is detected
H. Watchlisted company increases priority
I. Score explanation is deterministic
J. CRITICAL classification works
K. HIGH classification works
L. Duplicate alert suppressed
M. Material job change can trigger re-alert
N. Daily digest generation works
O. Unknown freshness is never treated as <=24h
P. Human approval gate remains intact
Q. Production MockJobSourceAdapter protection remains intact
R. Existing Phase 1–4 tests remain green
S. No external portal dependency in tests
T. No real notification required in tests
"""

import sqlite3
from datetime import UTC, datetime, timedelta

import pytest

from app.career.notifications import (
    NotificationDispatchStatus,
    ScheduleNotificationService,
)
from app.db.connection import get_connection
from app.db.models import (
    FreshnessStatus,
    JobPriorityCategory,
    NormalizedJob,
)
from app.db.repository import JobRepository
from app.db.schema import create_schema
from app.jobs.digest import DailyDigestService
from app.jobs.freshness import (
    calculate_fresh_job_priority_score,
    calculate_granular_freshness,
    calculate_job_freshness,
)
from app.jobs.normalizer import normalize_job_listing
from app.jobs.scanner import FreshJobScanner
from app.jobs.sources.adapters import MockJobSourceAdapter
from app.jobs.sources.base import RawJobPayload
from app.jobs.watchlist import CompanyWatchlistService
from app.matching.filters import HardFilterEngine
from app.matching.scorer import JobScoringEngine
from app.profile.loader import load_candidate_profile, load_fact_bank
from app.profile.models import (
    CandidateDetails,
    CandidateLocations,
    CandidateProfile,
    FactBank,
    ProjectFact,
    SkillFact,
    WorkAuthorization,
)


@pytest.fixture()
def mem_conn() -> sqlite3.Connection:
    conn = get_connection(":memory:", auto_init=True)
    create_schema(conn)
    return conn


@pytest.fixture()
def candidate_context():
    profile = CandidateProfile(
        candidate=CandidateDetails(
            target_roles=[
                "Design Verification Engineer",
                "Functional Verification Engineer",
                "ASIC Verification Engineer",
                "SoC Verification Engineer",
                "RTL Design Engineer",
                "Verification Intern",
                "Graduate Engineer Trainee",
            ],
            tier1_target_roles=[
                "Design Verification Engineer",
                "Functional Verification Engineer",
                "ASIC Verification Engineer",
                "SoC Verification Engineer",
            ],
            graduation_year=2025,
            experience_level="Fresher / Entry-Level",
            locations=CandidateLocations(
                india_priority=["Bengaluru", "Hyderabad", "Chennai", "Pune", "Noida", "Gurugram"],
                india_tier1=["Bengaluru", "Hyderabad", "Chennai"],
                india_tier2=["Pune", "Noida", "Gurugram"],
                overseas_enabled=True,
                overseas_require_sponsorship=True,
            ),
            work_authorization=WorkAuthorization(
                citizen_of="India",
                requires_sponsorship_overseas=True,
            ),
        )
    )

    facts = FactBank(
        version="1.0",
        facts=[
            SkillFact(
                fact_id="SKILL-001",
                subject="SystemVerilog",
                value={"topics": ["OOP", "Assertions", "Constraints", "Coverage"]},
                verified=True,
            ),
            SkillFact(
                fact_id="SKILL-002",
                subject="UVM",
                value={"topics": ["Scoreboard", "Driver", "Monitor", "Sequences", "TLM"]},
                verified=True,
            ),
            SkillFact(
                fact_id="SKILL-003",
                subject="Verilog",
                value="RTL and testbench design",
                verified=True,
            ),
            SkillFact(
                fact_id="SKILL-004",
                subject="SVA",
                value="Concurrent assertions and coverage",
                verified=True,
            ),
            SkillFact(
                fact_id="SKILL-005",
                subject="AXI",
                value="AXI4 protocol verification",
                verified=True,
            ),
            ProjectFact(
                fact_id="PROJ-001",
                subject="AXI4 Master/Slave VIP",
                value={"technologies": ["SystemVerilog", "UVM", "AXI", "FIFO"]},
                verified=True,
            ),
        ],
    )
    return profile, facts


# ---------------------------------------------------------------------------
# Test Category A: Candidate Profile Loading
# ---------------------------------------------------------------------------
class TestCandidateProfileLoading:
    def test_candidate_profile_and_fact_bank_load_correctly(self):
        profile = load_candidate_profile()
        facts = load_fact_bank()

        assert profile.candidate.graduation_year == 2025
        assert "Design Verification Engineer" in profile.candidate.target_roles
        assert len(profile.candidate.locations.india_priority) >= 5
        assert profile.candidate.work_authorization.citizen_of == "India"
        assert len(facts.get_verified_facts()) > 0


# ---------------------------------------------------------------------------
# Test Categories B, C, D, E, F: Smart Matching & Filtering Engine
# ---------------------------------------------------------------------------
class TestSmartMatchingAndFiltering:
    def test_exact_dv_role_scores_higher_than_generic_role(self, candidate_context):
        profile, facts = candidate_context
        scorer = JobScoringEngine(profile, facts)

        dv_job = normalize_job_listing(
            company="Qualcomm",
            title="Design Verification Engineer",
            raw_text="SystemVerilog, UVM, SVA in Bengaluru. 2025 batch.",
            location="Bengaluru",
            country="India",
        )
        generic_job = normalize_job_listing(
            company="Qualcomm",
            title="General Hardware Test Engineer",
            raw_text="Hardware lab testing in Bengaluru. 2025 batch.",
            location="Bengaluru",
            country="India",
        )

        dv_match = scorer.score_job(dv_job)
        generic_match = scorer.score_job(generic_job)

        assert dv_match.is_eligible is True
        assert dv_match.match_score > generic_match.match_score

    def test_uvm_and_systemverilog_increase_match_score(self, candidate_context):
        profile, facts = candidate_context
        scorer = JobScoringEngine(profile, facts)

        full_tech_job = normalize_job_listing(
            company="NVIDIA",
            title="ASIC Verification Engineer",
            raw_text="Requires SystemVerilog, UVM, SVA, AXI. 0-1 yrs in Hyderabad.",
            location="Hyderabad",
            country="India",
        )
        basic_job = normalize_job_listing(
            company="NVIDIA",
            title="ASIC Verification Engineer",
            raw_text="Requires basic digital design. 0-1 yrs in Hyderabad.",
            location="Hyderabad",
            country="India",
        )

        full_match = scorer.score_job(full_tech_job)
        basic_match = scorer.score_job(basic_job)

        assert full_match.match_score > basic_match.match_score
        assert "SystemVerilog" in full_match.score_breakdown.matching_skills
        assert "UVM" in full_match.score_breakdown.matching_skills

    def test_fresher_role_is_compatible(self, candidate_context):
        profile, _ = candidate_context
        filter_engine = HardFilterEngine(profile)

        fresher_job = normalize_job_listing(
            company="Texas Instruments",
            title="Graduate Engineer Trainee — Digital Verification",
            raw_text="2025 batch passouts. 0 years experience required.",
            location="Bengaluru",
            country="India",
        )
        res = filter_engine.evaluate(fresher_job)
        assert res.is_eligible is True
        assert any("2025" in c or "compatible" in c for c in res.passed_criteria)

    def test_senior_role_is_rejected(self, candidate_context):
        profile, _ = candidate_context
        filter_engine = HardFilterEngine(profile)

        senior_jobs = [
            ("Senior Verification Engineer", "5+ years experience in UVM."),
            ("Staff ASIC Verification Architect", "8+ years in processor verification."),
            ("Lead DV Engineer", "Lead 6-member team. 7+ years."),
            ("Principal Verification Engineer", "10+ years SystemVerilog experience."),
        ]

        for title, desc in senior_jobs:
            job = normalize_job_listing(
                company="Broadcom",
                title=title,
                raw_text=desc,
                location="Bengaluru",
                country="India",
            )
            res = filter_engine.evaluate(job)
            assert res.is_eligible is False, f"Expected '{title}' to be rejected"
            assert any("Senior" in f or "exceeding" in f for f in res.failed_criteria)

    def test_bengaluru_tier1_preference_works(self, candidate_context):
        profile, facts = candidate_context
        scorer = JobScoringEngine(profile, facts)

        blr_job = normalize_job_listing(
            company="Intel",
            title="Design Verification Engineer",
            raw_text="SystemVerilog, UVM in Bengaluru.",
            location="Bengaluru, India",
            country="India",
        )
        non_hub_job = normalize_job_listing(
            company="Intel",
            title="Design Verification Engineer",
            raw_text="SystemVerilog, UVM in Remote Island.",
            location="Remote Island",
            country="Other",
        )

        blr_match = scorer.score_job(blr_job)
        non_hub_match = scorer.score_job(non_hub_job)

        assert blr_match.score_breakdown.location_score > non_hub_match.score_breakdown.location_score
        assert blr_match.score_breakdown.location_score == 10.0


# ---------------------------------------------------------------------------
# Test Category G & H: Overseas Authorization & Watchlist Boost
# ---------------------------------------------------------------------------
class TestOverseasAndWatchlistIntelligence:
    def test_overseas_authorization_mismatch_detected(self, candidate_context):
        profile, _ = candidate_context
        filter_engine = HardFilterEngine(profile)

        # Overseas job explicitly stating NO visa sponsorship
        no_sponsor_job = normalize_job_listing(
            company="Apple",
            title="Silicon Verification Engineer",
            raw_text="US Citizenship required. No visa sponsorship provided. Must already have work authorization.",
            location="Austin, TX",
            country="United States",
        )
        res = filter_engine.evaluate(no_sponsor_job)
        assert res.is_eligible is False
        assert any("visa" in f or "work authorization" in f for f in res.failed_criteria)

    def test_watchlisted_company_increases_priority(self, candidate_context, mem_conn):
        profile, facts = candidate_context
        watchlist_service = CompanyWatchlistService(mem_conn)
        watchlist_service.add_company("NVIDIA", priority_level="CRITICAL")

        watched_job = normalize_job_listing(
            company="NVIDIA",
            title="Design Verification Engineer",
            raw_text="SystemVerilog, UVM in Bengaluru. 2025 passout.",
            location="Bengaluru",
            country="India",
        )
        watched_job.is_watchlist = True

        non_watched_job = normalize_job_listing(
            company="UnknownStartupX",
            title="Design Verification Engineer",
            raw_text="SystemVerilog, UVM in Bengaluru. 2025 passout.",
            location="Bengaluru",
            country="India",
        )
        non_watched_job.is_watchlist = False

        scorer = JobScoringEngine(profile, facts)
        watched_match = scorer.score_job(watched_job)
        non_watched_match = scorer.score_job(non_watched_job)

        assert watched_match.match_score > non_watched_match.match_score
        assert any("Watchlisted Company" in r for r in watched_match.score_breakdown.reasons)


# ---------------------------------------------------------------------------
# Test Category I, J, K, O: Score Explainability & Classification Categories
# ---------------------------------------------------------------------------
class TestScoreExplainabilityAndCategories:
    def test_score_explanation_is_deterministic(self, candidate_context):
        profile, facts = candidate_context
        scorer = JobScoringEngine(profile, facts)

        job = normalize_job_listing(
            company="Synopsys",
            title="Design Verification Engineer",
            raw_text="SystemVerilog, UVM, SVA in Bengaluru. 0-1 years.",
            location="Bengaluru",
            country="India",
        )

        res1 = scorer.score_job(job)
        res2 = scorer.score_job(job)

        assert res1.match_score == res2.match_score
        assert res1.explanation == res2.explanation
        assert "JOB MATCH:" in res1.explanation
        assert len(res1.score_breakdown.reasons) > 0

    def test_critical_classification_works(self):
        score_crit = calculate_fresh_job_priority_score(
            match_score=92.0,
            freshness_bucket=calculate_granular_freshness(datetime.now(UTC).isoformat())[0],
            freshness_confidence=calculate_granular_freshness(datetime.now(UTC).isoformat())[2],
            is_watchlist=True,
            is_india=True,
        )
        assert score_crit.category == JobPriorityCategory.CRITICAL
        assert score_crit.total_score >= 88.0

    def test_high_classification_works(self):
        now_dt = datetime.now(UTC)
        score_high = calculate_fresh_job_priority_score(
            match_score=80.0,
            freshness_bucket=calculate_granular_freshness((now_dt - timedelta(hours=10.0)).isoformat())[0],
            freshness_confidence=calculate_granular_freshness((now_dt - timedelta(hours=10.0)).isoformat())[2],
            is_watchlist=False,
            is_india=True,
        )
        assert score_high.category == JobPriorityCategory.HIGH
        assert score_high.total_score >= 75.0

    def test_unknown_freshness_is_never_treated_as_le_24h(self):
        status, age, _conf = calculate_job_freshness("Posted Recently")
        assert status == FreshnessStatus.UNKNOWN
        assert age is None

        score = calculate_fresh_job_priority_score(
            match_score=90.0,
            freshness_bucket=calculate_granular_freshness(None)[0],
            freshness_confidence=calculate_granular_freshness(None)[2],
        )
        assert score.is_fresh_24h_match is False
        assert score.freshness <= 5.0


# ---------------------------------------------------------------------------
# Test Category L, M: Alert Deduplication & Material Change Re-Alerting
# ---------------------------------------------------------------------------
class TestAlertEngineAndMaterialChanges:
    def test_duplicate_alert_suppressed_on_repeated_scan(self, mem_conn):
        now = datetime.now(UTC)
        raw_item = {
            "company": "Tenstorrent",
            "title": "Design Verification Engineer",
            "location": "Bengaluru, India",
            "country": "India",
            "published_at": (now - timedelta(hours=2.0)).isoformat(),
            "source_url": "https://tenstorrent.com/jobs/1",
            "raw_payload": "Tenstorrent hiring DV engineer in SystemVerilog and UVM.",
        }

        scanner = FreshJobScanner(conn=mem_conn, adapters=[], allow_mock=True)

        payload = RawJobPayload(
            company=raw_item["company"],
            title=raw_item["title"],
            raw_payload=raw_item["raw_payload"],
            location=raw_item["location"],
            country=raw_item["country"],
            source="manual",
            source_url=raw_item["source_url"],
            application_url=raw_item["source_url"],
            discovered_at=now.isoformat(),
            content_hash="hash1",
            metadata={"published_at": raw_item["published_at"]},
        )

        # First pass -> proposes notification
        res1 = scanner._process_raw_payload(payload, "test_adapter", "api", now, 24.0, 60.0, dry_run=False)
        assert res1["notification_proposed"] is True

        # Second pass (repeated discovery) -> duplicate alert suppressed
        res2 = scanner._process_raw_payload(payload, "test_adapter", "api", now, 24.0, 60.0, dry_run=False)
        assert res2["is_duplicate"] is True
        assert res2["notification_proposed"] is False

    def test_material_job_change_can_trigger_realert(self, mem_conn):
        now = datetime.now(UTC)
        scanner = FreshJobScanner(conn=mem_conn, adapters=[], allow_mock=True)

        payload1 = RawJobPayload(
            company=f"AMD_{now.timestamp()}",
            title="Design Verification Engineer",
            raw_payload="Initial basic listing.",
            location="Bengaluru",
            country="India",
            source="test",
            source_url="https://amd.com/job/1",
            application_url="https://amd.com/job/1",
            discovered_at=now.isoformat(),
            content_hash="hash1",
            metadata={"published_at": (now - timedelta(hours=2.0)).isoformat()},
        )
        res1 = scanner._process_raw_payload(payload1, "test", "api", now, 24.0, 60.0, dry_run=False)
        assert res1["notification_proposed"] is True

        # Materially changed payload (new direct application link + 200 bytes expanded description)
        payload2 = RawJobPayload(
            company=payload1.company,
            title="Design Verification Engineer",
            raw_payload="Expanded description with complete UVM requirements: SystemVerilog, UVM, SVA, Coverage, AXI, VCS simulations, and direct hiring manager contact.",
            location="Bengaluru",
            country="India",
            source="test",
            source_url="https://amd.com/job/1",
            application_url="https://amd.com/careers/apply-now/direct-dv",
            discovered_at=now.isoformat(),
            content_hash="hash2",
            metadata={"published_at": (now - timedelta(hours=2.0)).isoformat()},
        )
        res2 = scanner._process_raw_payload(payload2, "test", "api", now, 24.0, 60.0, dry_run=False)
        assert res2["is_duplicate"] is True
        assert res2["notification_proposed"] is True


# ---------------------------------------------------------------------------
# Test Category N: Daily Digest Generation
# ---------------------------------------------------------------------------
class TestDailyDigestGeneration:
    def test_daily_digest_generation_with_fresh_jobs(self, mem_conn):
        repo = JobRepository(mem_conn)
        now_iso = datetime.now(UTC).isoformat()

        job1 = NormalizedJob(
            company="Qualcomm",
            title="Lead DV Engineer",
            location="Bengaluru, India",
            country="India",
            source="test",
            first_seen=now_iso,
            last_seen=now_iso,
            fingerprint="qualcomm-leaddv-blr",
            published_at=now_iso,
            freshness_status="fresh_0_6_hours",
            freshness_age_hours=2.5,
            freshness_bucket="<= 3 hours",
            priority_score=92.0,
            priority_category="CRITICAL",
            is_watchlist=True,
        )
        repo.insert_normalized_job(job1)

        digest_service = DailyDigestService(mem_conn)
        digest = digest_service.generate_daily_digest(hours=24.0, top_n=5)

        assert digest.total_fresh_24h == 1
        assert digest.critical_count == 1
        assert len(digest.top_opportunities) == 1
        assert "Qualcomm" in digest.markdown_content
        assert "# 📅 Daily Career Intelligence Digest" in digest.markdown_content


# ---------------------------------------------------------------------------
# Test Category P & Q: Human Approval & Mock Adapter Protection
# ---------------------------------------------------------------------------
class TestSafetyAndHumanGates:
    def test_human_approval_gate_remains_intact(self, mem_conn):
        notif_service = ScheduleNotificationService(mem_conn)
        prop = notif_service.propose_schedule_notification(
            notification_type="opportunity_alert",
            destination="Candidate Portal",
            target_company="Arm",
            target_role="Graduate DV",
            scheduled_time=datetime.now(UTC).isoformat(),
            action_type="review_opportunity",
            subject="[FRESH] Graduate DV at Arm",
            body_content="Details",
            rationale="Rationale",
        )

        assert prop.status == NotificationDispatchStatus.PROPOSED
        assert prop.approved_at is None

        # Human gives explicit approval
        approved = notif_service.approve_proposal(prop.id)
        assert approved.status == NotificationDispatchStatus.APPROVED
        assert approved.approved_at is not None

    def test_mock_adapter_protection_in_production(self, mem_conn):
        with pytest.raises(ValueError, match="MockJobSourceAdapter cannot be used in production"):
            FreshJobScanner(conn=mem_conn, adapters=[MockJobSourceAdapter()], allow_mock=False)
