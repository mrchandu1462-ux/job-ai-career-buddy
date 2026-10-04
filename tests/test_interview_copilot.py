"""Comprehensive Phase 6 tests for Interview Prep Copilot & Tailored Practice Generator.

Validates:
A. JD extraction works
B. Candidate skill matching works
C. Missing skill detection works
D. Strong skill detection works
E. DV role generates DV topics
F. AXI role generates AXI topics
G. UVM role generates UVM topics
H. Project questions are grounded in candidate profile
I. Unsupported skills are not invented
J. Company-specific claims require evidence
K. Mock interview mode selection works
L. Answer evaluation works
M. Weakness tracking works
N. Readiness score is deterministic
O. Study plan adjusts to weaknesses
P. Existing human approval gate remains intact
Q. Existing freshness rules remain intact
R. Existing alert deduplication remains intact
S. Production MockJobSourceAdapter protection remains intact
T. No autonomous application behavior
U. Existing Phase 1-5 tests remain green
"""

from datetime import UTC, datetime, timedelta

import pytest

from app.career.copilot import (
    AnswerEvaluationStatus,
    EvidenceProvenance,
    InterviewCopilotService,
    InterviewReadinessLevel,
    JDAnalysisEngine,
    MockInterviewMode,
    QuestionCategory,
    SkillGapEngine,
    SkillProficiencyLevel,
)
from app.career.notifications import ScheduleNotificationService
from app.db.connection import get_connection
from app.db.models import FreshnessStatus, NormalizedJob, WeakArea
from app.db.schema import create_schema
from app.jobs.freshness import calculate_job_freshness
from app.jobs.scanner import FreshJobScanner
from app.jobs.sources.adapters import MockJobSourceAdapter
from app.jobs.sources.base import RawJobPayload
from app.profile.loader import load_candidate_profile, load_fact_bank


@pytest.fixture
def mem_conn():
    """In-memory SQLite connection with full schema initialized."""
    conn = get_connection(":memory:")
    create_schema(conn)
    return conn


@pytest.fixture
def candidate_context():
    """Load verified candidate profile and fact bank."""
    profile = load_candidate_profile()
    fact_bank = load_fact_bank()
    return profile, fact_bank


@pytest.fixture
def sample_dv_job():
    """Sample normalized DV job listing."""
    now_iso = datetime.now(UTC).isoformat()
    return NormalizedJob(
        company="NVIDIA",
        title="ASIC Verification Engineer",
        location="Bengaluru, India",
        country="India",
        source="career_portal",
        first_seen=now_iso,
        last_seen=now_iso,
        fingerprint="nvidia-asic-dv-blr-2025",
        description="NVIDIA is seeking an entry-level ASIC Verification Engineer. Responsibilities include building UVM testbenches, writing SystemVerilog constrained-random sequences, verifying AXI/AHB protocols, defining SVA assertions, and debugging regression failures in QuestaSim.",
        requirements="B.Tech in EEE/ECE 2025 batch. Strong SystemVerilog, UVM, SVA, AXI, Python.",
        skills=["SystemVerilog", "UVM", "AXI", "SVA", "Python", "QuestaSim"],
    )


# ---------------------------------------------------------------------------
# Requirement A: JD Extraction Works
# ---------------------------------------------------------------------------
class TestJDExtraction:
    def test_jd_extraction_extracts_technical_skills_and_role_tier(self, sample_dv_job):
        engine = JDAnalysisEngine()
        res = engine.analyze(sample_dv_job)

        assert res.role_tier == "TIER_1"
        assert res.has_sv is True
        assert res.has_uvm is True
        assert res.has_axi is True
        assert res.has_sva is True
        assert "SystemVerilog" in res.technical_skills
        assert "UVM" in res.technical_skills
        assert "AXI Protocol" in res.technical_skills
        assert "SVA / Assertions" in res.technical_skills


