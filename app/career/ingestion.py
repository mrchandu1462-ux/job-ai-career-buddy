import json
import re
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field

from app.career.repository import CareerRepository
from app.db.models import (
    InterviewQuestion,
    InterviewSession,
    KnowledgeItem,
    WeakArea,
)


def normalize_question_text(text: str) -> str:
    """Normalize question text by removing punctuation, lowercasing, and collapsing whitespace."""
    clean = text.lower()
    clean = re.sub(r"[^\w\s]", "", clean)
    clean = re.sub(r"\s+", " ", clean).strip()
    return clean


class QuestionIngestItem(BaseModel):
    """Input representation for importing an interview question."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    question: str = Field(..., min_length=3, description="Interview question text.")
    topic: str = Field(..., min_length=1, description="Subject/topic of the question.")
    category: str = Field(default="technical", description="technical, hr, or scenario.")
    company: str | None = Field(default=None, description="Company context if known.")
    role: str | None = Field(default=None, description="Role context if known.")
    user_answer: str | None = Field(default=None, description="Candidate's historical answer.")
    expected_answer: str | None = Field(default=None, description="Expected or model explanation.")
    feedback: str | None = Field(default=None, description="Interviewer comments or corrections.")
    was_correct: bool | None = Field(default=None, description="True if answered correctly, False if missed.")
    difficulty: str | None = Field(default=None, description="easy, medium, hard.")
    source: str = Field(..., min_length=1, description="Origin provenance (e.g. 'Mock session 1').")
    source_type: str = Field(default="manual", description="interview, mock, study_notes, discussion, ai_generated.")
    original_reference: str | None = Field(default=None, description="Reference marker in original notes.")
    verified: bool = Field(default=False, description="Explicit verification status.")
    times_asked: int = Field(default=1, ge=1, description="Historical frequency count.")


class WeakAreaIngestItem(BaseModel):
    """Input representation for importing an identified weak area."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    topic: str = Field(..., min_length=1, description="Skill or concept gap.")
    description: str = Field(..., min_length=1, description="Detailed explanation of the gap.")
    evidence_source: str | None = Field(default=None, description="Evidence source or interview citation.")
    source_type: str = Field(default="interview_feedback", description="feedback, self_assessment, mock_review.")
    severity: str = Field(default="medium", description="low, medium, high, critical.")
    confidence: float = Field(default=0.5, ge=0.0, le=1.0, description="Confidence level (0.0 to 1.0).")


class KnowledgeIngestItem(BaseModel):
    """Input representation for importing a verified reference explanation or study concept."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    topic: str = Field(..., min_length=1, description="Topic name.")
    concept: str = Field(..., min_length=1, description="Concept heading.")
    explanation: str = Field(..., min_length=1, description="Explanation text.")
    source: str = Field(..., min_length=1, description="Authoritative reference.")
    source_type: str = Field(default="textbook_reference", description="lrm, textbook, official_guide, notes.")
    verified: bool = Field(default=False, description="Verified status.")
    related_question_ids: list[int] = Field(default_factory=list, description="IDs of linked questions.")


class SessionIngestItem(BaseModel):
    """Input representation for importing a historical interview session."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    company: str = Field(..., min_length=1, description="Company interviewed with.")
    role: str = Field(..., min_length=1, description="Role interviewed for.")
    date: str = Field(..., description="ISO-8601 date of the interview.")
    round: str = Field(..., min_length=1, description="Round name.")
    outcome: str | None = Field(default=None, description="Outcome if known.")
    notes: str | None = Field(default=None, description="Candidate reflections.")
    created_at: str | None = Field(default=None, description="ISO-8601 creation timestamp.")


class CareerIngestPayload(BaseModel):
    """Container for batch importing career preparation material."""

    model_config = ConfigDict(extra="forbid")

    source: str = Field(..., min_length=1, description="Batch origin description.")
    source_type: str = Field(..., min_length=1, description="Primary batch type.")
    original_reference: str | None = Field(default=None, description="Batch reference marker.")
    session: SessionIngestItem | InterviewSession | None = Field(default=None, description="Optional parent interview session.")
    questions: list[QuestionIngestItem] = Field(default_factory=list)
    weak_areas: list[WeakAreaIngestItem] = Field(default_factory=list)
    knowledge_items: list[KnowledgeIngestItem] = Field(default_factory=list)


class IngestionResult(BaseModel):
    """Summary of ingested entities."""

    session_id: int | None = None
    questions_inserted: int = 0
    questions_deduplicated: int = 0
    weak_areas_inserted: int = 0
    knowledge_items_inserted: int = 0
    errors: list[str] = Field(default_factory=list)


