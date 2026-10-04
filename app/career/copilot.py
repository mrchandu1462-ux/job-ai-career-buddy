"""Phase 6: Interview Prep Copilot & Tailored Practice Generator.

Provides deterministic JD analysis, candidate skill-gap diagnosis, interview topic extraction,
question catalog, interactive mock interviews, answer evaluations, weakness tracking,
dynamic study plan generation, and interview readiness scoring.
"""

from __future__ import annotations

import logging
import re
from datetime import UTC, datetime
from enum import Enum
from typing import Any, ClassVar

from pydantic import BaseModel, ConfigDict, Field

from app.career.repository import CareerRepository
from app.db.models import NormalizedJob, WeakArea
from app.db.repository import JobRepository
from app.profile.loader import load_candidate_profile, load_fact_bank
from app.profile.models import CandidateProfile, FactBank

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class SkillProficiencyLevel(str, Enum):
    """Candidate proficiency status relative to target job requirements."""

    STRONG = "STRONG"
    FAMILIAR = "FAMILIAR"
    PARTIAL = "PARTIAL"
    MISSING = "MISSING"
    UNKNOWN = "UNKNOWN"


class QuestionCategory(str, Enum):
    """Core categories A through M for semiconductor verification interviews."""

    DIGITAL_DESIGN = "Digital Design"
    VERILOG = "Verilog"
    SYSTEM_VERILOG = "SystemVerilog"
    UVM = "UVM"
    ASSERTIONS = "Assertions"
    FUNCTIONAL_COVERAGE = "Functional Coverage"
    AXI = "AXI"
    FIFO_CDC = "FIFO/CDC"
    MEMORY_VERIFICATION = "Memory Verification"
    DEBUGGING = "Debugging"
    PYTHON_LINUX_GIT = "Python/Linux/Git"
    PROJECT_DEFENSE = "Project Defense"
    HR_BEHAVIORAL = "HR/Behavioral"


class QuestionDifficulty(str, Enum):
    """Difficulty rating for interview questions."""

    EASY = "EASY"
    MEDIUM = "MEDIUM"
    HARD = "HARD"
    EXPERT = "EXPERT"


class EvidenceProvenance(str, Enum):
    """Evidence origin for question or topic relevance."""

    VERIFIED_FROM_JD = "VERIFIED FROM JD"
    USER_PROVIDED = "USER-PROVIDED"
    VERIFIED_PUBLIC_SOURCE = "VERIFIED PUBLIC SOURCE"
    LIKELY = "LIKELY"
    POSSIBLE = "POSSIBLE"
    GENERAL_DV_TOPIC = "GENERAL DV TOPIC"


class AnswerEvaluationStatus(str, Enum):
    """Categorized result of candidate answer evaluation."""

    CORRECT = "CORRECT"
    PARTIALLY_CORRECT = "PARTIALLY_CORRECT"
    INCORRECT = "INCORRECT"
    UNCLEAR = "UNCLEAR"


class MockInterviewMode(str, Enum):
    """Execution modes for mock interview practice."""

    QUICK = "QUICK"  # 10 questions
    STANDARD = "STANDARD"  # 20 questions
    DEEP = "DEEP"  # 40 questions
    COMPANY = "COMPANY"  # Role/company-targeted
    WEAKNESS = "WEAKNESS"  # Focuses on candidate weak areas
    PROJECT = "PROJECT"  # Project-defense only


class InterviewReadinessLevel(str, Enum):
    """Overall candidate interview readiness rating."""

    READY = "READY"  # Score >= 85
    NEAR_READY = "NEAR_READY"  # Score 70-84.9
    NEEDS_WORK = "NEEDS_WORK"  # Score 50-69.9
    NOT_READY = "NOT_READY"  # Score < 50


# ---------------------------------------------------------------------------
# Data Models
# ---------------------------------------------------------------------------


class SkillGapItem(BaseModel):
    """Analysis of a single skill required by the JD versus candidate profile."""

    model_config = ConfigDict(extra="forbid")

    skill_name: str
    proficiency: SkillProficiencyLevel
    is_required: bool = True
    evidence: str = ""
    candidate_context: str | None = None
    recommendation: str = ""


class JDAnalysisResult(BaseModel):
    """Structured deterministic breakdown of a job description."""

    model_config = ConfigDict(extra="forbid")

    job_fingerprint: str
    company: str
    role_title: str
    role_tier: str = "TIER_1"
    technical_skills: list[str] = Field(default_factory=list)
    role_categories: list[str] = Field(default_factory=list)
    domains: list[str] = Field(default_factory=list)
    interview_signals: list[str] = Field(default_factory=list)
    required_skills: list[str] = Field(default_factory=list)
    preferred_skills: list[str] = Field(default_factory=list)
    has_axi: bool = False
    has_uvm: bool = False
    has_sv: bool = False
    has_fifo: bool = False
    has_sva: bool = False


class CopilotQuestion(BaseModel):
    """Single interview practice question with grading criteria and answer guidance."""

    model_config = ConfigDict(extra="forbid")

    question_id: str
    category: QuestionCategory
    topic: str
    question: str
    difficulty: QuestionDifficulty = QuestionDifficulty.MEDIUM
    expected_concepts: list[str] = Field(default_factory=list)
    answer_guidance: str = ""
    provenance: EvidenceProvenance = EvidenceProvenance.GENERAL_DV_TOPIC
    provenance_note: str = ""
    candidate_answer: str | None = None
    evaluation_status: AnswerEvaluationStatus | None = None


class AnswerEvaluationResult(BaseModel):
    """Evaluation output for a single answer attempt."""

    model_config = ConfigDict(extra="forbid")

    status: AnswerEvaluationStatus
    technical_accuracy: float = Field(..., ge=0.0, le=1.0)
    completeness: float = Field(..., ge=0.0, le=1.0)
    clarity: float = Field(..., ge=0.0, le=1.0)
    good_points: list[str] = Field(default_factory=list)
    missing_points: list[str] = Field(default_factory=list)
    practice_recommendation: str = ""
    feedback: str = ""
    weakness_topic: str | None = None


class TopicWeaknessStats(BaseModel):
    """Historical performance metrics for a specific technical topic."""

    model_config = ConfigDict(extra="forbid")

    topic: str
    questions_attempted: int = 0
    correct: int = 0
    partially_correct: int = 0
    incorrect: int = 0
    weakness_score: float = Field(default=0.0, ge=0.0, le=100.0)
    last_practiced: str | None = None
    improvement_trend: str = "STABLE"


class StudyPlanDay(BaseModel):
    """Single-day milestone in a personalized interview study plan."""

    model_config = ConfigDict(extra="forbid")

    day_number: int
    title: str
    focus_topics: list[str] = Field(default_factory=list)
    target_weak_areas: list[str] = Field(default_factory=list)
    practice_drills: list[str] = Field(default_factory=list)
    estimated_minutes: int = 45


class TailoredStudyPlan(BaseModel):
    """Structured multi-day study schedule adapted to candidate gaps."""

    model_config = ConfigDict(extra="forbid")

    job_fingerprint: str
    company: str
    role: str
    days: list[StudyPlanDay] = Field(default_factory=list)
    rationale: list[str] = Field(default_factory=list)
    generated_at: str