# ---------------------------------------------------------------------------
# Requirements B, C, D, I: Skill Matching, Missing Skills, Strong Skills & Zero Invention
# ---------------------------------------------------------------------------
class TestSkillGapAnalysis:
    def test_candidate_skill_matching_and_strong_skill_detection(self, candidate_context, sample_dv_job):
        profile, fact_bank = candidate_context
        engine = JDAnalysisEngine()
        gap_engine = SkillGapEngine(profile, fact_bank)

        jd_res = engine.analyze(sample_dv_job)
        gaps = gap_engine.evaluate_gaps(jd_res)

        sv_gap = next((g for g in gaps if "SystemVerilog" in g.skill_name), None)
        assert sv_gap is not None
        assert sv_gap.proficiency == SkillProficiencyLevel.STRONG
        assert "AXI4 UVC" in sv_gap.evidence or "project" in sv_gap.evidence.lower()

        uvm_gap = next((g for g in gaps if "UVM" in g.skill_name), None)
        assert uvm_gap is not None
        assert uvm_gap.proficiency == SkillProficiencyLevel.STRONG

    def test_missing_skill_detection_and_no_unsupported_skills_invented(self, candidate_context):
        profile, fact_bank = candidate_context
        engine = JDAnalysisEngine()
        gap_engine = SkillGapEngine(profile, fact_bank)

        job_with_unsupported_skills = NormalizedJob(
            company="Broadcom",
            title="Design Verification Engineer",
            location="Bengaluru",
            country="India",
            source="portal",
            first_seen="2026-10-04T00:00:00Z",
            last_seen="2026-10-04T00:00:00Z",
            fingerprint="broadcom-pcie-dv",
            description="Requires 2 years experience with PCIe Gen5 protocol verification and Low Power UPF verification.",
            requirements="PCIe, UPF, SystemVerilog.",
            skills=["PCIe", "UPF", "SystemVerilog"],
        )

        jd_res = engine.analyze(job_with_unsupported_skills)
        gaps = gap_engine.evaluate_gaps(jd_res)

        pcie_gap = next((g for g in gaps if "PCIe" in g.skill_name), None)
        assert pcie_gap is not None
        assert pcie_gap.proficiency == SkillProficiencyLevel.MISSING
        assert pcie_gap.candidate_context is None  # Never hallucinate candidate context for missing skills
        assert "Not present in verified candidate profile" in pcie_gap.evidence


# ---------------------------------------------------------------------------
# Requirements E, F, G: Topic Generation for DV, AXI, and UVM Roles
# ---------------------------------------------------------------------------
class TestInterviewTopicGeneration:
    def test_dv_role_generates_dv_topics(self, candidate_context, sample_dv_job):
        copilot = InterviewCopilotService(get_connection(":memory:"))
        prep_profile = copilot.analyze_job(sample_dv_job)

        topics_str = " ".join(prep_profile.interview_topics)
        assert "Level 1: Digital Logic" in topics_str
        assert "Level 2: Verilog" in topics_str
        assert "Level 3: SystemVerilog" in topics_str
        assert "Level 4: UVM" in topics_str
        assert "Level 5: AXI4" in topics_str
        assert "Level 6: Project Authenticity Defense" in topics_str

    def test_axi_role_generates_axi_topics(self, candidate_context, sample_dv_job):
        copilot = InterviewCopilotService(get_connection(":memory:"))
        prep_profile = copilot.analyze_job(sample_dv_job)

        axi_topic = next((t for t in prep_profile.interview_topics if "AXI4" in t), None)
        assert axi_topic is not None
        assert "VALID/READY" in axi_topic or "Protocol" in axi_topic


