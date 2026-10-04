"""Question Bank querying, explainable priority engine, and review pool categorization."""

import sqlite3
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.career.repository import CareerRepository
from app.db.models import InterviewQuestion, NormalizedJob


class QuestionBankFilter(BaseModel):
    """Filter criteria for searching questions in the Career Question Bank."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    company: str | None = None
    role: str | None = None
    round: str | None = None
    topic: str | None = None
    difficulty: str | None = None
    min_times_asked: int | None = None
    was_correct: bool | None = None
    source: str | None = None
    verified_only: bool = False


class PrioritizedQuestion(BaseModel):
    """Interview question annotated with explainable priority ranking and selection reasons."""

    model_config = ConfigDict(extra="forbid")

    question: InterviewQuestion
    priority_score: int = Field(..., ge=0)
    priority_level: str = Field(..., description="'HIGH', 'MEDIUM', 'LOW'")
    reasons: list[str] = Field(default_factory=list)


class QuestionReviewPool(BaseModel):
    """Complete 8-category review pool presented to candidate prior to final assessment."""

    model_config = ConfigDict(extra="forbid")

    job_id: int
    company: str
    title: str
    must_know: list[InterviewQuestion] = Field(default_factory=list)
    frequently_asked: list[InterviewQuestion] = Field(default_factory=list)
    previously_missed: list[InterviewQuestion] = Field(default_factory=list)
    job_specific: list[InterviewQuestion] = Field(default_factory=list)
    company_specific: list[InterviewQuestion] = Field(default_factory=list)
    weak_areas: list[InterviewQuestion] = Field(default_factory=list)
    fundamentals: list[InterviewQuestion] = Field(default_factory=list)
    advanced_bonus: list[InterviewQuestion] = Field(default_factory=list)
    total_unique_questions: int = 0


class QuestionBankService:
    """Service for querying, grouping, prioritizing, and building pre-interview study review pools."""

    def __init__(self, conn: sqlite3.Connection, career_repo: CareerRepository):
        self.conn = conn
        self.career_repo = career_repo

    def query_questions(self, filter_params: QuestionBankFilter) -> list[InterviewQuestion]:
        """Execute flexible multi-dimensional query over stored historical/mock questions."""
        query = """
        SELECT q.* FROM interview_questions q
        LEFT JOIN interview_sessions s ON q.session_id = s.id
        WHERE 1=1
        """
        params: list[Any] = []

        if filter_params.company:
            query += " AND (q.company LIKE ? OR s.company LIKE ?)"
            params.extend([f"%{filter_params.company}%", f"%{filter_params.company}%"])

        if filter_params.role:
            query += " AND (q.role LIKE ? OR s.role LIKE ?)"
            params.extend([f"%{filter_params.role}%", f"%{filter_params.role}%"])

        if filter_params.round:
            query += " AND s.round LIKE ?"
            params.append(f"%{filter_params.round}%")

        if filter_params.topic:
            query += " AND q.topic LIKE ?"
            params.append(f"%{filter_params.topic}%")

        if filter_params.difficulty:
            query += " AND LOWER(q.difficulty) = LOWER(?)"
            params.append(filter_params.difficulty)

        if filter_params.min_times_asked is not None:
            query += " AND q.times_asked >= ?"
            params.append(filter_params.min_times_asked)

        if filter_params.was_correct is not None:
            query += " AND q.was_correct = ?"
            params.append(1 if filter_params.was_correct else 0)

        if filter_params.source:
            query += " AND q.source LIKE ?"
            params.append(f"%{filter_params.source}%")

        if filter_params.verified_only:
            query += " AND q.verified = 1"

        query += " ORDER BY q.times_asked DESC, q.created_at DESC"

        cursor = self.conn.execute(query, tuple(params))
        return [self.career_repo._row_to_interview_question(r) for r in cursor.fetchall()]

    def group_by(
        self, questions: list[InterviewQuestion], group_key: str
    ) -> dict[str, list[InterviewQuestion]]:
        """Group questions by key: 'company', 'role', 'topic', 'difficulty', 'correctness', or 'source'."""
        grouped: dict[str, list[InterviewQuestion]] = {}
        for q in questions:
            if group_key == "company":
                key = q.company or "Unspecified Company"
            elif group_key == "role":
                key = q.role or "Unspecified Role"
            elif group_key == "topic":
                key = q.topic
            elif group_key == "difficulty":
                key = q.difficulty or "unrated"
            elif group_key == "correctness":
                if q.was_correct is True:
                    key = "Correct"
                elif q.was_correct is False:
                    key = "Incorrect / Missed"
                else:
                    key = "Unattempted"
            elif group_key == "source":
                key = q.source
            else:
                key = "All"

            grouped.setdefault(key, []).append(q)
        return grouped

    def prioritize_questions_for_job(
        self, job: NormalizedJob, candidate_questions: list[InterviewQuestion] | None = None
    ) -> list[PrioritizedQuestion]:
        """
        Score and prioritize questions for a target job with clear, explainable reasons.

        Priority Rules:
        +35: Previously answered incorrectly by user
        +25: High frequency (asked >= 2 times across interviews)
        +20: Directly matching target job skills or title keywords
        +20: Related to an active, unresolved weak area
        +15: Company match (asked previously by target company)
        +10: Role match (asked for identical role title)
        +10: Core fundamental topic (SystemVerilog, UVM, Digital Design, AXI, CDC)
        """
        if candidate_questions is None:
            candidate_questions = self.career_repo.get_all_questions()

        active_weak_areas = self.career_repo.list_weak_areas(resolved=False)
        weak_topics = {w.topic.lower() for w in active_weak_areas}
        job_skills = {s.lower() for s in job.skills}

        fundamental_topics = {
            "systemverilog",
            "verilog",
            "digital design",
            "uvm",
            "axi",
            "fifo",
            "cdc",
            "clock domain crossing",
            "sva",
            "assertions",
        }

        prioritized: list[PrioritizedQuestion] = []

        for q in candidate_questions:
            score = 0
            reasons: list[str] = []
            topic_lower = q.topic.lower()

            # 1. Previously Missed
            if q.was_correct is False:
                score += 35
                reasons.append("Previously answered incorrectly")

            # 2. Repeated / High Frequency
            if q.times_asked >= 2:
                score += 25
                reasons.append(f"Appeared in {q.times_asked} historical interviews / tests")

            # 3. Direct Job Skills Match
            if any(s in topic_lower or topic_lower in s for s in job_skills):
                score += 20
                reasons.append(f"Directly required by target job skills ('{q.topic}')")

            # 4. Active Weak Area
            if any(w in topic_lower or topic_lower in w for w in weak_topics):
                score += 20
                reasons.append(f"Active candidate weak area: '{q.topic}'")

            # 5. Company Match
            if job.company and q.company and (
                job.company.lower() in q.company.lower() or q.company.lower() in job.company.lower()
            ):
                score += 15
                reasons.append(f"Asked by target company ({job.company})")

            # 6. Role Match
            if job.title and q.role and (
                job.title.lower() in q.role.lower() or q.role.lower() in job.title.lower()
            ):
                score += 10
                reasons.append(f"Asked for matching role ({job.title})")

            # 7. Fundamental Concept
            if any(f in topic_lower for f in fundamental_topics):
                score += 10
                reasons.append("Core VLSI / DV fundamental concept")

            if score >= 50:
                level = "HIGH"
            elif score >= 25:
                level = "MEDIUM"
            else:
                level = "LOW"

            prioritized.append(
                PrioritizedQuestion(
                    question=q,
                    priority_score=score,
                    priority_level=level,
                    reasons=reasons,
                )
            )

        # Sort descending by priority score
        prioritized.sort(key=lambda item: -item.priority_score)
        return prioritized

    def build_review_pool_for_job(self, job: NormalizedJob) -> QuestionReviewPool:
        """
        Build the full pre-interview question review pool across 8 categories:
        A. Must Know
        B. Frequently Asked
        C. Previously Missed
        D. Job-Specific
        E. Company-Specific
        F. Weak Areas
        G. Fundamentals
        H. Advanced / Bonus
        """
        all_qs = self.career_repo.get_all_questions()
        active_weak_areas = self.career_repo.list_weak_areas(resolved=False)
        weak_topics = {w.topic.lower() for w in active_weak_areas}
        job_skills = {s.lower() for s in job.skills}

        fundamental_keywords = {
            "digital design",
            "boolean",
            "flip-flop",
            "fsm",
            "verilog",
            "systemverilog",
            "oop",
            "inheritance",
            "polymorphism",
        }

        must_know: list[InterviewQuestion] = []
        frequently_asked: list[InterviewQuestion] = []
        previously_missed: list[InterviewQuestion] = []
        job_specific: list[InterviewQuestion] = []
        company_specific: list[InterviewQuestion] = []
        weak_area_qs: list[InterviewQuestion] = []
        fundamentals: list[InterviewQuestion] = []
        advanced_bonus: list[InterviewQuestion] = []

        seen_ids: set[int] = set()

        for q in all_qs:
            topic_lower = q.topic.lower()
            if q.id is not None:
                seen_ids.add(q.id)

            # C. Previously Missed
            if q.was_correct is False:
                previously_missed.append(q)

            # B. Frequently Asked
            if q.times_asked >= 2:
                frequently_asked.append(q)

            # E. Company-Specific
            if job.company and q.company and (
                job.company.lower() in q.company.lower() or q.company.lower() in job.company.lower()
            ):
                company_specific.append(q)

            # D. Job-Specific
            if any(s in topic_lower or topic_lower in s for s in job_skills):
                job_specific.append(q)

            # F. Weak Areas
            if any(w in topic_lower or topic_lower in w for w in weak_topics):
                weak_area_qs.append(q)

            # G. Fundamentals
            if any(fk in topic_lower or fk in q.question.lower() for fk in fundamental_keywords):
                fundamentals.append(q)

            # H. Advanced / Bonus
            if (q.difficulty and q.difficulty.lower() == "hard") or (
                "cdc" in topic_lower or "uvm ral" in topic_lower or "axi burst" in topic_lower
            ):
                advanced_bonus.append(q)

            # A. Must Know (Intersection of high relevance + frequency or weak area)
            if (
                q.was_correct is False
                or q.times_asked >= 2
                or (
                    job.company
                    and q.company
                    and (
                        job.company.lower() in q.company.lower()
                        or q.company.lower() in job.company.lower()
                    )
                )
            ):
                must_know.append(q)

        return QuestionReviewPool(
            job_id=job.id if job.id is not None else 0,
            company=job.company,
            title=job.title,
            must_know=must_know,
            frequently_asked=frequently_asked,
            previously_missed=previously_missed,
            job_specific=job_specific,
            company_specific=company_specific,
            weak_areas=weak_area_qs,
            fundamentals=fundamentals,
            advanced_bonus=advanced_bonus,
            total_unique_questions=len(seen_ids),
        )
