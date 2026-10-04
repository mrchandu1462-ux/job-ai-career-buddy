"""Interactive learning mode for structured VLSI topic study, practice drills, and confidence updates."""

from datetime import UTC, datetime

from pydantic import BaseModel, ConfigDict, Field

from app.career.repository import CareerRepository
from app.db.models import InterviewQuestion, PreparationSession, WeakArea


class TopicCurriculum(BaseModel):
    """Structured curriculum for a specific VLSI/DV technical topic."""

    model_config = ConfigDict(extra="forbid")

    topic: str
    concept_summary: str
    key_subtopics: list[str] = Field(default_factory=list)
    common_interview_questions: list[str] = Field(default_factory=list)
    verified_knowledge_concepts: list[str] = Field(default_factory=list)
    active_weak_areas: list[WeakArea] = Field(default_factory=list)
    previous_mistakes: list[InterviewQuestion] = Field(default_factory=list)
    practice_questions: list[InterviewQuestion] = Field(default_factory=list)


class PracticeEvaluationResult(BaseModel):
    """Evaluation of a practice answer attempted during study mode."""

    model_config = ConfigDict(extra="forbid")

    question_id: int
    topic: str
    user_answer: str
    expected_answer: str
    was_correct: bool
    feedback: str
    previous_confidence: float
    updated_confidence: float
    resolved: bool


# Built-in structured subtopics for core DV / VLSI concepts
CURATED_TOPIC_SUBTOPICS: dict[str, list[str]] = {
    "Async FIFO": [
        "Dual-clock FIFO architecture",
        "Binary to Gray code conversion",
        "2-flip-flop synchronizer chain",
        "CDC pointer synchronization",
        "FIFO Full condition detection",
        "FIFO Empty condition detection",
        "Pointer wrap-around & MSB checking",
        "Metastability mitigation & MTBF",
        "SVA assertions for overflow/underflow",
    ],
    "UVM": [
        "UVM Testbench hierarchy",
        "Phase execution order (build, connect, run, extract, check, report)",
        "Component vs Object (`uvm_component` vs `uvm_sequence_item`)",
        "Factory overrides (`set_type_override_by_type`)",
        "Configuration Database (`uvm_config_db`)",
        "TLM analysis ports and FIFOs",
        "Virtual sequences and virtual sequencers",
        "UVM RAL (Register Abstraction Layer) architecture",
        "Objections and test termination mechanism",
    ],
    "SystemVerilog OOP": [
        "Classes and handles vs objects",
        "Encapsulation (local vs protected vs public)",
        "Inheritance and polymorphism (`super`, `virtual methods`)",
        "Abstract classes and pure virtual methods",
        "Shallow copy vs Deep copy (`new()` vs custom copy)",
        "Parametrized classes",
        "Static class members and lifetime",
        "Memory management and garbage collection",
    ],
    "SystemVerilog Assertions": [
        "Immediate vs Concurrent assertions",
        "Assertion clocking and preponed sample region",
        "Sequences and Properties",
        "Implication operators (`|->` overlapping vs `|=>` non-overlapping)",
        "Consecutive repetition `[*n]`, non-consecutive `[=n]`, goto `[->n]`",
        "Built-in functions (`$rose`, `$fell`, `$stable`, `$past`, `$onehot`)",
        "Multi-clock assertions and clock domain crossing pitfalls",
        "Cover properties and Vacuous pass detection",
    ],
    "AXI Protocol": [
        "5 independent AXI4 channels (AW, W, B, AR, R)",
        "VALID / READY 2-way handshake rules",
        "Burst types (FIXED, INCR, WRAP)",
        "Burst length, size, and address calculation",
        "Out-of-order and interleaved transaction IDs",
        "Write response dependencies and error codes (OKAY, EXOKAY, SLVERR, DECERR)",
        "Exclusive access and locked transactions",
        "AXI Lite vs AXI Stream vs AXI4 Full differences",
    ],
    "Clock Domain Crossing": [
        "Metastability fundamentals and MTBF equations",
        "Multi-flop synchronizers (2-FF and 3-FF)",
        "Fast-to-slow clock data loss prevention (pulse stretchers)",
        "Control path vs Data path synchronization",
        "Mux synchronizers and Handshake synchronizers",
        "Gray code synchronization for multi-bit buses",
        "Reconvergence hazards and glitch protection",
        "Static CDC analysis and waiver rules",
    ],
    "Constrained Random Verification": [
        "Random variables (`rand` vs `randc`)",
        "Constraint distribution (`dist { ... }`)",
        "Conditional constraints (`if-else` and `->`)",
        "Ordering constraints (`solve x before y`)",
        "Inline constraints (`randomize() with { ... }`)",
        "Disabling constraints (`constraint_mode(0)`) and variables (`rand_mode(0)`)",
        "Soft constraints (`soft` keyword) and conflict resolution",
    ],
    "Digital Design": [
        "Setup time, Hold time, and Clock-to-Q delay",
        "Timing violation remediation (setup slack vs hold slack)",
        "Mealy vs Moore Finite State Machine design",
        "Blocking (`=`) vs Non-blocking (`<=`) assignment rules",
        "Clock gating architecture and latch-based gating",
        "Reset methodologies (Asynchronous assert / Synchronous deassert)",
        "Static Timing Analysis (STA) path classification",
    ],
}


