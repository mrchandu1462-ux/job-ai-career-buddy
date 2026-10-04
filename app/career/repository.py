"""Repository and matching engine for Career & Interview Knowledge Base."""

import json
import sqlite3
from datetime import UTC, datetime
from typing import Any

from app.db.models import (
    AssessmentRecord,
    AssessmentStatus,
    AssessmentType,
    InterviewQuestion,
    InterviewSession,
    KnowledgeItem,
    MockQuestionItem,
    NormalizedJob,
    PreparationSession,
    WeakArea,
)


class CareerRepository:
    """DAO for managing previous interview sessions, questions, weak areas, prep logs, and knowledge items."""

    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    # -------------------------------------------------------------------------
    # Interview Sessions
    # -------------------------------------------------------------------------
    def _row_to_interview_session(self, row: sqlite3.Row) -> InterviewSession:
        return InterviewSession(
            id=row["id"],
            company=row["company"],
            role=row["role"],
            date=row["date"],
            round=row["round"],
            outcome=row["outcome"],
            notes=row["notes"],
            created_at=row["created_at"],
        )

    def insert_interview_session(self, session: InterviewSession) -> int:
        """Insert a historical interview session."""
        query = """
        INSERT INTO interview_sessions (company, role, date, round, outcome, notes, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """
        cursor = self.conn.execute(
            query,
            (
                session.company,
                session.role,
                session.date,
                session.round,
                session.outcome,
                session.notes,
                session.created_at,
            ),
        )
        self.conn.commit()
        return cursor.lastrowid

    def get_interview_session(self, session_id: int) -> InterviewSession | None:
        """Fetch session by ID."""
        cursor = self.conn.execute(
            "SELECT * FROM interview_sessions WHERE id = ?", (session_id,)
        )
        row = cursor.fetchone()
        return self._row_to_interview_session(row) if row else None

    def list_interview_sessions(
        self, company: str | None = None
    ) -> list[InterviewSession]:
        """List sessions optionally filtered by company."""
        query = "SELECT * FROM interview_sessions WHERE 1=1"
        params: list[Any] = []
        if company:
            query += " AND company LIKE ?"
            params.append(f"%{company}%")
        query += " ORDER BY date DESC, id DESC"
        cursor = self.conn.execute(query, tuple(params))
        return [self._row_to_interview_session(r) for r in cursor.fetchall()]

    # -------------------------------------------------------------------------
    # Interview Questions
    # -------------------------------------------------------------------------
    def _row_to_interview_question(self, row: sqlite3.Row) -> InterviewQuestion:
        was_correct_val = (
            bool(row["was_correct"]) if row["was_correct"] is not None else None
        )
        return InterviewQuestion(
            id=row["id"],
            session_id=row["session_id"],
            job_id=row["job_id"],
            company=row["company"],
            role=row["role"],
            question=row["question"],
            category=row["category"],
            topic=row["topic"],
            user_answer=row["user_answer"],
            expected_answer=row["expected_answer"],
            feedback=row["feedback"],
            was_correct=was_correct_val,
            difficulty=row["difficulty"],
            source=row["source"],
            verified=bool(row["verified"]),
            times_asked=row["times_asked"],
            created_at=row["created_at"],
        )

    def insert_interview_question(self, q: InterviewQuestion) -> int:
        """Insert an interview question."""
        was_correct_int = (
            (1 if q.was_correct else 0) if q.was_correct is not None else None
        )
        query = """
        INSERT INTO interview_questions (
            session_id, job_id, company, role, question, category, topic,
            user_answer, expected_answer, feedback, was_correct, difficulty,
            source, verified, times_asked, created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        cursor = self.conn.execute(
            query,
            (
                q.session_id,
                q.job_id,
                q.company,
                q.role,
                q.question,
                q.category,
                q.topic,
                q.user_answer,
                q.expected_answer,
                q.feedback,
                was_correct_int,
                q.difficulty,
                q.source,
                1 if q.verified else 0,
                q.times_asked,
                q.created_at,
            ),
        )
        self.conn.commit()
        return cursor.lastrowid

    def get_interview_question(self, question_id: int) -> InterviewQuestion | None:
        """Fetch question by ID."""
        cursor = self.conn.execute(
            "SELECT * FROM interview_questions WHERE id = ?", (question_id,)
        )
        row = cursor.fetchone()
        return self._row_to_interview_question(row) if row else None

    def get_all_questions(self) -> list[InterviewQuestion]:
        """Fetch all stored questions."""
        cursor = self.conn.execute(
            "SELECT * FROM interview_questions ORDER BY created_at DESC"
        )
        return [self._row_to_interview_question(r) for r in cursor.fetchall()]

    def get_questions_by_company(self, company: str) -> list[InterviewQuestion]:
        """Retrieve questions asked by a specific company."""
        query = """
        SELECT q.* FROM interview_questions q
        LEFT JOIN interview_sessions s ON q.session_id = s.id
        WHERE q.company LIKE ? OR s.company LIKE ?
        ORDER BY q.created_at DESC
        """
        cursor = self.conn.execute(query, (f"%{company}%", f"%{company}%"))
        return [self._row_to_interview_question(r) for r in cursor.fetchall()]

    def get_questions_by_role(self, role: str) -> list[InterviewQuestion]:
        """Retrieve questions asked for a specific role."""
        query = """
        SELECT q.* FROM interview_questions q
        LEFT JOIN interview_sessions s ON q.session_id = s.id
        WHERE q.role LIKE ? OR s.role LIKE ?
        ORDER BY q.created_at DESC
        """
        cursor = self.conn.execute(query, (f"%{role}%", f"%{role}%"))
        return [self._row_to_interview_question(r) for r in cursor.fetchall()]

    def get_questions_by_topic(self, topic: str) -> list[InterviewQuestion]:
        """Retrieve questions matching a specific topic."""
        query = """
        SELECT * FROM interview_questions
        WHERE topic LIKE ?
        ORDER BY created_at DESC
        """
        cursor = self.conn.execute(query, (f"%{topic}%",))
        return [self._row_to_interview_question(r) for r in cursor.fetchall()]

    def get_incorrect_questions(self) -> list[InterviewQuestion]:
        """Retrieve questions where the candidate previously answered incorrectly."""
        query = """
        SELECT * FROM interview_questions
        WHERE was_correct = 0
        ORDER BY created_at DESC
        """
        cursor = self.conn.execute(query)
        return [self._row_to_interview_question(r) for r in cursor.fetchall()]

    def get_repeated_questions(self, min_times: int = 2) -> list[InterviewQuestion]:
        """Retrieve questions that have been asked multiple times."""
        query = """
        SELECT * FROM interview_questions
        WHERE times_asked >= ?
        ORDER BY times_asked DESC, created_at DESC
        """
        cursor = self.conn.execute(query, (min_times,))
        return [self._row_to_interview_question(r) for r in cursor.fetchall()]

    # -------------------------------------------------------------------------
    # Weak Areas
    # -------------------------------------------------------------------------
    def _row_to_weak_area(self, row: sqlite3.Row) -> WeakArea:
        return WeakArea(
            id=row["id"],
            topic=row["topic"],
            description=row["description"],
            evidence_source=row["evidence_source"],
            severity=row["severity"],
            confidence=row["confidence"],
            last_reviewed=row["last_reviewed"],
            review_count=row["review_count"],
            resolved=bool(row["resolved"]),
            created_at=row["created_at"],
        )

    def insert_weak_area(self, area: WeakArea) -> int:
        """Insert a newly identified weak area."""
        query = """
        INSERT INTO weak_areas (
            topic, description, evidence_source, severity, confidence,
            last_reviewed, review_count, resolved, created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        cursor = self.conn.execute(
            query,
            (
                area.topic,
                area.description,
                area.evidence_source,
                area.severity,
                area.confidence,
                area.last_reviewed,
                area.review_count,
                1 if area.resolved else 0,
                area.created_at,
            ),
        )
        self.conn.commit()
        return cursor.lastrowid

    def get_weak_area(self, weak_area_id: int) -> WeakArea | None:
        """Fetch weak area by ID."""
        cursor = self.conn.execute(
            "SELECT * FROM weak_areas WHERE id = ?", (weak_area_id,)
        )
        row = cursor.fetchone()
        return self._row_to_weak_area(row) if row else None

    def list_weak_areas(
        self, resolved: bool | None = None, topic: str | None = None
    ) -> list[WeakArea]:
        """List weak areas with optional resolved filter."""
        query = "SELECT * FROM weak_areas WHERE 1=1"
        params: list[Any] = []
        if resolved is not None:
            query += " AND resolved = ?"
            params.append(1 if resolved else 0)
        if topic:
            query += " AND topic LIKE ?"
            params.append(f"%{topic}%")
        query += " ORDER BY confidence ASC, id ASC"
        cursor = self.conn.execute(query, tuple(params))
        return [self._row_to_weak_area(r) for r in cursor.fetchall()]

    def update_weak_area_review(
        self,
        weak_area_id: int,
        new_confidence: float | None = None,
        resolved: bool | None = None,
    ) -> None:
        """Record review progress and update confidence/resolved status."""
        now_iso = datetime.now(UTC).isoformat()
        query = """
        UPDATE weak_areas
        SET review_count = review_count + 1,
            last_reviewed = ?,
            confidence = COALESCE(?, confidence),
            resolved = COALESCE(?, resolved)
        WHERE id = ?
        """
        resolved_int = (1 if resolved else 0) if resolved is not None else None
        self.conn.execute(query, (now_iso, new_confidence, resolved_int, weak_area_id))
        self.conn.commit()

    # -------------------------------------------------------------------------
    # Preparation Sessions
    # -------------------------------------------------------------------------
    def _row_to_prep_session(self, row: sqlite3.Row) -> PreparationSession:
        topics_list = json.loads(row["topics"]) if row["topics"] else []
        return PreparationSession(
            id=row["id"],
            job_id=row["job_id"],
            date=row["date"],
            topics=topics_list,
            questions_attempted=row["questions_attempted"],
            performance_summary=row["performance_summary"],
            notes=row["notes"],
            created_at=row["created_at"],
        )

    def insert_prep_session(self, session: PreparationSession) -> int:
        """Insert a preparation session log."""
        query = """
        INSERT INTO preparation_sessions (
            job_id, date, topics, questions_attempted, performance_summary, notes, created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """
        cursor = self.conn.execute(
            query,
            (
                session.job_id,
                session.date,
                json.dumps(session.topics),
                session.questions_attempted,
                session.performance_summary,
                session.notes,
                session.created_at,
            ),
        )
        self.conn.commit()
        return cursor.lastrowid

    def list_prep_sessions(
        self, job_id: int | None = None
    ) -> list[PreparationSession]:
        """List preparation sessions."""
        query = "SELECT * FROM preparation_sessions WHERE 1=1"
        params: list[Any] = []
        if job_id is not None:
            query += " AND job_id = ?"
            params.append(job_id)
        query += " ORDER BY date DESC, id DESC"
        cursor = self.conn.execute(query, tuple(params))
        return [self._row_to_prep_session(r) for r in cursor.fetchall()]

    # -------------------------------------------------------------------------
    # Knowledge Items
    # -------------------------------------------------------------------------
    def _row_to_knowledge_item(self, row: sqlite3.Row) -> KnowledgeItem:
        q_ids = (
            json.loads(row["related_question_ids"])
            if row["related_question_ids"]
            else []
        )
        return KnowledgeItem(
            id=row["id"],
            topic=row["topic"],
            concept=row["concept"],
            explanation=row["explanation"],
            source=row["source"],
            verified=bool(row["verified"]),
            related_question_ids=q_ids,
            created_at=row["created_at"],
        )

    def insert_knowledge_item(self, item: KnowledgeItem) -> int:
        """Insert a verified or study knowledge item."""
        query = """
        INSERT INTO knowledge_items (topic, concept, explanation, source, verified, related_question_ids, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """
        cursor = self.conn.execute(
            query,
            (
                item.topic,
                item.concept,
                item.explanation,
                item.source,
                1 if item.verified else 0,
                json.dumps(item.related_question_ids),
                item.created_at,
            ),
        )
        self.conn.commit()
        return cursor.lastrowid

    def get_knowledge_items_by_topic(self, topic: str) -> list[KnowledgeItem]:
        """Fetch knowledge items for a topic."""
        query = "SELECT * FROM knowledge_items WHERE topic LIKE ? ORDER BY id ASC"
        cursor = self.conn.execute(query, (f"%{topic}%",))
        return [self._row_to_knowledge_item(r) for r in cursor.fetchall()]

    # -------------------------------------------------------------------------
    # Cross-Entity Job Matching & Preparation Synthesis
    # -------------------------------------------------------------------------
    def get_questions_for_job(
        self, job: NormalizedJob, include_topics: bool = True
    ) -> list[InterviewQuestion]:
        """Retrieve previous questions relevant to a specific job based on company, role, or skills."""
        matched: dict[int, InterviewQuestion] = {}

        # 1. Company exact/partial match
        if job.company:
            for q in self.get_questions_by_company(job.company):
                if q.id is not None:
                    matched[q.id] = q

        # 2. Role match
        if job.title:
            for q in self.get_questions_by_role(job.title):
                if q.id is not None:
                    matched[q.id] = q

        # 3. Topic & skills match
        if include_topics and job.skills:
            for skill in job.skills:
                for q in self.get_questions_by_topic(skill):
                    if q.id is not None:
                        matched[q.id] = q

        return list(matched.values())

    def match_career_context_for_job(self, job: NormalizedJob) -> dict[str, Any]:
        """Synthesize job context against historical career knowledge base."""
        matched_questions = self.get_questions_for_job(job)

        # Extract topics from matched questions and job skills
        topics = set(job.skills)
        for q in matched_questions:
            topics.add(q.topic)

        # Match active weak areas for these topics
        matched_weak_areas: list[WeakArea] = []
        for topic in topics:
            matched_weak_areas.extend(self.list_weak_areas(resolved=False, topic=topic))

        # Match reference knowledge items
        matched_knowledge: list[KnowledgeItem] = []
        for topic in topics:
            matched_knowledge.extend(self.get_knowledge_items_by_topic(topic))

        return {
            "job_id": job.id,
            "company": job.company,
            "title": job.title,
            "relevant_topics": sorted(topics),
            "relevant_questions": matched_questions,
            "relevant_weak_areas": matched_weak_areas,
            "relevant_knowledge_items": matched_knowledge,
        }

    # -------------------------------------------------------------------------
    # Assessments
    # -------------------------------------------------------------------------
    def _row_to_assessment_record(self, row: sqlite3.Row) -> AssessmentRecord:
        raw_qs = json.loads(row["questions"]) if row["questions"] else []
        questions = [MockQuestionItem.model_validate(q) for q in raw_qs]
        breakdown = json.loads(row["topic_breakdown"]) if row["topic_breakdown"] else {}

        return AssessmentRecord(
            id=row["id"],
            job_id=row["job_id"],
            company=row["company"],
            role=row["role"],
            assessment_type=AssessmentType(row["assessment_type"]),
            title=row["title"],
            time_limit_minutes=row["time_limit_minutes"],
            questions=questions,
            status=AssessmentStatus(row["status"]),
            score=row["score"],
            total_questions=row["total_questions"],
            correct_count=row["correct_count"],
            incorrect_count=row["incorrect_count"],
            topic_breakdown=breakdown,
            created_at=row["created_at"],
            completed_at=row["completed_at"],
        )

    def insert_assessment(self, record: AssessmentRecord) -> int:
        """Persist a new assessment record."""
        raw_questions = [q.model_dump() for q in record.questions]
        query = """
        INSERT INTO assessments (
            job_id, company, role, assessment_type, title, time_limit_minutes,
            questions, status, score, total_questions, correct_count,
            incorrect_count, topic_breakdown, created_at, completed_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        cursor = self.conn.execute(
            query,
            (
                record.job_id,
                record.company,
                record.role,
                record.assessment_type.value,
                record.title,
                record.time_limit_minutes,
                json.dumps(raw_questions),
                record.status.value,
                record.score,
                record.total_questions,
                record.correct_count,
                record.incorrect_count,
                json.dumps(record.topic_breakdown),
                record.created_at,
                record.completed_at,
            ),
        )
        self.conn.commit()
        return cursor.lastrowid

    def get_assessment(self, assessment_id: int) -> AssessmentRecord | None:
        """Fetch assessment by ID."""
        cursor = self.conn.execute("SELECT * FROM assessments WHERE id = ?", (assessment_id,))
        row = cursor.fetchone()
        return self._row_to_assessment_record(row) if row else None

    def list_assessments(self, job_id: int | None = None) -> list[AssessmentRecord]:
        """Fetch all stored assessments, optionally filtered by job_id."""
        query = "SELECT * FROM assessments WHERE 1=1"
        params: list[Any] = []
        if job_id is not None:
            query += " AND job_id = ?"
            params.append(job_id)
        query += " ORDER BY id DESC"
        cursor = self.conn.execute(query, tuple(params))
        return [self._row_to_assessment_record(r) for r in cursor.fetchall()]