class CareerIngestionService:
    """Service that validates provenance and deduplicates questions before database insertion."""

    def __init__(self, repo: CareerRepository):
        self.repo = repo

    def ingest_question(
        self,
        item: QuestionIngestItem,
        session_id: int | None = None,
        job_id: int | None = None,
    ) -> tuple[int, bool]:
        """
        Ingest an interview question with deterministic deduplication.
        Returns: (question_id, is_new_record)
        """
        now_iso = datetime.now(UTC).isoformat()
        norm_incoming = normalize_question_text(item.question)

        # Check existing questions for deterministic match
        all_questions = self.repo.get_all_questions()
        for existing in all_questions:
            if existing.id is None:
                continue
            if normalize_question_text(existing.question) == norm_incoming:
                # Substantially identical question found -> increment frequency count
                new_count = existing.times_asked + item.times_asked
                query = """
                UPDATE interview_questions
                SET times_asked = ?,
                    feedback = COALESCE(?, feedback),
                    was_correct = COALESCE(?, was_correct)
                WHERE id = ?
                """
                was_correct_int = (
                    (1 if item.was_correct else 0) if item.was_correct is not None else None
                )
                self.repo.conn.execute(
                    query, (new_count, item.feedback, was_correct_int, existing.id)
                )
                self.repo.conn.commit()
                return existing.id, False

        # Guard: AI generated answers must NEVER be silently marked verified
        verified_flag = False if item.source_type == "ai_generated" else item.verified

        # Insert new question
        new_q = InterviewQuestion(
            session_id=session_id,
            job_id=job_id,
            company=item.company,
            role=item.role,
            question=item.question,
            category=item.category,
            topic=item.topic,
            user_answer=item.user_answer,
            expected_answer=item.expected_answer,
            feedback=item.feedback,
            was_correct=item.was_correct,
            difficulty=item.difficulty,
            source=f"{item.source} [{item.source_type}]"
            + (f" ({item.original_reference})" if item.original_reference else ""),
            verified=verified_flag,
            times_asked=item.times_asked,
            created_at=now_iso,
        )
        q_id = self.repo.insert_interview_question(new_q)
        return q_id, True

    def ingest_payload(self, payload: CareerIngestPayload) -> IngestionResult:
        """Process a structured batch ingestion payload with full provenance preservation."""
        result = IngestionResult()
        now_iso = datetime.now(UTC).isoformat()

        # 1. Optional Session
        session_id = None
        if payload.session:
            if isinstance(payload.session, InterviewSession):
                sess = payload.session
            else:
                sess = InterviewSession(
                    company=payload.session.company,
                    role=payload.session.role,
                    date=payload.session.date,
                    round=payload.session.round,
                    outcome=payload.session.outcome,
                    notes=payload.session.notes,
                    created_at=payload.session.created_at or now_iso,
                )
            session_id = self.repo.insert_interview_session(sess)
            result.session_id = session_id

        # 2. Questions
        for q_item in payload.questions:
            try:
                _, is_new = self.ingest_question(q_item, session_id=session_id)
                if is_new:
                    result.questions_inserted += 1
                else:
                    result.questions_deduplicated += 1
            except (ValueError, sqlite3.Error, TypeError, KeyError) as e:
                result.errors.append(f"Failed to ingest question '{q_item.question[:30]}...': {e}")

        # 3. Weak Areas
        for wa_item in payload.weak_areas:
            try:
                wa = WeakArea(
                    topic=wa_item.topic,
                    description=wa_item.description,
                    evidence_source=f"{wa_item.evidence_source or payload.source} [{wa_item.source_type}]",
                    severity=wa_item.severity,
                    confidence=wa_item.confidence,
                    created_at=now_iso,
                )
                self.repo.insert_weak_area(wa)
                result.weak_areas_inserted += 1
            except (ValueError, sqlite3.Error, TypeError, KeyError) as e:
                result.errors.append(f"Failed to ingest weak area '{wa_item.topic}': {e}")

        # 4. Knowledge Items
        for k_item in payload.knowledge_items:
            try:
                # Guard against auto-verifying AI generated notes
                verified_flag = False if k_item.source_type == "ai_generated" else k_item.verified
                ki = KnowledgeItem(
                    topic=k_item.topic,
                    concept=k_item.concept,
                    explanation=k_item.explanation,
                    source=f"{k_item.source} [{k_item.source_type}]",
                    verified=verified_flag,
                    related_question_ids=k_item.related_question_ids,
                    created_at=now_iso,
                )
                self.repo.insert_knowledge_item(ki)
                result.knowledge_items_inserted += 1
            except (ValueError, sqlite3.Error, TypeError, KeyError) as e:
                result.errors.append(f"Failed to ingest knowledge item '{k_item.concept}': {e}")

        return result

    def import_from_dict(self, data: dict | list) -> IngestionResult:
        """Import from raw dictionary or list of payload dictionaries."""
        combined_result = IngestionResult()

        if isinstance(data, list):
            for item in data:
                sub_res = self.import_from_dict(item)
                combined_result.questions_inserted += sub_res.questions_inserted
                combined_result.questions_deduplicated += sub_res.questions_deduplicated
                combined_result.weak_areas_inserted += sub_res.weak_areas_inserted
                combined_result.knowledge_items_inserted += sub_res.knowledge_items_inserted
                combined_result.errors.extend(sub_res.errors)
            return combined_result

        # Single dictionary -> parse CareerIngestPayload
        payload = CareerIngestPayload.model_validate(data)
        return self.ingest_payload(payload)

    def import_from_file(self, file_path: str) -> IngestionResult:
        """Import structured career/interview data from YAML or JSON file."""
        p = Path(file_path)
        if not p.exists():
            raise FileNotFoundError(f"Historical interview file not found: {file_path}")

        raw_content = p.read_text(encoding="utf-8")
        if p.suffix in [".yaml", ".yml"]:
            data = yaml.safe_load(raw_content)
        elif p.suffix == ".json":
            data = json.loads(raw_content)
        else:
            raise ValueError(f"Unsupported file format '{p.suffix}'. Expected .yaml, .yml, or .json")

        if not data:
            return IngestionResult()

        return self.import_from_dict(data)