class LearningModeService:
    """Service providing interactive study modules, practice evaluations, and confidence tracking."""

    def __init__(self, career_repo: CareerRepository):
        self.career_repo = career_repo

    def get_topic_curriculum(self, topic: str) -> TopicCurriculum:
        """Synthesize a complete study curriculum for a topic from verified knowledge, weak areas, and history."""
        # Find matching subtopics
        subtopics: list[str] = []
        for curated_t, subs in CURATED_TOPIC_SUBTOPICS.items():
            if curated_t.lower() in topic.lower() or topic.lower() in curated_t.lower():
                subtopics.extend(subs)
                break
        if not subtopics:
            subtopics = [f"{topic} Fundamentals", f"{topic} Architecture", f"{topic} Verification & Debugging"]

        # 1. Fetch verified knowledge items
        knowledge_items = self.career_repo.get_knowledge_items_by_topic(topic)
        verified_concepts = [k.concept for k in knowledge_items if k.verified]
        concept_summary = (
            knowledge_items[0].explanation
            if knowledge_items
            else f"Comprehensive study and verification drill for {topic}."
        )

        # 2. Fetch active weak areas
        active_weak_areas = self.career_repo.list_weak_areas(resolved=False, topic=topic)

        # 3. Fetch past questions on this topic
        topic_questions = self.career_repo.get_questions_by_topic(topic)
        mistakes = [q for q in topic_questions if q.was_correct is False]
        common_q_texts = [q.question for q in topic_questions if q.times_asked >= 2] or [
            q.question for q in topic_questions[:3]
        ]

        return TopicCurriculum(
            topic=topic,
            concept_summary=concept_summary,
            key_subtopics=subtopics,
            common_interview_questions=common_q_texts,
            verified_knowledge_concepts=verified_concepts,
            active_weak_areas=active_weak_areas,
            previous_mistakes=mistakes,
            practice_questions=topic_questions[:5],
        )

    def evaluate_practice_answer(
        self,
        question_id: int,
        user_answer: str,
        was_correct: bool,
        feedback: str | None = None,
    ) -> PracticeEvaluationResult:
        """
        Evaluate a candidate practice response and adapt candidate weak-area confidence.
        Uses multi-observation confidence adjustment (requires multiple positive reviews to resolve).
        """
        q = self.career_repo.get_interview_question(question_id)
        if not q:
            raise ValueError(f"Question #{question_id} not found.")

        topic = q.topic
        expected = q.expected_answer or "Reference expected verification behavior."
        eval_feedback = feedback or (
            "Well explained! Meets verification requirements."
            if was_correct
            else f"Review recommended. Key concept: {expected}"
        )

        # Look up existing weak area for topic
        existing_was = self.career_repo.list_weak_areas(topic=topic)
        prev_conf = 0.5
        updated_conf = 0.5
        resolved = False

        if existing_was:
            wa = existing_was[0]
            prev_conf = wa.confidence
            if was_correct:
                # Multi-observation step: +0.15 on success
                updated_conf = min(1.0, round(wa.confidence + 0.15, 2))
                resolved = updated_conf >= 0.85 and wa.review_count >= 2
            else:
                # Penalty on failure: -0.20
                updated_conf = max(0.1, round(wa.confidence - 0.20, 2))
                resolved = False

            self.career_repo.update_weak_area_review(
                weak_area_id=wa.id,
                new_confidence=updated_conf,
                resolved=resolved,
            )
        else:
            if not was_correct:
                prev_conf = 0.5
                updated_conf = 0.3
                self.career_repo.insert_weak_area(
                    WeakArea(
                        topic=topic,
                        description=f"Identified gap in practice question: '{q.question}'",
                        evidence_source="Interactive Learning Mode Practice",
                        severity="medium",
                        confidence=updated_conf,
                        created_at=datetime.now(UTC).isoformat(),
                    )
                )

        return PracticeEvaluationResult(
            question_id=question_id,
            topic=topic,
            user_answer=user_answer,
            expected_answer=expected,
            was_correct=was_correct,
            feedback=eval_feedback,
            previous_confidence=prev_conf,
            updated_confidence=updated_conf,
            resolved=resolved,
        )

    def log_learning_session(
        self,
        job_id: int | None,
        topics: list[str],
        questions_attempted: int,
        summary: str,
        notes: str | None = None,
    ) -> int:
        """Record completed study session log in SQLite."""
        session = PreparationSession(
            job_id=job_id,
            date=datetime.now(UTC).date().isoformat(),
            topics=topics,
            questions_attempted=questions_attempted,
            performance_summary=summary,
            notes=notes,
            created_at=datetime.now(UTC).isoformat(),
        )
        return self.career_repo.insert_prep_session(session)