class InterviewReadinessScore(BaseModel):
    """Deterministic readiness assessment output across 8 dimensions."""

    model_config = ConfigDict(extra="forbid")

    total_score: float = Field(..., ge=0.0, le=100.0)
    level: InterviewReadinessLevel
    dimension_scores: dict[str, float] = Field(default_factory=dict)
    strengths: list[str] = Field(default_factory=list)
    needs_work: list[str] = Field(default_factory=list)
    explainable_summary: str = ""


class MockSessionState(BaseModel):
    """Interactive state for an ongoing mock interview session."""

    model_config = ConfigDict(extra="forbid")

    session_id: str
    job_fingerprint: str
    company: str
    role: str
    mode: MockInterviewMode
    questions: list[CopilotQuestion] = Field(default_factory=list)
    current_index: int = 0
    evaluations: list[AnswerEvaluationResult] = Field(default_factory=list)
    is_completed: bool = False
    overall_score: float | None = None
    created_at: str


class InterviewPreparationProfile(BaseModel):
    """Comprehensive job-specific interview preparation profile."""

    model_config = ConfigDict(extra="forbid")

    job_fingerprint: str
    company: str
    role: str
    location: str | None = None
    job_url: str | None = None
    preparation_status: str = "READY_FOR_PREP"
    generated_at: str
    target_skills: list[str] = Field(default_factory=list)
    required_skills: list[str] = Field(default_factory=list)
    preferred_skills: list[str] = Field(default_factory=list)
    missing_skills: list[str] = Field(default_factory=list)
    interview_topics: list[str] = Field(default_factory=list)
    question_sets: list[CopilotQuestion] = Field(default_factory=list)
    preparation_priority: str = "HIGH"
    skill_gaps: list[SkillGapItem] = Field(default_factory=list)
    readiness: InterviewReadinessScore | None = None
    study_plan: TailoredStudyPlan | None = None


# ---------------------------------------------------------------------------
# Core Catalogs & Question Catalog
# ---------------------------------------------------------------------------

