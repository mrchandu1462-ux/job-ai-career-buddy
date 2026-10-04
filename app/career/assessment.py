"""Adaptive assessment engine for timed mocks, pre-interview drills, remediation, and schedules."""

import json
import sqlite3
from datetime import UTC, datetime, timedelta
from typing import Any

from app.career.repository import CareerRepository
from app.db.models import (
    AssessmentRecord,
    AssessmentStatus,
    AssessmentType,
    MockQuestionItem,
    PreparationSchedule,
    ReadinessAssessment,
    ScheduleMilestone,
    WeakArea,
)
from app.db.repository import JobRepository


class AdaptiveAssessmentEngine:
    """Adaptive engine for generating, scoring, and remediating mock assessments and preparation schedules."""

    def __init__(self, conn: sqlite3.Connection, career_repo: CareerRepository, job_repo: JobRepository):
        self.conn = conn
        self.career_repo = career_repo
        self.job_repo = job_repo

    # -------------------------------------------------------------------------
    # Assessment Database Operations
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

    # -------------------------------------------------------------------------
    # Assessment Generation
    # -------------------------------------------------------------------------
    def generate_mock_test(
        self,
        job_id: int | None = None,
        topic: str | None = None,
        time_limit_minutes: int = 45,
        num_questions: int = 5,
    ) -> AssessmentRecord:
        """Generate a personalized timed mock test from historical interview questions."""
        now_iso = datetime.now(UTC).isoformat()
        company = None
        role = None

        candidate_questions = []
        if job_id is not None:
            job = self.job_repo.get_normalized_job(job_id)
            if job:
                company = job.company
                role = job.title
                candidate_questions = self.career_repo.get_questions_for_job(job)
        elif topic is not None:
            candidate_questions = self.career_repo.get_questions_by_topic(topic)
        else:
            candidate_questions = self.career_repo.get_all_questions()

        # Fallback to all questions if specific pool is insufficient
        if not candidate_questions:
            candidate_questions = self.career_repo.get_all_questions()

        selected_qs = candidate_questions[:num_questions]
        mock_items = [
            MockQuestionItem(
                question_id=q.id if q.id is not None else 0,
                question=q.question,
                topic=q.topic,
                difficulty=q.difficulty,
                expected_answer=q.expected_answer,
            )
            for q in selected_qs
        ]

        title = (
            f"Timed Mock Test: {company or topic or 'General VLSI'}"
            f" ({len(mock_items)} Questions / {time_limit_minutes} Mins)"
        )

        record = AssessmentRecord(
            job_id=job_id,
            company=company,
            role=role,
            assessment_type=AssessmentType.TIMED_MOCK,
            title=title,
            time_limit_minutes=time_limit_minutes,
            questions=mock_items,
            status=AssessmentStatus.CREATED,
            total_questions=len(mock_items),
            created_at=now_iso,
        )
        record.id = self.insert_assessment(record)
        return record

    def generate_pre_interview_assessment(
        self, job_id: int, time_limit_minutes: int = 60
    ) -> AssessmentRecord:
        """Generate a comprehensive pre-interview drill covering all required job topics and weak areas."""
        job = self.job_repo.get_normalized_job(job_id)
        if not job:
            raise ValueError(f"Job id {job_id} not found.")

        now_iso = datetime.now(UTC).isoformat()
        matched_questions = self.career_repo.get_questions_for_job(job)

        # Prioritize previously missed questions and high-frequency questions
        incorrect = [q for q in matched_questions if q.was_correct is False]
        repeated = [q for q in matched_questions if q.times_asked >= 2]
        others = [q for q in matched_questions if q not in incorrect and q not in repeated]

        pool = incorrect + repeated + others
        selected = pool[:10]  # Standard pre-interview drill length

        mock_items = [
            MockQuestionItem(
                question_id=q.id if q.id is not None else 0,
                question=q.question,
                topic=q.topic,
                difficulty=q.difficulty,
                expected_answer=q.expected_answer,
            )
            for q in selected
        ]

        title = f"Final Pre-Interview Assessment: {job.title} at {job.company}"
        record = AssessmentRecord(
            job_id=job_id,
            company=job.company,
            role=job.title,
            assessment_type=AssessmentType.PRE_INTERVIEW,
            title=title,
            time_limit_minutes=time_limit_minutes,
            questions=mock_items,
            status=AssessmentStatus.CREATED,
            total_questions=len(mock_items),
            created_at=now_iso,
        )
        record.id = self.insert_assessment(record)
        return record

    def generate_remediation_test(
        self,
        previous_assessment_id: int | None = None,
        job_id: int | None = None,
        time_limit_minutes: int = 30,
    ) -> AssessmentRecord:
        """Generate a targeted remediation assessment isolating mistakes and low-confidence topics."""
        now_iso = datetime.now(UTC).isoformat()
        company = None
        role = None
        target_question_ids: set[int] = set()

        if previous_assessment_id is not None:
            prev = self.get_assessment(previous_assessment_id)
            if prev:
                company = prev.company
                role = prev.role
                job_id = prev.job_id
                for q in prev.questions:
                    if q.was_correct is False:
                        target_question_ids.add(q.question_id)

        # If no specific previous assessment or no missed questions found, pull all historical incorrect questions
        if not target_question_ids:
            for q in self.career_repo.get_incorrect_questions():
                if q.id is not None:
                    target_question_ids.add(q.id)

        questions = [
            self.career_repo.get_interview_question(qid)
            for qid in target_question_ids
            if self.career_repo.get_interview_question(qid) is not None
        ]

        mock_items = [
            MockQuestionItem(
                question_id=q.id if q.id is not None else 0,
                question=q.question,
                topic=q.topic,
                difficulty=q.difficulty,
                expected_answer=q.expected_answer,
            )
            for q in questions
            if q is not None
        ]

        title = f"Remediation Assessment: Mistake Review & Gap Closure ({len(mock_items)} Questions)"
        record = AssessmentRecord(
            job_id=job_id,
            company=company,
            role=role,
            assessment_type=AssessmentType.REMEDIATION,
            title=title,
            time_limit_minutes=time_limit_minutes,
            questions=mock_items,
            status=AssessmentStatus.CREATED,
            total_questions=len(mock_items),
            created_at=now_iso,
        )
        record.id = self.insert_assessment(record)
        return record

    # -------------------------------------------------------------------------
    # Assessment Scoring & Weak-Area Updating
    # -------------------------------------------------------------------------
    def submit_assessment_answers(
        self, assessment_id: int, user_answers: list[dict[str, Any]]
    ) -> AssessmentRecord:
        """
        Score the assessment, update candidate performance, and adjust weak areas.
        user_answers format: [{'question_id': int, 'user_answer': str, 'was_correct': bool, 'time_spent_seconds': int, 'feedback': str}]
        """
        record = self.get_assessment(assessment_id)
        if not record:
            raise ValueError(f"Assessment id {assessment_id} not found.")

        now_iso = datetime.now(UTC).isoformat()
        answer_map = {ans["question_id"]: ans for ans in user_answers}

        correct_count = 0
        incorrect_count = 0
        topic_stats: dict[str, dict[str, int | float]] = {}

        updated_questions = []
        for q in record.questions:
            ans = answer_map.get(q.question_id)
            if ans:
                q.user_answer = ans.get("user_answer")
                q.was_correct = ans.get("was_correct")
                q.time_spent_seconds = ans.get("time_spent_seconds", 0)
                q.feedback = ans.get("feedback")
            else:
                q.was_correct = False

            if q.was_correct:
                correct_count += 1
            else:
                incorrect_count += 1

            # Update topic performance
            if q.topic not in topic_stats:
                topic_stats[q.topic] = {"correct": 0, "incorrect": 0, "total": 0}
            topic_stats[q.topic]["total"] += 1
            if q.was_correct:
                topic_stats[q.topic]["correct"] += 1
            else:
                topic_stats[q.topic]["incorrect"] += 1

            # Adaptive Weak-Area Feedback Loop
            existing_was = self.career_repo.list_weak_areas(topic=q.topic)
            if not q.was_correct:
                # Misunderstood concept -> update or create weak area
                if existing_was:
                    wa = existing_was[0]
                    new_conf = max(0.1, wa.confidence - 0.2)
                    self.career_repo.update_weak_area_review(
                        weak_area_id=wa.id, new_confidence=new_conf, resolved=False
                    )
                else:
                    self.career_repo.insert_weak_area(
                        WeakArea(
                            topic=q.topic,
                            description=f"Missed question during assessment: '{q.question}'",
                            evidence_source=f"Assessment #{assessment_id} ({record.title})",
                            severity="medium",
                            confidence=0.3,
                            created_at=now_iso,
                        )
                    )
            else:
                # Correct response -> improve topic confidence
                if existing_was:
                    wa = existing_was[0]
                    new_conf = min(1.0, wa.confidence + 0.2)
                    is_resolved = new_conf >= 0.8
                    self.career_repo.update_weak_area_review(
                        weak_area_id=wa.id,
                        new_confidence=new_conf,
                        resolved=is_resolved,
                    )

            updated_questions.append(q)

        total = len(updated_questions)
        final_score = round((correct_count / total * 100.0), 1) if total > 0 else 0.0

        # Persist completed assessment
        raw_qs = [q.model_dump() for q in updated_questions]
        query = """
        UPDATE assessments
        SET questions = ?,
            status = ?,
            score = ?,
            total_questions = ?,
            correct_count = ?,
            incorrect_count = ?,
            topic_breakdown = ?,
            completed_at = ?
        WHERE id = ?
        """
        self.conn.execute(
            query,
            (
                json.dumps(raw_qs),
                AssessmentStatus.COMPLETED.value,
                final_score,
                total,
                correct_count,
                incorrect_count,
                json.dumps(topic_stats),
                now_iso,
                assessment_id,
            ),
        )
        self.conn.commit()

        record.questions = updated_questions
        record.status = AssessmentStatus.COMPLETED
        record.score = final_score
        record.correct_count = correct_count
        record.incorrect_count = incorrect_count
        record.topic_breakdown = topic_stats
        record.completed_at = now_iso
        return record

    # -------------------------------------------------------------------------
    # Job Readiness Assessment
    # -------------------------------------------------------------------------
    def compute_job_readiness(
        self,
        job_id: int,
        ready_threshold: float = 80.0,
        critical_topic_ready_min: float = 65.0,
        borderline_threshold: float = 65.0,
        critical_topic_fail_min: float = 60.0,
        critical_topics: list[str] | None = None,
    ) -> ReadinessAssessment:
        """
        Compute an objective, deterministic readiness score (0-100%) for a job listing.

        Readiness Gates:
        - High Readiness (READY): Overall >= ready_threshold (default 80%) AND no critical topic < critical_topic_ready_min (default 65%)
        - Moderate Readiness (BORDERLINE): Overall >= borderline_threshold (default 65%) AND all critical topics >= critical_topic_fail_min (default 60%)
        - Needs Preparation (NOT READY): Overall < borderline_threshold OR any critical topic < critical_topic_fail_min
        """
        job = self.job_repo.get_normalized_job(job_id)
        if not job:
            raise ValueError(f"Job id {job_id} not found.")

        now_iso = datetime.now(UTC).isoformat()
        topics = set(job.skills)
        if not topics:
            topics = {"SystemVerilog", "UVM", "Digital Design"}

        if critical_topics is None:
            critical_topics = ["SystemVerilog", "UVM", "AXI", "CDC", "FIFO", "Assertions", "Digital Design"]

        topic_scores: dict[str, float] = {}
        mastered: list[str] = []
        weak: list[str] = []

        total_score_sum = 0.0
        for t in topics:
            was = self.career_repo.list_weak_areas(topic=t)
            active_wa = [w for w in was if not w.resolved]
            if active_wa:
                # Active weak area reduces topic readiness score
                avg_conf = sum(w.confidence for w in active_wa) / len(active_wa)
                score = round(avg_conf * 100.0, 1)
                weak.append(t)
            else:
                score = 90.0  # Base readiness for topics without unresolved weak areas
                mastered.append(t)

            topic_scores[t] = score
            total_score_sum += score

        overall = round(total_score_sum / len(topics), 1) if topics else 0.0

        # Check critical topics performance
        crit_scores = [
            topic_scores[t]
            for t in topic_scores
            if any(c.lower() in t.lower() or t.lower() in c.lower() for c in critical_topics)
        ]
        min_crit_score = min(crit_scores) if crit_scores else 90.0

        if overall >= ready_threshold and min_crit_score >= critical_topic_ready_min:
            level = "High Readiness"
            action = f"Candidate is well-prepared (Overall: {overall}%, Min Critical Topic: {min_crit_score}%). Conduct final pre-interview review."
        elif overall < borderline_threshold or min_crit_score < critical_topic_fail_min:
            level = "Needs Preparation"
            action = (
                f"Candidate requires focused study (Overall: {overall}%, Min Critical Topic: {min_crit_score}% < {critical_topic_fail_min}% threshold). "
                f"Execute targeted remediation drills before interviewing."
            )
        else:
            level = "Moderate Readiness"
            action = f"Candidate is borderline (Overall: {overall}%, Min Critical Topic: {min_crit_score}%). Review identified weak areas and complete remediation."

        return ReadinessAssessment(
            job_id=job_id,
            company=job.company,
            title=job.title,
            overall_readiness_score=overall,
            readiness_level=level,
            mastered_topics=mastered,
            weak_topics=weak,
            topic_scores=topic_scores,
            recommended_action=action,
            generated_at=now_iso,
        )

    # -------------------------------------------------------------------------
    # Preparation Scheduling & Approval Gates
    # -------------------------------------------------------------------------
    def generate_preparation_schedule(
        self, job_id: int, target_interview_date: str, days_available: int = 7
    ) -> PreparationSchedule:
        """
        Generate a multi-day preparation schedule with explicit user approval gates.
        Scheduling/email/calendar actions remain in unapproved state until confirmed by user.
        """
        job = self.job_repo.get_normalized_job(job_id)
        if not job:
            raise ValueError(f"Job id {job_id} not found.")

        now_iso = datetime.now(UTC).isoformat()
        today = datetime.now(UTC).date()
        target_date = datetime.fromisoformat(target_interview_date).date()
        days_span = max(1, (target_date - today).days)

        active_weak_areas = self.career_repo.list_weak_areas(resolved=False)
        weak_topics = [w.topic for w in active_weak_areas] or ["SystemVerilog OOP", "UVM Phases"]

        milestones: list[ScheduleMilestone] = []

        # Day 1: Foundation & Weak Area Study
        milestones.append(
            ScheduleMilestone(
                day_offset=0,
                date=(today).isoformat(),
                title=f"Core Study: {', '.join(weak_topics[:2])}",
                topics=weak_topics[:2],
                action_type="study_review",
                estimated_minutes=45,
                requires_user_approval=True,
                approved=False,
            )
        )

        # Day 2: Timed Mock Drill
        milestones.append(
            ScheduleMilestone(
                day_offset=1,
                date=(today + timedelta(days=1)).isoformat(),
                title=f"Timed Mock Test: {job.company} Role Focus",
                topics=job.skills[:3] if job.skills else ["SystemVerilog", "UVM"],
                action_type="timed_mock",
                estimated_minutes=45,
                requires_user_approval=True,
                approved=False,
            )
        )

        # Day 3: Remediation Test on Mistakes
        milestones.append(
            ScheduleMilestone(
                day_offset=2,
                date=(today + timedelta(days=2)).isoformat(),
                title="Remediation Test: Review Missed Concepts",
                topics=weak_topics[:3],
                action_type="remediation",
                estimated_minutes=30,
                requires_user_approval=True,
                approved=False,
            )
        )

        # Final Day (Pre-Interview): Final Comprehensive Drill
        final_offset = max(3, days_span - 1)
        milestones.append(
            ScheduleMilestone(
                day_offset=final_offset,
                date=(today + timedelta(days=final_offset)).isoformat(),
                title=f"Final Pre-Interview Assessment: {job.title}",
                topics=job.skills,
                action_type="final_pre_interview",
                estimated_minutes=60,
                requires_user_approval=True,
                approved=False,
            )
        )

        raw_milestones = [m.model_dump() for m in milestones]
        query = """
        INSERT INTO preparation_schedules (job_id, company, title, target_interview_date, milestones, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """
        cursor = self.conn.execute(
            query,
            (
                job_id,
                job.company,
                job.title,
                target_interview_date,
                json.dumps(raw_milestones),
                now_iso,
            ),
        )
        self.conn.commit()

        return PreparationSchedule(
            id=cursor.lastrowid,
            job_id=job_id,
            company=job.company,
            title=job.title,
            target_interview_date=target_interview_date,
            milestones=milestones,
            created_at=now_iso,
        )

    def approve_schedule_milestone(
        self, schedule_id: int, milestone_index: int
    ) -> ScheduleMilestone:
        """Explicit candidate approval for a preparation schedule milestone."""
        cursor = self.conn.execute(
            "SELECT * FROM preparation_schedules WHERE id = ?", (schedule_id,)
        )
        row = cursor.fetchone()
        if not row:
            raise ValueError(f"Preparation schedule #{schedule_id} not found.")

        raw_milestones = json.loads(row["milestones"])
        if milestone_index < 0 or milestone_index >= len(raw_milestones):
            raise IndexError(f"Milestone index {milestone_index} out of range.")

        raw_milestones[milestone_index]["approved"] = True

        self.conn.execute(
            "UPDATE preparation_schedules SET milestones = ? WHERE id = ?",
            (json.dumps(raw_milestones), schedule_id),
        )
        self.conn.commit()
        return ScheduleMilestone.model_validate(raw_milestones[milestone_index])
