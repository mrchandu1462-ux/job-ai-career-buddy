"""Preparation engine for generating deterministic, provenance-backed job preparation plans."""

from datetime import UTC, datetime

from pydantic import BaseModel, ConfigDict, Field

from app.career.repository import CareerRepository
from app.db.models import (
    InterviewQuestion,
    KnowledgeItem,
    NormalizedJob,
    WeakArea,
)
from app.db.repository import JobRepository


class RecommendedSession(BaseModel):
    """Structured study or mock drill module for candidate preparation."""

    model_config = ConfigDict(extra="forbid")

    session_name: str
    focus_topic: str
    target_weak_areas: list[str] = Field(default_factory=list)
    practice_questions: list[str] = Field(default_factory=list)
    verified_reference_concepts: list[str] = Field(default_factory=list)
    estimated_duration_minutes: int = 45


class PreparationPlan(BaseModel):
    """Complete tailored preparation plan synthesized deterministically for a target job."""

    model_config = ConfigDict(extra="forbid")

    job_id: int
    company: str
    title: str
    generated_at: str
    priority_topics: list[str]
    historical_questions: list[InterviewQuestion]
    incorrect_questions: list[InterviewQuestion]
    repeated_questions: list[InterviewQuestion]
    weak_areas: list[WeakArea]
    verified_knowledge: list[KnowledgeItem]
    recommended_sessions: list[RecommendedSession]
    rationale: list[str]


class PreparationEngine:
    """Deterministic preparation engine matching job descriptions against Career Knowledge Base."""

    def __init__(self, career_repo: CareerRepository, job_repo: JobRepository):
        self.career_repo = career_repo
        self.job_repo = job_repo

    def prepare_for_job(self, job_id: int) -> PreparationPlan:
        """
        Generate a comprehensive, deterministic preparation plan for a given job.
        Prioritizes:
          1. Job-required skills & title keywords
          2. Active candidate weak areas matching job topics (weighted by lower confidence / higher severity)
          3. Previously missed/incorrect questions
          4. High-frequency / repeated interview questions
          5. Verified reference knowledge items
        """
        job: NormalizedJob | None = self.job_repo.get_normalized_job(job_id)
        if not job:
            raise ValueError(f"NormalizedJob with id {job_id} not found in database.")

        now_iso = datetime.now(UTC).isoformat()

        # 1. Gather all related questions (company, role, skills)
        matched_questions = self.career_repo.get_questions_for_job(job)

        # 2. Extract specific categories of questions
        incorrect_questions = [q for q in matched_questions if q.was_correct is False]
        repeated_questions = [q for q in matched_questions if q.times_asked >= 2]

        # 3. Identify all active candidate topics
        job_topics = set(job.skills)
        if "Verification" in job.title or "DV" in job.title:
            job_topics.add("SystemVerilog")
            job_topics.add("UVM")
        if "RTL" in job.title:
            job_topics.add("Verilog")
            job_topics.add("Digital Design")

        for q in matched_questions:
            job_topics.add(q.topic)

        # 4. Gather active weak areas & rank by severity/confidence
        active_weak_areas: list[WeakArea] = []
        for topic in job_topics:
            active_weak_areas.extend(
                self.career_repo.list_weak_areas(resolved=False, topic=topic)
            )

        # Deduplicate weak areas by ID
        unique_weak_areas = {wa.id: wa for wa in active_weak_areas if wa.id is not None}
        sorted_weak_areas = sorted(
            unique_weak_areas.values(),
            key=lambda w: (
                0 if w.severity == "critical" else 1 if w.severity == "high" else 2,
                w.confidence,
            ),
        )

        # 5. Gather verified knowledge items
        knowledge_items: list[KnowledgeItem] = []
        for topic in job_topics:
            knowledge_items.extend(self.career_repo.get_knowledge_items_by_topic(topic))

        unique_knowledge = {ki.id: ki for ki in knowledge_items if ki.id is not None}
        verified_knowledge = [ki for ki in unique_knowledge.values() if ki.verified]

        # 6. Compute deterministic topic priorities
        # Priority weight score:
        # +3 for presence in active weak areas
        # +2 for previously missed question on topic
        # +2 for presence in job.skills
        # +1 for high-frequency question
        topic_scores: dict[str, int] = {t: 0 for t in job_topics}
        for t in job_topics:
            if t in job.skills:
                topic_scores[t] += 2
        for wa in sorted_weak_areas:
            if wa.topic in topic_scores:
                topic_scores[wa.topic] += 3
        for q in incorrect_questions:
            if q.topic in topic_scores:
                topic_scores[q.topic] += 2
        for q in repeated_questions:
            if q.topic in topic_scores:
                topic_scores[q.topic] += 1

        priority_topics = [
            topic
            for topic, score in sorted(
                topic_scores.items(), key=lambda item: (-item[1], item[0])
            )
        ]

        # 7. Generate structured recommended preparation sessions
        recommended_sessions: list[RecommendedSession] = []
        for top_topic in priority_topics[:4]:  # Top 4 priority topics
            topic_wa = [w.description for w in sorted_weak_areas if w.topic == top_topic]
            topic_qs = [
                q.question for q in matched_questions if q.topic == top_topic
            ]
            topic_ki = [
                k.concept for k in verified_knowledge if k.topic == top_topic
            ]

            recommended_sessions.append(
                RecommendedSession(
                    session_name=f"Deep-Dive & Drill: {top_topic}",
                    focus_topic=top_topic,
                    target_weak_areas=topic_wa,
                    practice_questions=topic_qs[:5],
                    verified_reference_concepts=topic_ki[:3],
                    estimated_duration_minutes=45 if topic_wa else 30,
                )
            )

        # 8. Document rationale
        rationale: list[str] = [
            f"Targeted for '{job.title}' at '{job.company}'.",
            f"Identified {len(job.skills)} required technical skills from job listing.",
            f"Found {len(matched_questions)} historical interview questions matching company, role, or topics.",
            f"Flagged {len(sorted_weak_areas)} active weak areas needing revision before interview.",
            f"Prioritized {len(incorrect_questions)} previously missed questions and {len(repeated_questions)} high-frequency questions.",
        ]

        return PreparationPlan(
            job_id=job.id if job.id is not None else job_id,
            company=job.company,
            title=job.title,
            generated_at=now_iso,
            priority_topics=priority_topics,
            historical_questions=matched_questions,
            incorrect_questions=incorrect_questions,
            repeated_questions=repeated_questions,
            weak_areas=sorted_weak_areas,
            verified_knowledge=verified_knowledge,
            recommended_sessions=recommended_sessions,
            rationale=rationale,
        )