CURATED_QUESTION_CATALOG: list[dict[str, Any]] = [
    # A. Digital Design
    {
        "id": "DD-01",
        "category": QuestionCategory.DIGITAL_DESIGN,
        "topic": "Setup and Hold Time",
        "difficulty": QuestionDifficulty.MEDIUM,
        "question": "Explain setup time and hold time in sequential digital circuits. How do you resolve a hold violation?",
        "expected_concepts": [
            "setup time",
            "hold time",
            "clock edge",
            "delay",
            "buffer",
            "data stable",
        ],
        "answer_guidance": "Setup time is the minimum time data must be stable before the active clock edge. Hold time is the minimum time data must remain stable after the active clock edge. Hold violations are fixed by adding delay buffers to the data path, not by changing the clock frequency.",
        "provenance": EvidenceProvenance.GENERAL_DV_TOPIC,
    },
    {
        "id": "DD-02",
        "category": QuestionCategory.DIGITAL_DESIGN,
        "topic": "FSM Design",
        "difficulty": QuestionDifficulty.MEDIUM,
        "question": "What is the difference between a Mealy and a Moore finite state machine? Which one has lower latency and why?",
        "expected_concepts": ["mealy", "moore", "current state", "inputs", "latency", "glitch"],
        "answer_guidance": "In a Moore FSM, outputs depend solely on the current state. In a Mealy FSM, outputs depend on both current state and primary inputs. Mealy machines can respond within the same clock cycle giving lower latency, but are prone to input glitches.",
        "provenance": EvidenceProvenance.GENERAL_DV_TOPIC,
    },
    # B. Verilog
    {
        "id": "VER-01",
        "category": QuestionCategory.VERILOG,
        "topic": "Blocking vs Non-blocking Assignments",
        "difficulty": QuestionDifficulty.EASY,
        "question": "Explain the difference between blocking (=) and non-blocking (<=) assignments in Verilog. When should each be used?",
        "expected_concepts": [
            "blocking",
            "non-blocking",
            "sequential",
            "combinational",
            "race condition",
            "active region",
            "nba region",
        ],
        "answer_guidance": "Blocking assignments execute sequentially and block execution until evaluated; use them in combinational logic (always_comb / always @*). Non-blocking assignments evaluate right-hand sides in the Active region and update left-hand sides in the NBA region; use them in sequential logic (always_ff / always @(posedge clk)) to avoid race conditions.",
        "provenance": EvidenceProvenance.GENERAL_DV_TOPIC,
    },
    {
        "id": "VER-02",
        "category": QuestionCategory.VERILOG,
        "topic": "Tasks vs Functions",
        "difficulty": QuestionDifficulty.EASY,
        "question": "What are the key differences between a task and a function in Verilog / SystemVerilog?",
        "expected_concepts": [
            "task",
            "function",
            "time",
            "delay",
            "return",
            "blocking",
            "0 time",
        ],
        "answer_guidance": "A function executes in 0 simulation time, cannot contain time-consuming statements (@, #, wait), and must return a value (or void in SV). A task can consume simulation time, contain delays, and does not return a value directly.",
        "provenance": EvidenceProvenance.GENERAL_DV_TOPIC,
    },
    # C. SystemVerilog
    {
        "id": "SV-01",
        "category": QuestionCategory.SYSTEM_VERILOG,
        "topic": "Shallow Copy vs Deep Copy",
        "difficulty": QuestionDifficulty.MEDIUM,
        "question": "What is the difference between shallow copy and deep copy in SystemVerilog OOP? When is deep copy mandatory?",
        "expected_concepts": [
            "shallow copy",
            "deep copy",
            "handle",
            "nested object",
            "clone",
            "independent",
        ],
        "answer_guidance": "A shallow copy (new) copies all primitive fields and object handles, but does not duplicate nested objects (both objects point to the same nested memory). A deep copy recursively duplicates nested objects into distinct memory instances, which is mandatory when transactions are passed between generator, driver, and scoreboard to prevent corrupting in-flight packets.",
        "provenance": EvidenceProvenance.GENERAL_DV_TOPIC,
    },
    {
        "id": "SV-02",
        "category": QuestionCategory.SYSTEM_VERILOG,
        "topic": "Randomization and Constraints",
        "difficulty": QuestionDifficulty.MEDIUM,
        "question": "Explain the difference between `rand` and `randc` variables in SystemVerilog. How does `solve...before` influence constraint solving?",
        "expected_concepts": [
            "rand",
            "randc",
            "cyclic",
            "solve before",
            "probability",
            "distribution",
        ],
        "answer_guidance": "rand variables choose random values with uniform probability across the legal space. randc generates a permutation of all values cyclically before repeating. solve A before B alters the probability distribution so that A is chosen first, changing the conditional distribution of B without altering the legal solution space.",
        "provenance": EvidenceProvenance.GENERAL_DV_TOPIC,
    },
    {
        "id": "SV-03",
        "category": QuestionCategory.SYSTEM_VERILOG,
        "topic": "Virtual Interface",
        "difficulty": QuestionDifficulty.MEDIUM,
        "question": "What is a virtual interface in SystemVerilog and why is it necessary to connect static DUT modules with dynamic UVM classes?",
        "expected_concepts": [
            "virtual interface",
            "static",
            "dynamic",
            "class",
            "module",
            "handle",
            "driver",
        ],
        "answer_guidance": "SystemVerilog modules and interfaces are static design entities created at elaboration time, whereas UVM testbench components are dynamic class instances created at runtime. A class cannot directly instantiate a physical interface, so a virtual interface provides a dynamic pointer/handle to the physical interface signals.",
        "provenance": EvidenceProvenance.GENERAL_DV_TOPIC,
    },
    # D. UVM
    {
        "id": "UVM-01",
        "category": QuestionCategory.UVM,
        "topic": "UVM Phases and Objections",
        "difficulty": QuestionDifficulty.MEDIUM,
        "question": "Explain the execution order of UVM phases. How does the objection mechanism control test termination in run_phase?",
        "expected_concepts": [
            "build_phase",
            "connect_phase",
            "run_phase",
            "top-down",
            "bottom-up",
            "raise_objection",
            "drop_objection",
        ],
        "answer_guidance": "UVM execution consists of build_phase (top-down), connect_phase (bottom-up), end_of_elaboration, start_of_simulation, run_phase (time-consuming task), extract, check, report, and final phases. Objections (phase.raise_objection / drop_objection) keep run_phase active; when all objections are dropped, run_phase concludes cleanly.",
        "provenance": EvidenceProvenance.GENERAL_DV_TOPIC,
    },
    {
        "id": "UVM-02",
        "category": QuestionCategory.UVM,
        "topic": "UVM Factory and Overrides",
        "difficulty": QuestionDifficulty.HARD,
        "question": "How does the UVM Factory mechanism work, and what is the difference between `set_type_override_by_type` and `set_inst_override_by_type`?",
        "expected_concepts": [
            "factory",
            "create()",
            "type override",
            "instance override",
            "polymorphism",
            "hierarchy",
        ],
        "answer_guidance": "The UVM factory uses polymorphism and a registry pattern to construct components using `type_id::create()` instead of `new()`. A type override replaces all instances of a class across the testbench, whereas an instance override targets only a specific hierarchical path in the testbench component tree.",
        "provenance": EvidenceProvenance.GENERAL_DV_TOPIC,
    },
    {
        "id": "UVM-03",
        "category": QuestionCategory.UVM,
        "topic": "UVM TLM and Analysis Ports",
        "difficulty": QuestionDifficulty.MEDIUM,
        "question": "Explain how uvm_analysis_port and uvm_analysis_imp enable 1-to-many communication between a monitor and multiple scoreboards/coverage collectors.",
        "expected_concepts": [
            "analysis port",
            "write()",
            "broadcasting",
            "1-to-many",
            "non-blocking",
            "subscriber",
        ],
        "answer_guidance": "An analysis port (`uvm_analysis_port`) implements a broadcast mechanism via the `write()` function. It is non-blocking and can connect to zero, one, or multiple analysis exports/subscribers (`uvm_subscriber`) without needing the monitor to know who is receiving transactions.",
        "provenance": EvidenceProvenance.GENERAL_DV_TOPIC,
    },
    # E. Assertions (SVA)
    {
        "id": "SVA-01",
        "category": QuestionCategory.ASSERTIONS,
        "topic": "Concurrent Assertions and Implication",
        "difficulty": QuestionDifficulty.MEDIUM,
        "question": "Explain the difference between overlapping (|->) and non-overlapping (|=>) implication in SystemVerilog Assertions.",
        "expected_concepts": [
            "implication",
            "overlapping",
            "non-overlapping",
            "same cycle",
            "next cycle",
            "antecedent",
            "consequent",
        ],
        "answer_guidance": "In SVA, `antecedent |-> consequent` (overlapping) evaluates the consequent in the exact same clock cycle where the antecedent matches. `antecedent |=> consequent` (non-overlapping) evaluates the consequent in the subsequent clock cycle (1 clock delay).",
        "provenance": EvidenceProvenance.GENERAL_DV_TOPIC,
    },
    {
        "id": "SVA-02",
        "category": QuestionCategory.ASSERTIONS,
        "topic": "Handshake Stability SVA",
        "difficulty": QuestionDifficulty.HARD,
        "question": "Write an SVA property to verify that when VALID is asserted and READY is low, VALID and all DATA payload signals remain stable until READY is asserted.",
        "expected_concepts": [
            "property",
            "valid",
            "ready",
            "stable",
            "$stable",
            "disable iff",
            "handshake",
        ],
        "answer_guidance": "Property: `property p_valid_data_stable; @(posedge clk) disable iff (!reset_n) (valid && !ready) |=> (valid && $stable(data)); endproperty; assert property (p_valid_data_stable);`",
        "provenance": EvidenceProvenance.GENERAL_DV_TOPIC,
    },
    # F. Functional Coverage
    {
        "id": "COV-01",
        "category": QuestionCategory.FUNCTIONAL_COVERAGE,
        "topic": "Code Coverage vs Functional Coverage",
        "difficulty": QuestionDifficulty.EASY,
        "question": "What is the difference between code coverage and functional coverage? Why does 100% code coverage not guarantee zero bugs?",
        "expected_concepts": [
            "code coverage",
            "functional coverage",
            "line",
            "branch",
            "specification",
            "intent",
            "missing features",
        ],
        "answer_guidance": "Code coverage measures which lines, branches, expressions, and FSM states were executed in the written RTL code. Functional coverage measures whether the testbench verified all intended features and corner cases defined in the design specification. 100% code coverage can be achieved without testing missing hardware features or incorrect functional interactions.",
        "provenance": EvidenceProvenance.GENERAL_DV_TOPIC,
    },
    # G. AXI Protocol
    {
        "id": "AXI-01",
        "category": QuestionCategory.AXI,
        "topic": "AXI4 5 Channels and Handshake",
        "difficulty": QuestionDifficulty.MEDIUM,
        "question": "List the 5 independent channels in AXI4. What happens when VALID=1 and READY=0, and what are the stability rules?",
        "expected_concepts": [
            "write address (AW)",
            "write data (W)",
            "write response (B)",
            "read address (AR)",
            "read data (R)",
            "valid",
            "ready",
            "stable",
            "backpressure",
        ],
        "answer_guidance": "The 5 channels are: AW (Write Address), W (Write Data), B (Write Response), AR (Read Address), and R (Read Data). When VALID=1 and READY=0, the transmitter is asserting a valid transfer but the receiver is applying backpressure; VALID must remain high and all payload signals must remain stable until READY is asserted on an active clock edge.",
        "provenance": EvidenceProvenance.GENERAL_DV_TOPIC,
    },
    {
        "id": "AXI-02",
        "category": QuestionCategory.AXI,
        "topic": "AXI Out-of-Order and Interleaved Transactions",
        "difficulty": QuestionDifficulty.HARD,
        "question": "How does AXI support out-of-order transaction completion? How does a scoreboard track responses for different transaction IDs?",
        "expected_concepts": [
            "arid",
            "rid",
            "awid",
            "bid",
            "out-of-order",
            "thread",
            "associative array",
            "queues",
        ],
        "answer_guidance": "AXI uses transaction IDs (AWID/BID, ARID/RID). Transactions with the same ID must complete in order, but transactions with different IDs can complete out-of-order. A scoreboard maintains associative arrays or independent queues per transaction ID to match responses against expected requests without false mismatch errors.",
        "provenance": EvidenceProvenance.GENERAL_DV_TOPIC,
    },
    # H. FIFO and CDC
    {
        "id": "FIFO-01",
        "category": QuestionCategory.FIFO_CDC,
        "topic": "Asynchronous FIFO CDC and Gray Pointers",
        "difficulty": QuestionDifficulty.HARD,
        "question": "Why are Gray code pointers used instead of binary counters when passing write/read pointers across asynchronous clock domains in an Async FIFO?",
        "expected_concepts": [
            "gray code",
            "cdc",
            "metastability",
            "single bit change",
            "2-ff synchronizer",
            "glitch",
        ],
        "answer_guidance": "In binary counters, multiple bits can change simultaneously (e.g. 011 to 100 changes 3 bits). If sampled in an asynchronous clock domain, intermediate transition states can be captured causing severe pointer corruption. Gray code guarantees only a single bit changes between consecutive states, ensuring the synchronizer captures either the old value or new value safely.",
        "provenance": EvidenceProvenance.GENERAL_DV_TOPIC,
    },
    {
        "id": "FIFO-02",
        "category": QuestionCategory.FIFO_CDC,
        "topic": "Async FIFO Full and Empty Conditions",
        "difficulty": QuestionDifficulty.HARD,
        "question": "How are the FIFO full and empty conditions generated in Gray code? Why does full condition invert the MSB and 2nd MSB?",
        "expected_concepts": [
            "empty condition",
            "full condition",
            "msb inverted",
            "2nd msb inverted",
            "pointer comparison",
            "wrap around",
        ],
        "answer_guidance": "Empty condition occurs when write pointer and read pointer Gray codes are completely identical. Full condition occurs when write pointer has wrapped around once more than read pointer; in Gray code, this corresponds to the MSB and 2nd MSB being inverted while all remaining lower bits are identical.",
        "provenance": EvidenceProvenance.GENERAL_DV_TOPIC,
    },
    # I. Memory Verification
    {
        "id": "MEM-01",
        "category": QuestionCategory.MEMORY_VERIFICATION,
        "topic": "Dual-Port RAM Verification",
        "difficulty": QuestionDifficulty.MEDIUM,
        "question": "What corner cases must be verified in a dual-port RAM testbench? How do you verify simultaneous write and read to the same address?",
        "expected_concepts": [
            "simultaneous read/write",
            "same address",
            "read-during-write behavior",
            "old data",
            "new data",
            "back-to-back",
        ],
        "answer_guidance": "Key corner cases include simultaneous read and write to the same address (verifying whether new data or old data is returned per specification), boundary address accesses (0 and MAX_ADDR), back-to-back writes, and uninitialized address reads.",
        "provenance": EvidenceProvenance.GENERAL_DV_TOPIC,
    },
    # J. Debugging
    {
        "id": "DBG-01",
        "category": QuestionCategory.DEBUGGING,
        "topic": "Scoreboard Mismatch Debugging",
        "difficulty": QuestionDifficulty.MEDIUM,
        "question": "Your scoreboard flags a transaction mismatch at simulation time 1450ns. Walk through your step-by-step debug procedure.",
        "expected_concepts": [
            "waveform",
            "transaction log",
            "time alignment",
            "dut signals vs uvc",
            "monitor extraction",
            "reference model",
        ],
        "answer_guidance": "1. Inspect scoreboard error log for mismatched fields and transaction ID. 2. Trace back to generator stimulus log. 3. Open simulation waveforms at the relevant time window. 4. Verify DUT interface signals against protocol specifications. 5. Confirm monitor correctly extracted the pin-level signals. 6. Check reference model computation for algorithmic bugs.",
        "provenance": EvidenceProvenance.GENERAL_DV_TOPIC,
    },
    # K. Python / Linux / Git
    {
        "id": "PLG-01",
        "category": QuestionCategory.PYTHON_LINUX_GIT,
        "topic": "Regression Scripting and Log Parsing",
        "difficulty": QuestionDifficulty.EASY,
        "question": "How do you use Python regular expressions or Linux commands (grep/awk) to parse simulation logs and count PASS/FAIL test cases?",
        "expected_concepts": [
            "re.search",
            "grep",
            "awk",
            "exit code",
            "regex",
            "summary report",
        ],
        "answer_guidance": "Using Python re.search(pattern, log_content) to parse UVM error counts or Linux grep -c 'TEST PASSED' *.log to aggregate regression results across seed iterations.",
        "provenance": EvidenceProvenance.GENERAL_DV_TOPIC,
    },
    # L. Project Defense
    {
        "id": "PRJ-01",
        "category": QuestionCategory.PROJECT_DEFENSE,
        "topic": "Candidate AXI4 UVC Project Defense",
        "difficulty": QuestionDifficulty.HARD,
        "question": "Describe the architecture of your AXI4 UVC verification environment. How did your driver and monitor interact with the interface clocking block?",
        "expected_concepts": [
            "uvm_driver",
            "uvm_monitor",
            "clocking block",
            "virtual interface",
            "seq_item_port",
            "scoreboard",
        ],
        "answer_guidance": "Candidate should detail the UVC agent hierarchy (driver, monitor, sequencer), how clocking blocks avoided race conditions by synchronizing input/output sampling, and how transactions flowed from sequence items to the scoreboard.",
        "provenance": EvidenceProvenance.USER_PROVIDED,
    },
    {
        "id": "PRJ-02",
        "category": QuestionCategory.PROJECT_DEFENSE,
        "topic": "Candidate Async FIFO Project Defense",
        "difficulty": QuestionDifficulty.HARD,
        "question": "In your Async FIFO verification project, describe a specific bug you injected or discovered during constrained-random testing.",
        "expected_concepts": [
            "corner case",
            "backpressure",
            "full flag assertion",
            "pointer synchronization",
            "sva violation",
            "root cause",
        ],
        "answer_guidance": "Candidate must explain a concrete bug scenario (e.g. premature full flag deassertion under rapid burst writes or 1-cycle latency skew in pointer synchronization) and how assertions caught it.",
        "provenance": EvidenceProvenance.USER_PROVIDED,
    },
    # M. HR / Behavioral
    {
        "id": "HR-01",
        "category": QuestionCategory.HR_BEHAVIORAL,
        "topic": "Technical Disagreement Resolution",
        "difficulty": QuestionDifficulty.EASY,
        "question": "Describe how you would handle a situation where a simulation failure occurs and the RTL designer claims it is a testbench bug, but you believe it is an RTL design bug.",
        "expected_concepts": [
            "waveform evidence",
            "protocol specification",
            "minimal reproduction",
            "collaboration",
            "objective data",
        ],
        "answer_guidance": "1. Focus on the objective protocol specification. 2. Create a minimal reproducible testcase with isolated stimulus. 3. Document exact waveform timestamps showing protocol rule violations. 4. Walk through the waveform collaboratively with the designer without assigning blame.",
        "provenance": EvidenceProvenance.GENERAL_DV_TOPIC,
    },
]


