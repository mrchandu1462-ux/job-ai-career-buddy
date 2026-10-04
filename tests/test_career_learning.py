"""Tests for LearningModeService structured topic study, practice drill evaluations, and confidence adaptation."""

import pytest

from app.career.ingestion import (
    CareerIngestionService,
    CareerIngestPayload,
    KnowledgeIngestItem,
    QuestionIngestItem,
    WeakAreaIngestItem,
)
from app.career.learning import LearningModeService
from app.career.repository import CareerRepository
from app.db.connection import get_db


@pytest.fixture
def db_conn():
    with get_db(":memory:") as conn:
        yield conn


@pytest.fixture
def career_repo(db_conn):
    return CareerRepository(db_conn)


@pytest.fixture
def learning_service(career_repo):
    return LearningModeService(career_repo)


@pytest.fixture
def seeded_learning_kb(career_repo):
    ingest = CareerIngestionService(career_repo)
    payload = CareerIngestPayload(
        source="Async FIFO Study Module",
        source_type="study_session",
        knowledge_items=[
            KnowledgeIngestItem(
                topic="Async FIFO",
                concept="Dual Clock Pointer Synchronization",
                explanation="Gray code ensures only one bit flips per cycle, preventing multi-bit sampling glitches across clock domains.",
                source="Clifford Cummings CDC Whitepaper",
                verified=True,
            )
        ],
        questions=[
            QuestionIngestItem(
                company="Broadcom",
                role="Design Verification Engineer",
                question="Why is Gray code used for FIFO pointers?",
                topic="Async FIFO",
                expected_answer="Single-bit Hamming distance avoids metastability hazards in asynchronous clock domains.",
                was_correct=False,
                source="Broadcom Technical",
                verified=True,
            )
        ],
        weak_areas=[
            WeakAreaIngestItem(
                topic="Async FIFO",
                description="CDC pointer synchronization edge cases.",
                severity="high",
                confidence=0.4,
            )
        ],
    )
    ingest.ingest_payload(payload)


def test_get_topic_curriculum(learning_service, seeded_learning_kb):
    """Test generating a structured curriculum with subtopics and previous mistakes."""
    curriculum = learning_service.get_topic_curriculum("Async FIFO")

    assert curriculum.topic == "Async FIFO"
    assert len(curriculum.key_subtopics) >= 5
    assert any("Gray code" in s for s in curriculum.key_subtopics)
    assert len(curriculum.verified_knowledge_concepts) >= 1
    assert len(curriculum.previous_mistakes) >= 1
    assert len(curriculum.active_weak_areas) >= 1
    assert len(curriculum.practice_questions) >= 1


def test_evaluate_practice_answer_correct_and_multi_observation(learning_service, career_repo, seeded_learning_kb):
    """Test practice answer evaluation and confidence adaptation over multiple successful attempts."""
    questions = career_repo.get_questions_by_topic("Async FIFO")
    q_id = questions[0].id

    # 1st correct answer -> increases confidence from 0.40 to 0.55, but not yet resolved
    res1 = learning_service.evaluate_practice_answer(
        question_id=q_id,
        user_answer="Gray code has a single-bit change between adjacent values.",
        was_correct=True,
    )
    assert res1.was_correct is True
    assert res1.updated_confidence == 0.55
    assert res1.resolved is False

    # 2nd review / correct answer
    res2 = learning_service.evaluate_practice_answer(
        question_id=q_id,
        user_answer="Detailed pointer sync answer.",
        was_correct=True,
    )
    assert res2.updated_confidence == 0.70

    # 3rd review / correct answer -> confidence reaches >= 0.85 and resolves
    learning_service.evaluate_practice_answer(
        question_id=q_id,
        user_answer="Flawless CDC explanation.",
        was_correct=True,
    )
    res4 = learning_service.evaluate_practice_answer(
        question_id=q_id,
        user_answer="Mastered explanation.",
        was_correct=True,
    )
    assert res4.updated_confidence >= 0.85
    assert res4.resolved is True


def test_evaluate_practice_answer_incorrect_penalty(learning_service, career_repo, seeded_learning_kb):
    """Test penalty on incorrect practice answer."""
    questions = career_repo.get_questions_by_topic("Async FIFO")
    q_id = questions[0].id

    res = learning_service.evaluate_practice_answer(
        question_id=q_id,
        user_answer="Incorrect binary arithmetic guess.",
        was_correct=False,
    )
    assert res.was_correct is False
    assert res.updated_confidence <= 0.25
    assert res.resolved is False


def test_log_learning_session(learning_service, career_repo):
    """Test recording a completed study session log in database."""
    session_id = learning_service.log_learning_session(
        job_id=None,
        topics=["Async FIFO", "UVM TLM"],
        questions_attempted=5,
        summary="Covered Gray code conversions and analysis FIFO exports.",
        notes="Reviewed Cummings CDC paper.",
    )
    assert session_id is not None
    sessions = career_repo.list_prep_sessions()
    assert len(sessions) == 1
    assert "Async FIFO" in sessions[0].topics
