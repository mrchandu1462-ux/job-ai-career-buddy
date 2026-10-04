"""Tests for Career & Interview Knowledge Base."""

import pytest

from app.career.repository import CareerRepository
from app.db.connection import get_db
from app.db.models import (
    InterviewQuestion,
    InterviewSession,
    JobStatus,
    KnowledgeItem,
    NormalizedJob,
    PreparationSession,
    WeakArea,
)


@pytest.fixture
def career_repo():
    """Provides a fresh CareerRepository backed by an in-memory database."""
    with get_db(":memory:") as conn:
        yield CareerRepository(conn)


def test_insert_and_list_interview_sessions(career_repo):
    """Test logging previous interview sessions."""
    session = InterviewSession(
        company="Intel India",
        role="ASIC Verification Engineer",
        date="2026-09-15",
        round="Technical 1 - SystemVerilog OOP",
        outcome="passed",
        notes="Strong focus on virtual interfaces and polymorphism.",
        created_at="2026-09-15T18:00:00Z",
    )
    s_id = career_repo.insert_interview_session(session)
    assert s_id > 0

    fetched = career_repo.get_interview_session(s_id)
    assert fetched is not None
    assert fetched.company == "Intel India"
    assert fetched.round == "Technical 1 - SystemVerilog OOP"

    intel_sessions = career_repo.list_interview_sessions(company="Intel")
    assert len(intel_sessions) == 1
    assert intel_sessions[0].id == s_id


def test_insert_and_query_interview_questions(career_repo):
    """Test querying questions by company, role, topic, and status."""
    q1 = InterviewQuestion(
        company="Qualcomm",
        role="Design Verification Engineer",
        question="Explain the difference between pure virtual methods and virtual methods in SystemVerilog.",
        category="technical",
        topic="SystemVerilog OOP",
        user_answer="Pure virtual methods have no implementation in base class.",
        expected_answer="Pure virtual functions provide interface prototype without implementation, making the class abstract.",
        was_correct=True,
        source="Qualcomm Campus Technical Round 1",
        verified=True,
        times_asked=2,
        created_at="2026-09-10T14:00:00Z",
    )
    q2 = InterviewQuestion(
        company="NVIDIA",
        role="RTL Design Engineer",
        question="How do you handle multi-bit asynchronous clock domain crossing without data corruption?",
        category="technical",
        topic="Clock Domain Crossing",
        user_answer="Use dual flip-flop synchronizer on all bits.",
        expected_answer="Use asynchronous FIFO or Gray-coded pointer synchronization.",
        feedback="Incorrect: multi-bit buses suffer from bus skew; standard 2-FF synchronizers are only for single-bit signals.",
        was_correct=False,
        source="NVIDIA Technical Discussion",
        verified=False,
        times_asked=3,
        created_at="2026-09-12T16:00:00Z",
    )
    q3 = InterviewQuestion(
        company="Texas Instruments",
        role="Design Verification Engineer",
        question="Why is UVM build_phase executed top-down while connect_phase is bottom-up?",
        category="technical",
        topic="UVM Phases",
        was_correct=True,
        source="TI Mock Interview",
        verified=True,
        times_asked=1,
        created_at="2026-09-20T10:00:00Z",
    )

    q1_id = career_repo.insert_interview_question(q1)
    q2_id = career_repo.insert_interview_question(q2)
    career_repo.insert_interview_question(q3)

    # 1. Query all
    all_q = career_repo.get_all_questions()
    assert len(all_q) == 3

    # 2. Query by company
    nv_q = career_repo.get_questions_by_company("NVIDIA")
    assert len(nv_q) == 1
    assert nv_q[0].id == q2_id

    # 3. Query by role
    dv_q = career_repo.get_questions_by_role("Design Verification Engineer")
    assert len(dv_q) == 2

    # 4. Query by topic
    sv_q = career_repo.get_questions_by_topic("SystemVerilog OOP")
    assert len(sv_q) == 1
    assert sv_q[0].id == q1_id

    # 5. Query questions answered incorrectly
    incorrect = career_repo.get_incorrect_questions()
    assert len(incorrect) == 1
    assert incorrect[0].id == q2_id
    assert incorrect[0].was_correct is False

    # 6. Query repeated questions
    repeated = career_repo.get_repeated_questions(min_times=2)
    assert len(repeated) == 2
    assert repeated[0].times_asked >= 2