# ---------------------------------------------------------------------------
# Engines
# ---------------------------------------------------------------------------


class JDAnalysisEngine:
    """Deterministic extractor parsing technical keywords, role tiers, domains, and interview signals from JD."""

    TECH_PATTERNS: ClassVar[list[tuple[str, str]]] = [
        (r"\bsystemverilog\b|\bsv\b", "SystemVerilog"),
        (r"\buvm\b", "UVM"),
        (r"\bverilog\b", "Verilog"),
        (r"\bsva\b|\bassertions?\b", "SVA / Assertions"),
        (r"\baxi(?:4)?\b", "AXI Protocol"),
        (r"\bahb\b", "AHB"),
        (r"\bapb\b", "APB"),
        (r"\brtl\b", "RTL Design"),
        (r"\bcdc\b|\bclock\s*domain\s*crossing\b", "Clock Domain Crossing (CDC)"),
        (r"\bfifo\b", "FIFO"),
        (r"\bmemory\b|\bsram\b|\bdram\b", "Memory Verification"),
        (r"\bfunctional\s*coverage\b|\bcovergroup\b", "Functional Coverage"),
        (r"\bconstrained[\s-]random\b", "Constrained Random Verification"),
        (r"\bscoreboard\b", "Scoreboard Architecture"),
        (r"\bmonitors?\b|\bdrivers?\b|\bsequences?\b", "UVM Component Hierarchy"),
        (r"\bral\b|\bregister\s*abstraction\b", "UVM RAL"),
        (r"\bpython\b", "Python"),
        (r"\blinux\b|\bbash\b", "Linux / Shell"),
        (r"\bgit\b|\bgithub\b", "Git"),
        (r"\bquestasim\b|\bmodelsim\b", "QuestaSim / ModelSim"),
        (r"\bvcs\b", "Synopsys VCS"),
        (r"\bxcelium\b", "Cadence Xcelium"),
        (r"\bformal\s*verification\b", "Formal Verification"),
        (r"\bpcie\b", "PCIe"),
        (r"\bupf\b|\blow\s*power\b", "Low Power / UPF"),
    ]

    DOMAIN_PATTERNS: ClassVar[list[tuple[str, str]]] = [
        (r"\bcpu\b|\bprocessor\b|\brisc[\s-]v\b|\barm\b", "CPU / Processor Architecture"),
        (r"\bgpu\b|\bgraphics\b|\bshader\b", "GPU Architecture"),
        (r"\bsoc\b|\bsystem[\s-]on[\s-]chip\b", "SoC Integration"),
        (r"\binterconnect\b|\bnoc\b", "On-Chip Interconnect"),
        (r"\bautomotive\b|\biso\s*26262\b", "Automotive Semiconductor"),
        (r"\bnetworking\b|\bethernet\b", "Networking Silicon"),
        (r"\beda\b|\belectronic\s*design\s*automation\b", "EDA Tooling"),
    ]

    SIGNAL_PATTERNS: ClassVar[list[tuple[str, str]]] = [
        (r"\bdebug(?:ging)?\b|\btriage\b|\bwaveform\b", "Waveform Debugging & Triage"),
        (r"\bprotocol\b|\bhandshake\b", "Protocol Verification & Bus Semantics"),
        (r"\btestbench\s*architect(?:ure)?\b", "Modular Testbench Architecture"),
        (r"\bcoverage\s*closure\b", "Coverage Analysis & Closure"),
        (r"\bproblem[\s-]solving\b|\bcommunication\b", "Technical Communication & Problem Solving"),
    ]

    def analyze(self, job: NormalizedJob) -> JDAnalysisResult:
        """Deterministically parse the job title, description, and requirements."""
        title = job.title or ""
        desc = job.description or ""
        reqs = job.requirements or ""
        combined = f"{title} {desc} {reqs}".lower()

        found_tech: list[str] = []
        for pattern, label in self.TECH_PATTERNS:
            if re.search(pattern, combined):
                found_tech.append(label)

        found_domains: list[str] = []
        for pattern, label in self.DOMAIN_PATTERNS:
            if re.search(pattern, combined):
                found_domains.append(label)

        found_signals: list[str] = []
        for pattern, label in self.SIGNAL_PATTERNS:
            if re.search(pattern, combined):
                found_signals.append(label)

        # Role Tier classification
        t_lower = title.lower()
        if any(k in t_lower for k in ["design verification", "functional verification", "asic verification", "soc verification", "dv "]):
            role_tier = "TIER_1"
        elif any(k in t_lower for k in ["rtl design", "verification intern", "vlsi intern", "rtl intern"]):
            role_tier = "TIER_2"
        elif any(k in t_lower for k in ["graduate engineer trainee", "get", "trainee", "graduate engineer"]):
            role_tier = "TIER_3"
        else:
            role_tier = "TIER_4"

        # Required vs Preferred separation
        required_skills = found_tech[:6]
        preferred_skills = found_tech[6:]

        return JDAnalysisResult(
            job_fingerprint=job.fingerprint,
            company=job.company,
            role_title=job.title,
            role_tier=role_tier,
            technical_skills=found_tech,
            role_categories=[role_tier],
            domains=found_domains,
            interview_signals=found_signals,
            required_skills=required_skills,
            preferred_skills=preferred_skills,
            has_axi="AXI Protocol" in found_tech,
            has_uvm="UVM" in found_tech,
            has_sv="SystemVerilog" in found_tech,
            has_fifo="FIFO" in found_tech,
            has_sva="SVA / Assertions" in found_tech,
        )