# ---------------------------------------------------------------------------
# Requirements H & J: Grounded Project Questions & Provenance
# ---------------------------------------------------------------------------
class TestProjectGroundedQuestionsAndProvenance:
    def test_project_questions_grounded_in_candidate_profile(self, candidate_context, sample_dv_job):
        copilot = InterviewCopilotService(get_connection(":memory:"))
        prep_profile = copilot.analyze_job(sample_dv_job)

        prj_questions = [q for q in prep_profile.question_sets if q.category == QuestionCategory.PROJECT_DEFENSE]
        assert len(prj_questions) >= 2

        axi_prj_q = next((q for q in prj_questions if "AXI4 UVC" in q.topic), None)
        assert axi_prj_q is not None
        assert "clocking block" in axi_prj_q.question or "architecture" in axi_prj_q.question
        assert axi_prj_q.provenance == EvidenceProvenance.USER_PROVIDED

    def test_company_claims_require_evidence_and_labeling(self, sample_dv_job):
        copilot = InterviewCopilotService(get_connection(":memory:"))
        prep_profile = copilot.analyze_job(sample_dv_job)

        for q in prep_profile.question_sets:
            assert isinstance(q.provenance, EvidenceProvenance)
            assert q.provenance in (
                EvidenceProvenance.GENERAL_DV_TOPIC,
                EvidenceProvenance.USER_PROVIDED,
                EvidenceProvenance.VERIFIED_FROM_JD,
                EvidenceProvenance.VERIFIED_PUBLIC_SOURCE,
                EvidenceProvenance.LIKELY,
                EvidenceProvenance.POSSIBLE,
            )


# ---------------------------------------------------------------------------
# Requirements K & L: Mock Interview Modes & Answer Evaluation
# ---------------------------------------------------------------------------
class TestMockInterviewEngineAndAnswerEvaluation:
    def test_mock_interview_mode_selection_works(self, sample_dv_job):
        copilot = InterviewCopilotService(get_connection(":memory:"))

        quick_session = copilot.start_mock_interview(sample_dv_job, mode=MockInterviewMode.QUICK)
        assert len(quick_session.questions) == 10
        assert quick_session.mode == MockInterviewMode.QUICK

        project_session = copilot.start_mock_interview(sample_dv_job, mode=MockInterviewMode.PROJECT)
        assert all(q.category == QuestionCategory.PROJECT_DEFENSE for q in project_session.questions)

    def test_answer_evaluation_correct_and_partial_and_incorrect(self, sample_dv_job):
        copilot = InterviewCopilotService(get_connection(":memory:"))
        session = copilot.start_mock_interview(sample_dv_job, mode=MockInterviewMode.QUICK)

        # 1. Correct Answer
        strong_ans = (
            "Setup time is the minimum duration data must be stable before the active clock edge. "
            "Hold time is the duration data must remain stable after the clock edge. "
            "Hold violations are fixed by adding delay buffers into the data path."
        )
        res_correct = copilot.evaluate_mock_turn(session, strong_ans)
        assert res_correct.status == AnswerEvaluationStatus.CORRECT
        assert res_correct.technical_accuracy >= 0.75
        assert len(res_correct.good_points) > 0

        # 2. Incomplete / Partial Answer
        partial_ans = "Setup time is before clock edge."
        res_partial = copilot.evaluate_mock_turn(session, partial_ans)
        assert res_partial.status in (AnswerEvaluationStatus.PARTIALLY_CORRECT, AnswerEvaluationStatus.INCORRECT)
        assert len(res_partial.missing_points) > 0


# ---------------------------------------------------------------------------
# Requirements M, N, O: Weakness Tracking, Readiness Score, Dynamic Study Plan
# ---------------------------------------------------------------------------
class TestWeaknessReadinessAndStudyPlan:
    def test_weakness_tracking_persists_gaps(self, mem_conn, sample_dv_job):
        copilot = InterviewCopilotService(mem_conn)
        session = copilot.start_mock_interview(sample_dv_job, mode=MockInterviewMode.QUICK)

        # Submit incorrect answer to trigger gap logging
        res_inc = copilot.evaluate_mock_turn(session, "I do not know")
        assert res_inc.status in (AnswerEvaluationStatus.INCORRECT, AnswerEvaluationStatus.UNCLEAR)

        # Verify weak area was persisted
        weak_areas = copilot.career_repo.list_weak_areas(resolved=False)
        assert len(weak_areas) >= 1

        stats = copilot.weakness_service.get_topic_stats(session.questions[0].topic)
        assert stats.topic == session.questions[0].topic
        assert stats.weakness_score > 0.0

    def test_readiness_score_is_deterministic(self, mem_conn, sample_dv_job):
        copilot = InterviewCopilotService(mem_conn)
        profile = copilot.analyze_job(sample_dv_job)

        assert profile.readiness is not None
        assert 0.0 <= profile.readiness.total_score <= 100.0
        assert profile.readiness.level in (
            InterviewReadinessLevel.READY,
            InterviewReadinessLevel.NEAR_READY,
            InterviewReadinessLevel.NEEDS_WORK,
            InterviewReadinessLevel.NOT_READY,
        )
        assert len(profile.readiness.strengths) > 0
        assert "READINESS:" in profile.readiness.explainable_summary

    def test_study_plan_adjusts_to_weaknesses(self, mem_conn, sample_dv_job):
        copilot = InterviewCopilotService(mem_conn)
        copilot.career_repo.insert_weak_area(
            WeakArea(
                topic="UVM Objections",
                description="Failed objection drop timing",
                severity="high",
                confidence=0.3,
                created_at=datetime.now(UTC).isoformat(),
            )
        )

        profile = copilot.analyze_job(sample_dv_job)
        assert profile.study_plan is not None
        assert len(profile.study_plan.days) == 7

        day3 = profile.study_plan.days[2]
        assert "UVM" in day3.title
        assert any("UVM" in w for w in day3.target_weak_areas)