def test_weak_areas_tracking_and_review(career_repo):
    """Test logging and revising candidate weak areas."""
    wa = WeakArea(
        topic="Clock Domain Crossing",
        description="Candidate struggled with multi-bit CDC synchronization and Gray coding.",
        evidence_source="NVIDIA Technical Discussion Question #2",
        severity="high",
        confidence=0.3,
        created_at="2026-09-12T17:00:00Z",
    )
    wa_id = career_repo.insert_weak_area(wa)
    assert wa_id > 0

    active_weak = career_repo.list_weak_areas(resolved=False)
    assert len(active_weak) == 1
    assert active_weak[0].topic == "Clock Domain Crossing"
    assert active_weak[0].review_count == 0

    # Perform a study review and update confidence
    career_repo.update_weak_area_review(
        weak_area_id=wa_id, new_confidence=0.8, resolved=True
    )

    updated_wa = career_repo.get_weak_area(wa_id)
    assert updated_wa is not None
    assert updated_wa.review_count == 1
    assert updated_wa.confidence == 0.8
    assert updated_wa.resolved is True
    assert updated_wa.last_reviewed is not None

    # Verify filtering
    assert len(career_repo.list_weak_areas(resolved=False)) == 0
    assert len(career_repo.list_weak_areas(resolved=True)) == 1


def test_preparation_sessions_and_knowledge_items(career_repo):
    """Test logging preparation sessions and knowledge items."""
    # Preparation Session
    session = PreparationSession(
        date="2026-10-01",
        topics=["SystemVerilog OOP", "UVM Scoreboard", "Clock Domain Crossing"],
        questions_attempted=15,
        performance_summary="Solved 13/15 questions correctly. Revised Gray coding for CDC.",
        notes="Good progress on UVM TLM connections.",
        created_at="2026-10-01T20:00:00Z",
    )
    prep_id = career_repo.insert_prep_session(session)
    assert prep_id > 0

    prep_list = career_repo.list_prep_sessions()
    assert len(prep_list) == 1
    assert "SystemVerilog OOP" in prep_list[0].topics

    # Knowledge Item
    k_item = KnowledgeItem(
        topic="UVM Phases",
        concept="Phase Execution Order",
        explanation="build_phase executes top-down to instantiate children components before configuring them.",
        source="UVM 1.2 User Guide & Verified Notes",
        verified=True,
        related_question_ids=[],
        created_at="2026-10-01T21:00:00Z",
    )
    k_id = career_repo.insert_knowledge_item(k_item)
    assert k_id > 0

    items = career_repo.get_knowledge_items_by_topic("UVM Phases")
    assert len(items) == 1
    assert items[0].concept == "Phase Execution Order"
    assert items[0].verified is True


def test_matching_career_context_for_new_job(career_repo):
    """Test synthesizing historical questions, weak areas, and knowledge items for a target job."""
    # 1. Seed knowledge base
    career_repo.insert_interview_question(
        InterviewQuestion(
            company="Synopsys",
            role="Design Verification Engineer",
            question="How do you write a covergroup for an APB bus protocol in SystemVerilog?",
            topic="SystemVerilog Functional Coverage",
            source="Synopsys Historical Interview",
            verified=True,
            created_at="2026-09-01T10:00:00Z",
        )
    )
    career_repo.insert_weak_area(
        WeakArea(
            topic="SystemVerilog Functional Coverage",
            description="Need more practice with cross-coverage and illegal bins.",
            severity="medium",
            confidence=0.4,
            created_at="2026-09-02T10:00:00Z",
        )
    )
    career_repo.insert_knowledge_item(
        KnowledgeItem(
            topic="SystemVerilog Functional Coverage",
            concept="Cross Coverage Syntax",
            explanation="cross cp_addr, cp_data { ignore_bins ... }",
            source="SystemVerilog LRM",
            verified=True,
            created_at="2026-09-02T11:00:00Z",
        )
    )

    # 2. Target Job
    target_job = NormalizedJob(
        id=101,
        company="Synopsys",
        title="Design Verification Engineer",
        location="Bengaluru",
        country="India",
        skills=["SystemVerilog", "SystemVerilog Functional Coverage", "UVM"],
        source="manual",
        status=JobStatus.ACTIVE,
        first_seen="2026-10-04T10:00:00Z",
        last_seen="2026-10-04T10:00:00Z",
        fingerprint="synopsys-dv-101",
    )

    # 3. Match context
    context = career_repo.match_career_context_for_job(target_job)
    assert context["job_id"] == 101
    assert context["company"] == "Synopsys"
    assert len(context["relevant_questions"]) >= 1
    assert context["relevant_questions"][0].question.startswith("How do you write a covergroup")
    assert len(context["relevant_weak_areas"]) >= 1
    assert context["relevant_weak_areas"][0].topic == "SystemVerilog Functional Coverage"
    assert len(context["relevant_knowledge_items"]) >= 1