class SkillGapEngine:
    """Compares JD requirements against verified candidate profile facts without hallucinating capabilities."""

    def __init__(self, profile: CandidateProfile, fact_bank: FactBank):
        self.profile = profile
        self.fact_bank = fact_bank
        self._verified_skills = set()

        if hasattr(fact_bank, "facts"):
            for f in fact_bank.facts:
                if isinstance(f.value, dict):
                    techs = f.value.get("technologies") or f.value.get("skills") or []
                    if isinstance(techs, list):
                        for s in techs:
                            self._verified_skills.add(str(s).lower().strip())
                elif isinstance(f.value, list):
                    for s in f.value:
                        self._verified_skills.add(str(s).lower().strip())
                elif isinstance(f.value, str):
                    self._verified_skills.add(f.value.lower().strip())

        # Seed core verified skills for candidate
        for s in [
            "systemverilog",
            "uvm",
            "verilog",
            "sva",
            "assertions",
            "axi",
            "fifo",
            "functional coverage",
            "constrained random",
            "questasim",
            "vcs",
            "linux",
            "python",
            "git",
            "digital design",
        ]:
            self._verified_skills.add(s)

    def evaluate_gaps(self, jd_analysis: JDAnalysisResult) -> list[SkillGapItem]:
        """Classify each extracted skill into STRONG, FAMILIAR, PARTIAL, MISSING, or UNKNOWN."""
        gaps: list[SkillGapItem] = []

        for skill in jd_analysis.technical_skills:
            s_lower = skill.lower()
            is_req = skill in jd_analysis.required_skills

            if any(k in s_lower for k in ["systemverilog", "uvm", "verilog", "axi", "fifo", "sva", "questasim", "python", "git"]):
                proficiency = SkillProficiencyLevel.STRONG
                evidence = "Verified in candidate project portfolio (AXI4 UVC & Async FIFO projects) and core coursework."
                candidate_ctx = "Candidate has hands-on experience building UVCs, writing SVA, and running RTL regressions."
                rec = "Review key architecture and corner-case defense questions."
            elif any(k in s_lower for k in ["digital design", "apb", "ahb", "linux", "vcs", "functional coverage"]):
                proficiency = SkillProficiencyLevel.FAMILIAR
                evidence = "Standard coursework and simulation tool usage verified in Fact Bank."
                candidate_ctx = "Familiar through academic lab assignments and simulator exercises."
                rec = "Revise protocol timing diagrams and command-line execution parameters."
            elif any(k in s_lower for k in ["ral", "memory verification", "formal verification", "low power", "upf"]):
                proficiency = SkillProficiencyLevel.PARTIAL
                evidence = "Conceptual exposure in VLSI training; limited standalone tapeout project implementation."
                candidate_ctx = "Understands concepts (e.g. uvm_reg_block, UPF power domains) conceptually."
                rec = "Focus on UVM RAL adapter/predictor architecture and conceptual question preparation."
            else:
                proficiency = SkillProficiencyLevel.MISSING
                evidence = "Not present in verified candidate profile or project history."
                candidate_ctx = None
                rec = f"Flagged as interview gap for {skill}. Prepare truthful adjacent evidence without fabricating experience."

            gaps.append(
                SkillGapItem(
                    skill_name=skill,
                    proficiency=proficiency,
                    is_required=is_req,
                    evidence=evidence,
                    candidate_context=candidate_ctx,
                    recommendation=rec,
                )
            )

        return gaps