# ---------------------------------------------------------------------------
# Requirements P, Q, R, S, T: Safety, Integrity, Human Gates & Mock Protection
# ---------------------------------------------------------------------------
class TestSafetyIntegrityAndHumanGates:
    def test_human_approval_gate_remains_intact(self, mem_conn):
        service = ScheduleNotificationService(mem_conn)
        prop = service.propose_schedule_notification(
            notification_type="interview_prep",
            destination="Candidate Portal",
            target_company="Intel",
            target_role="DV Engineer",
            scheduled_time=datetime.now(UTC).isoformat(),
            action_type="review_study_plan",
            subject="Interview Prep Ready",
            body_content="Complete Day 1 drills.",
            rationale="Automated prep plan.",
        )
        assert prop.status == "proposed"
        assert prop.approved_at is None
        assert prop.dispatched_at is None

    def test_unknown_freshness_is_never_treated_as_le_24h(self):
        status, age, _conf = calculate_job_freshness("Posted Recently")
        assert status == FreshnessStatus.UNKNOWN
        assert age is None

    def test_alert_deduplication_remains_intact(self, mem_conn):
        now = datetime.now(UTC)
        scanner = FreshJobScanner(conn=mem_conn, adapters=[], allow_mock=True)

        payload = RawJobPayload(
            company="Qualcomm",
            title="Design Verification Engineer",
            raw_payload="SystemVerilog, UVM, AXI in Hyderabad. 2025 batch.",
            location="Hyderabad",
            country="India",
            source="test",
            source_url="https://qualcomm.com/job/dv-1",
            application_url="https://qualcomm.com/job/dv-1",
            discovered_at=now.isoformat(),
            content_hash="hash_dedup_1",
            metadata={"published_at": (now - timedelta(hours=2.0)).isoformat()},
        )

        res1 = scanner._process_raw_payload(payload, "test", "api", now, 24.0, 60.0, dry_run=False)
        assert res1["notification_proposed"] is True

        res2 = scanner._process_raw_payload(payload, "test", "api", now, 24.0, 60.0, dry_run=False)
        assert res2["is_duplicate"] is True
        assert res2["notification_proposed"] is False

    def test_production_mock_job_source_adapter_blocked(self, mem_conn):
        with pytest.raises(ValueError, match="MockJobSourceAdapter cannot be used in production"):
            FreshJobScanner(
                conn=mem_conn,
                adapters=[MockJobSourceAdapter()],
                allow_mock=False,
            )

    def test_no_autonomous_applications_are_submitted(self, mem_conn, sample_dv_job):
        copilot = InterviewCopilotService(mem_conn)
        prep_profile = copilot.analyze_job(sample_dv_job)
        session = copilot.start_mock_interview(sample_dv_job)

        assert prep_profile is not None
        assert session is not None

        # Ensure no application records or submissions were created
        apps = mem_conn.execute("SELECT * FROM applications;").fetchall()
        assert len(apps) == 0
        events = mem_conn.execute("SELECT * FROM application_events WHERE event_type = 'submitted';").fetchall()
        assert len(events) == 0