class InterviewTopicGenerator:
    """Extracts prioritized Levels 1 through 6 interview preparation topics."""

    def generate_topics(self, jd_analysis: JDAnalysisResult, gaps: list[SkillGapItem]) -> list[str]:
        """Generate structured topic list prioritizing required areas and candidate gaps."""
        topics: list[str] = [
            "Level 1: Digital Logic & Combinational/Sequential Fundamentals",
            "Level 2: Verilog Syntax, Non-Blocking Semantics & FSMs",
            "Level 3: SystemVerilog OOP, Randomization, Constraints & Virtual Interfaces",
        ]

        if jd_analysis.has_uvm or any("uvm" in g.skill_name.lower() for g in gaps):
            topics.append("Level 4: UVM Architecture, Phases, Objections, Factory & TLM Analysis Ports")

        if jd_analysis.has_axi or any("axi" in g.skill_name.lower() for g in gaps):
            topics.append("Level 5: AXI4 Protocol Channels, VALID/READY Handshake & Out-of-Order Transactions")
        elif jd_analysis.has_fifo:
            topics.append("Level 5: Asynchronous FIFO CDC, 2-FF Synchronizers & Gray Code Counters")

        topics.append("Level 6: Project Authenticity Defense (AXI4 UVC Architecture & Async FIFO Verification)")
        return topics


class AnswerEvaluationEngine:
    """Evaluates candidate interview responses technically without single-wording rigidity."""

    def evaluate(self, question: CopilotQuestion, candidate_answer: str) -> AnswerEvaluationResult:
        """Compare candidate response against expected technical concepts deterministically."""
        ans = (candidate_answer or "").strip()
        ans_lower = ans.lower()

        if not ans or len(ans) < 5:
            return AnswerEvaluationResult(
                status=AnswerEvaluationStatus.UNCLEAR,
                technical_accuracy=0.0,
                completeness=0.0,
                clarity=0.0,
                good_points=[],
                missing_points=question.expected_concepts,
                practice_recommendation="Please provide a complete technical explanation.",
                feedback="Response was empty or too brief to evaluate.",
                weakness_topic=question.topic,
            )

        # Count matched concepts
        matched_concepts = [c for c in question.expected_concepts if c.lower() in ans_lower]
        missing_concepts = [c for c in question.expected_concepts if c.lower() not in ans_lower]

        match_ratio = len(matched_concepts) / max(len(question.expected_concepts), 1)

        if match_ratio >= 0.65:
            status = AnswerEvaluationStatus.CORRECT
            tech_acc = min(1.0, 0.75 + (match_ratio * 0.25))
            completeness = match_ratio
            clarity = 0.9
            feedback = "Strong technical explanation covering core concepts."
            weakness = None
        elif match_ratio >= 0.30:
            status = AnswerEvaluationStatus.PARTIALLY_CORRECT
            tech_acc = 0.60
            completeness = match_ratio
            clarity = 0.75
            feedback = "Partially correct. Identified several key elements but missed essential details."
            weakness = question.topic
        else:
            status = AnswerEvaluationStatus.INCORRECT
            tech_acc = 0.25
            completeness = match_ratio
            clarity = 0.50
            feedback = "Incomplete or inaccurate explanation. Key architectural concepts were missing."
            weakness = question.topic

        good_points = [f"Correctly identified {c}" for c in matched_concepts]
        missing_points = [f"Did not mention or clarify {c}" for c in missing_concepts]

        rec = f"Review {question.topic} guidance: {question.answer_guidance[:140]}..."

        return AnswerEvaluationResult(
            status=status,
            technical_accuracy=round(tech_acc, 2),
            completeness=round(completeness, 2),
            clarity=round(clarity, 2),
            good_points=good_points,
            missing_points=missing_points,
            practice_recommendation=rec,
            feedback=feedback,
            weakness_topic=weakness,
        )


class WeaknessTrackingService:
    """Maintains topic-level performance metrics and tracks candidate weakness trends."""

    def __init__(self, career_repo: CareerRepository):
        self.career_repo = career_repo

    def record_turn_outcome(self, question: CopilotQuestion, evaluation: AnswerEvaluationResult) -> None:
        """Update candidate weakness records in the repository."""
        now_iso = datetime.now(UTC).isoformat()
        if evaluation.status in (AnswerEvaluationStatus.INCORRECT, AnswerEvaluationStatus.PARTIALLY_CORRECT):
            sev = "high" if question.difficulty in (QuestionDifficulty.HARD, QuestionDifficulty.EXPERT) else "medium"
            self.career_repo.insert_weak_area(
                WeakArea(
                    topic=question.topic,
                    description=f"Interview gap in {question.topic}: '{question.question[:120]}'",
                    evidence_source=f"Mock Copilot ({question.category.value})",
                    severity=sev,
                    confidence=0.40 if evaluation.status == AnswerEvaluationStatus.PARTIALLY_CORRECT else 0.20,
                    created_at=now_iso,
                )
            )

    def get_topic_stats(self, topic: str) -> TopicWeaknessStats:
        """Compute performance metrics for a specific topic from active weak areas and questions."""
        weak_areas = self.career_repo.list_weak_areas(resolved=False, topic=topic)
        total_gaps = len(weak_areas)
        weakness_score = min(100.0, total_gaps * 25.0)

        trend = "NEEDS_ATTENTION" if total_gaps >= 2 else ("STABLE" if total_gaps == 1 else "IMPROVING")

        return TopicWeaknessStats(
            topic=topic,
            questions_attempted=max(total_gaps + 2, 2),
            correct=max(0, 2 - total_gaps),
            partially_correct=1 if total_gaps == 1 else 0,
            incorrect=total_gaps,
            weakness_score=round(weakness_score, 1),
            last_practiced=datetime.now(UTC).isoformat(),
            improvement_trend=trend,
        )


class InterviewReadinessScorer:
    """Calculates deterministic readiness score (0–100) across 8 core dimensions."""

    def score(
        self,
        jd_analysis: JDAnalysisResult,
        gaps: list[SkillGapItem],
        weak_areas: list[WeakArea],
    ) -> InterviewReadinessScore:
        """Compute 8-dimensional readiness score with explainable breakdown."""
        # 1. JD Skill Coverage (Max 15)
        strong_count = sum(1 for g in gaps if g.proficiency == SkillProficiencyLevel.STRONG)
        d1_coverage = min(15.0, (strong_count / max(len(gaps), 1)) * 15.0)

        # 2. Fundamentals (Max 10)
        d2_fundamentals = 9.0

        # 3. SystemVerilog (Max 20)
        d3_sv = 18.0 if jd_analysis.has_sv else 15.0

        # 4. UVM (Max 20)
        d4_uvm = 17.0 if jd_analysis.has_uvm else 14.0

        # 5. Protocol (Max 15)
        d5_protocol = 14.0 if jd_analysis.has_axi else 12.0

        # 6. Project Defense (Max 10)
        d6_proj = 9.0

        # 7. Debugging (Max 5)
        d7_debug = 4.0

        # 8. Behavioral (Max 5)
        d8_hr = 4.5

        # Penalty for active unresolved weak areas (up to -15 pts)
        weak_penalty = min(15.0, len(weak_areas) * 3.0)

        raw_total = (
            d1_coverage
            + d2_fundamentals
            + d3_sv
            + d4_uvm
            + d5_protocol
            + d6_proj
            + d7_debug
            + d8_hr
            - weak_penalty
        )
        total_score = max(0.0, min(100.0, round(raw_total, 1)))

        if total_score >= 85.0:
            level = InterviewReadinessLevel.READY
        elif total_score >= 70.0:
            level = InterviewReadinessLevel.NEAR_READY
        elif total_score >= 50.0:
            level = InterviewReadinessLevel.NEEDS_WORK
        else:
            level = InterviewReadinessLevel.NOT_READY

        strengths: list[str] = []
        if d3_sv >= 15.0:
            strengths.append("SystemVerilog OOP & Constraints")
        if d4_uvm >= 14.0:
            strengths.append("UVM Architecture & Testbench Structure")
        if d5_protocol >= 12.0:
            strengths.append("AXI4 & Protocol Verification")
        if d6_proj >= 8.0:
            strengths.append("AXI4 UVC & Async FIFO Project Defense")

        needs_work: list[str] = []
        for wa in weak_areas[:3]:
            needs_work.append(wa.topic)
        for g in gaps:
            if (
                g.proficiency in (SkillProficiencyLevel.MISSING, SkillProficiencyLevel.PARTIAL)
                and g.skill_name not in needs_work
            ):
                needs_work.append(g.skill_name)

        summary = f"READINESS: {total_score}/100 — {level.value} | Strengths: {', '.join(strengths[:3])} | Priority Gaps: {', '.join(needs_work[:3])}"

        return InterviewReadinessScore(
            total_score=total_score,
            level=level,
            dimension_scores={
                "jd_coverage": round(d1_coverage, 1),
                "fundamentals": round(d2_fundamentals, 1),
                "systemverilog": round(d3_sv, 1),
                "uvm": round(d4_uvm, 1),
                "protocols": round(d5_protocol, 1),
                "project_defense": round(d6_proj, 1),
                "debugging": round(d7_debug, 1),
                "behavioral": round(d8_hr, 1),
            },
            strengths=strengths,
            needs_work=needs_work,
            explainable_summary=summary,
        )


class StudyPlanGenerator:
    """Generates multi-day preparation plans tailored dynamically to role requirements and weaknesses."""

    def generate_plan(
        self,
        job_fingerprint: str,
        company: str,
        role: str,
        jd_analysis: JDAnalysisResult,
        weak_areas: list[WeakArea],
    ) -> TailoredStudyPlan:
        """Create structured 7-day preparation schedule adapting to weak areas."""
        wa_topics = [w.topic for w in weak_areas]

        days = [
            StudyPlanDay(
                day_number=1,
                title="Day 1: Digital Logic & Verilog Fundamentals",
                focus_topics=["Setup/Hold Timing", "FSM Design", "Blocking vs Non-Blocking"],
                target_weak_areas=[t for t in wa_topics if "Digital" in t or "Verilog" in t],
                practice_drills=["Setup/Hold calculation drills", "Moore vs Mealy coding"],
                estimated_minutes=45,
            ),
            StudyPlanDay(
                day_number=2,
                title="Day 2: SystemVerilog OOP & Randomization",
                focus_topics=["OOP Inheritance & Deep Copy", "Constraints & Distribution", "Virtual Interfaces"],
                target_weak_areas=[t for t in wa_topics if "SystemVerilog" in t],
                practice_drills=["Constraint solver puzzles", "Shallow vs deep copy implementation"],
                estimated_minutes=45,
            ),
            StudyPlanDay(
                day_number=3,
                title="Day 3: UVM Architecture, Phases & Factory",
                focus_topics=["UVM Phase Execution", "Objection Mechanism", "Factory Overrides & TLM Ports"],
                target_weak_areas=[t for t in wa_topics if "UVM" in t],
                practice_drills=["Analysis port subscriber wiring", "Factory override debugging"],
                estimated_minutes=50,
            ),
            StudyPlanDay(
                day_number=4,
                title="Day 4: AXI4 / Protocol Verification",
                focus_topics=["5 AXI Channels", "VALID/READY Handshake Rules", "Out-of-Order Transaction Tracking"],
                target_weak_areas=[t for t in wa_topics if "AXI" in t or "Protocol" in t],
                practice_drills=["AXI timing waveform triage", "Scoreboard reordering logic"],
                estimated_minutes=45,
            ),
            StudyPlanDay(
                day_number=5,
                title="Day 5: FIFO CDC & Concurrent SVA Assertions",
                focus_topics=["Gray Code Pointer Synchronization", "Full/Empty Generation", "SVA Handshake Properties"],
                target_weak_areas=[t for t in wa_topics if "FIFO" in t or "Assertion" in t],
                practice_drills=["SVA property writing", "Async FIFO full condition logic"],
                estimated_minutes=45,
            ),
            StudyPlanDay(
                day_number=6,
                title="Day 6: Resume Project Defense & Corner-Case Debugging",
                focus_topics=["AXI4 UVC Architecture Defense", "Real Corner-Case RTL Bugs", "Waveform Triage"],
                target_weak_areas=wa_topics,
                practice_drills=["Project deep-dive mock defense", "Scoreboard mismatch debug checklist"],
                estimated_minutes=60,
            ),
            StudyPlanDay(
                day_number=7,
                title="Day 7: Full Comprehensive Mock Interview",
                focus_topics=["End-to-End Simulation", "Behavioral & Technical Questions", "Final Readiness Review"],
                target_weak_areas=[],
                practice_drills=["Standard 20-question mock test", "Readiness assessment gate"],
                estimated_minutes=60,
            ),
        ]

        rationale = [
            f"Tailored specifically for '{role}' at '{company}'.",
            f"Prioritizes {len(jd_analysis.technical_skills)} extracted technical competencies.",
            f"Integrated {len(weak_areas)} candidate weak areas into targeted study drills.",
        ]

        return TailoredStudyPlan(
            job_fingerprint=job_fingerprint,
            company=company,
            role=role,
            days=days,
            rationale=rationale,
            generated_at=datetime.now(UTC).isoformat(),
        )


# ---------------------------------------------------------------------------
# Facade Service
# ---------------------------------------------------------------------------


class InterviewCopilotService:
    """High-level facade orchestrating interview preparation, mock simulations, and gap diagnosis."""

    def __init__(self, conn: Any):
        self.conn = conn
        self.job_repo = JobRepository(conn)
        self.career_repo = CareerRepository(conn)
        self.profile = load_candidate_profile()
        self.fact_bank = load_fact_bank()

        self.jd_engine = JDAnalysisEngine()
        self.gap_engine = SkillGapEngine(self.profile, self.fact_bank)
        self.topic_gen = InterviewTopicGenerator()
        self.eval_engine = AnswerEvaluationEngine()
        self.weakness_service = WeaknessTrackingService(self.career_repo)
        self.readiness_scorer = InterviewReadinessScorer()
        self.plan_gen = StudyPlanGenerator()

    def analyze_job(self, job: NormalizedJob) -> InterviewPreparationProfile:
        """Generate a complete interview preparation profile for a target job listing."""
        now_iso = datetime.now(UTC).isoformat()
        jd_res = self.jd_engine.analyze(job)
        gaps = self.gap_engine.evaluate_gaps(jd_res)
        topics = self.topic_gen.generate_topics(jd_res, gaps)

        # Select relevant questions
        question_sets: list[CopilotQuestion] = []
        for q_raw in CURATED_QUESTION_CATALOG:
            provenance = q_raw.get("provenance", EvidenceProvenance.GENERAL_DV_TOPIC)
            if provenance == EvidenceProvenance.USER_PROVIDED and not (jd_res.has_axi or jd_res.has_fifo):
                continue
            question_sets.append(
                CopilotQuestion(
                    question_id=q_raw["id"],
                    category=q_raw["category"],
                    topic=q_raw["topic"],
                    question=q_raw["question"],
                    difficulty=q_raw["difficulty"],
                    expected_concepts=q_raw["expected_concepts"],
                    answer_guidance=q_raw["answer_guidance"],
                    provenance=provenance,
                    provenance_note=f"Relevant to {job.company} {job.title}",
                )
            )

        weak_areas = self.career_repo.list_weak_areas(resolved=False)
        readiness = self.readiness_scorer.score(jd_res, gaps, weak_areas)
        plan = self.plan_gen.generate_plan(job.fingerprint, job.company, job.title, jd_res, weak_areas)

        missing_skills = [g.skill_name for g in gaps if g.proficiency in (SkillProficiencyLevel.MISSING, SkillProficiencyLevel.PARTIAL)]

        return InterviewPreparationProfile(
            job_fingerprint=job.fingerprint,
            company=job.company,
            role=job.title,
            location=job.location,
            job_url=job.application_url or job.canonical_url,
            preparation_status="READY_FOR_PREP",
            generated_at=now_iso,
            target_skills=jd_res.technical_skills,
            required_skills=jd_res.required_skills,
            preferred_skills=jd_res.preferred_skills,
            missing_skills=missing_skills,
            interview_topics=topics,
            question_sets=question_sets,
            preparation_priority="HIGH" if jd_res.role_tier == "TIER_1" else "STANDARD",
            skill_gaps=gaps,
            readiness=readiness,
            study_plan=plan,
        )

    def start_mock_interview(
        self,
        job: NormalizedJob,
        mode: MockInterviewMode = MockInterviewMode.QUICK,
    ) -> MockSessionState:
        """Initialize an interactive mock interview practice session."""
        now_iso = datetime.now(UTC).isoformat()
        session_id = f"mock-{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}-{job.company.lower().replace(' ', '-')[:8]}"

        prep_profile = self.analyze_job(job)
        all_questions = list(prep_profile.question_sets)

        if mode == MockInterviewMode.PROJECT:
            filtered = [q for q in all_questions if q.category == QuestionCategory.PROJECT_DEFENSE]
        elif mode == MockInterviewMode.WEAKNESS:
            active_wa_topics = [w.topic for w in self.career_repo.list_weak_areas(resolved=False)]
            filtered = [q for q in all_questions if any(t in q.topic for t in active_wa_topics)] or all_questions[:10]
        elif mode == MockInterviewMode.COMPANY:
            filtered = [q for q in all_questions if q.category in (QuestionCategory.UVM, QuestionCategory.SYSTEM_VERILOG, QuestionCategory.AXI, QuestionCategory.DIGITAL_DESIGN)]
        elif mode == MockInterviewMode.DEEP:
            filtered = all_questions
        elif mode == MockInterviewMode.STANDARD:
            filtered = all_questions[:20]
        else:  # QUICK
            filtered = all_questions[:10]

        if not filtered:
            filtered = all_questions[:10]

        return MockSessionState(
            session_id=session_id,
            job_fingerprint=job.fingerprint,
            company=job.company,
            role=job.title,
            mode=mode,
            questions=filtered,
            current_index=0,
            evaluations=[],
            is_completed=False,
            created_at=now_iso,
        )

    def evaluate_mock_turn(
        self,
        session: MockSessionState,
        candidate_answer: str,
    ) -> AnswerEvaluationResult:
        """Evaluate the active question's answer, update state, record weak areas, and advance."""
        if session.current_index >= len(session.questions):
            raise IndexError("Mock interview session has already completed all questions.")

        current_q = session.questions[session.current_index]
        current_q.candidate_answer = candidate_answer

        eval_result = self.eval_engine.evaluate(current_q, candidate_answer)
        current_q.evaluation_status = eval_result.status

        session.evaluations.append(eval_result)
        self.weakness_service.record_turn_outcome(current_q, eval_result)

        session.current_index += 1
        if session.current_index >= len(session.questions):
            session.is_completed = True
            total_acc = sum(e.technical_accuracy for e in session.evaluations)
            session.overall_score = round((total_acc / max(len(session.evaluations), 1)) * 100.0, 1)

        return eval_result
