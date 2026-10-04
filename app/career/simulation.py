"""Multi-stage interview simulation and resume project authenticity defense engine."""

from datetime import UTC, datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field

from app.career.repository import CareerRepository
from app.db.models import WeakArea


class SimulationStage(str, Enum):
    """Sequential stages for full mock interview simulation."""

    HR = "HR"
    DIGITAL_DESIGN = "Digital Design"
    SYSTEM_VERILOG = "SystemVerilog"
    UVM = "UVM"
    PROTOCOL = "Protocol"
    PROJECT_DEEP_DIVE = "Project Deep Dive"
    DEBUGGING = "Debugging"
    BEHAVIORAL = "Behavioral"


class ProjectAuthenticityQuestion(BaseModel):
    """Deep-dive defense question verifying candidate's hands-on project authenticity."""

    model_config = ConfigDict(extra="forbid")

    project_name: str
    focus_aspect: str
    question_text: str
    expected_depth: str
    authenticity_flag: str | None = None


class SimulationTurn(BaseModel):
    """Single turn of interactive interview simulation."""

    model_config = ConfigDict(extra="forbid")

    turn_number: int
    stage: SimulationStage
    question: str
    expected_answer: str | None = None
    user_response: str | None = None
    evaluated_correctness: bool | None = None
    depth_score: float | None = Field(default=None, ge=0.0, le=1.0)
    clarity_score: float | None = Field(default=None, ge=0.0, le=1.0)
    feedback: str | None = None
    timestamp: str


class SimulationSession(BaseModel):
    """Complete record of a multi-stage interview simulation."""

    model_config = ConfigDict(extra="forbid")

    session_id: str
    company: str
    role: str
    current_stage_index: int = 0
    stages: list[SimulationStage]
    turns: list[SimulationTurn] = Field(default_factory=list)
    is_completed: bool = False
    overall_score: float | None = None
    created_at: str


# Core project defense defense templates for common VLSI fresher projects
PROJECT_DEFENSE_TEMPLATES: dict[str, list[dict[str, str]]] = {
    "axi": [
        {
            "aspect": "Topology & Architecture",
            "question": "Draw and explain your AXI4 UVC architecture. How did your agent connect to the DUT interface?",
            "depth": "Should explain active/passive agent modes, virtual interface binding in connect_phase, driver/monitor/sequencer hierarchy.",
        },
        {
            "aspect": "Sequence vs Sequencer",
            "question": "Explain how transactions were generated from your sequence and dispatched through the sequencer to the driver.",
            "depth": "Must detail `start_item()`, `finish_item()`, `seq_item_port.get_next_item()`, and `item_done()` handshake.",
        },
        {
            "aspect": "Scoreboard & Transaction Matching",
            "question": "How did your scoreboard handle out-of-order write responses and interleaved read IDs without race conditions?",
            "depth": "Must describe associative arrays or queues keyed on `AWID` / `ARID` and in-order matching per ID thread.",
        },
        {
            "aspect": "Functional Coverage & SVA",
            "question": "What cross-coverage bins did you define, and what concurrent assertions guarded the VALID/READY handshake?",
            "depth": "Must cite cross bins between burst_type x burst_size x burst_len, and SVA for VALID staying high until READY asserted.",
        },
        {
            "aspect": "Real Bugs Found",
            "question": "Describe a real RTL corner-case bug caught by your testbench and how you debugged the waveform.",
            "depth": "Must describe concrete scenario (e.g. back-to-back unaligned wrap bursts or FIFO overflow under backpressure).",
        },
    ],
    "fifo": [
        {
            "aspect": "CDC & Pointer Synchronization",
            "question": "Explain the exact logic used to generate FIFO full and empty flags across asynchronous clock domains.",
            "depth": "Must explain 2-FF Gray code pointer synchronization and why Gray code prevents multi-bit transition glitches.",
        },
        {
            "aspect": "Full Condition Detection",
            "question": "How did your full condition logic distinguish between completely full vs completely empty when Gray pointers match?",
            "depth": "Must explain MSB and 2nd MSB bit inversion check for full condition versus exact match for empty condition.",
        },
        {
            "aspect": "Assertions & Overflow Guarding",
            "question": "Write an SVA property to prove that write enable is never asserted when the FIFO is full.",
            "depth": "Must provide `assert property (@(posedge wclk) full |-> !winc)` or equivalent with disable iff.",
        },
    ],
    "apb": [
        {
            "aspect": "Protocol State Machine",
            "question": "Explain the APB bridge protocol states: IDLE, SETUP, and ACCESS, and the role of PREADY and PSLVERR.",
            "depth": "Must describe exact cycle transitions: SETUP is 1 cycle where PSEL=1, PENABLE=0, then ACCESS where PENABLE=1.",
        },
        {
            "aspect": "UVC Implementation",
            "question": "How did your APB driver drive signals during SETUP and wait for PREADY during ACCESS?",
            "depth": "Must demonstrate driver clocking block interaction and non-blocking assignment synchronicity.",
        },
    ],
}


class ProjectAuthenticityChecker:
    """Generates rigorous deep-dive defense questions to verify hands-on authenticity of candidate resume projects."""

    def __init__(self, career_repo: CareerRepository):
        self.career_repo = career_repo

    def generate_defense_questions_for_project(
        self, project_name: str, project_description: str
    ) -> list[ProjectAuthenticityQuestion]:
        """Generate targeted project defense questions based on project keywords."""
        name_lower = project_name.lower()
        desc_lower = project_description.lower()
        matched_templates: list[dict[str, str]] = []

        if "axi" in name_lower or "axi" in desc_lower:
            matched_templates.extend(PROJECT_DEFENSE_TEMPLATES.get("axi", []))
        elif "fifo" in name_lower or "fifo" in desc_lower:
            matched_templates.extend(PROJECT_DEFENSE_TEMPLATES.get("fifo", []))
        elif "apb" in name_lower or "apb" in desc_lower or "uart" in desc_lower:
            matched_templates.extend(PROJECT_DEFENSE_TEMPLATES.get("apb", []))
        else:
            # Generic VLSI project defense questions
            matched_templates = [
                {
                    "aspect": "Testbench Architecture",
                    "question": f"Explain the verification environment architecture created for '{project_name}'.",
                    "depth": "Candidate must explain component connectivity, stimulus generation, and verification methodology.",
                },
                {
                    "aspect": "Corner-Case Verification",
                    "question": f"What was the most difficult corner case verified in '{project_name}', and how did you verify it?",
                    "depth": "Candidate must explain constrained-random sequences and assertions used.",
                },
                {
                    "aspect": "Bug Identification",
                    "question": "Describe a specific functional bug you found in RTL during simulation.",
                    "depth": "Candidate must clearly articulate symptom, root cause, waveform tracing, and fix verification.",
                },
            ]

        return [
            ProjectAuthenticityQuestion(
                project_name=project_name,
                focus_aspect=t["aspect"],
                question_text=t["question"],
                expected_depth=t["depth"],
            )
            for t in matched_templates
        ]


class InterviewSimulationEngine:
    """Engine orchestrating realistic, sequential turn-by-turn interview simulations."""

    def __init__(self, career_repo: CareerRepository):
        self.career_repo = career_repo
        self.authenticity_checker = ProjectAuthenticityChecker(career_repo)

    def start_simulation(
        self,
        company: str,
        role: str,
        stages: list[SimulationStage] | None = None,
    ) -> SimulationSession:
        """Initialize a new multi-stage interview simulation session."""
        now_iso = datetime.now(UTC).isoformat()
        session_id = f"sim-{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}-{company.lower().replace(' ', '-')[:10]}"
        sim_stages = stages or [
            SimulationStage.HR,
            SimulationStage.DIGITAL_DESIGN,
            SimulationStage.SYSTEM_VERILOG,
            SimulationStage.UVM,
            SimulationStage.PROTOCOL,
            SimulationStage.PROJECT_DEEP_DIVE,
            SimulationStage.DEBUGGING,
            SimulationStage.BEHAVIORAL,
        ]

        return SimulationSession(
            session_id=session_id,
            company=company,
            role=role,
            current_stage_index=0,
            stages=sim_stages,
            turns=[],
            is_completed=False,
            created_at=now_iso,
        )

    def get_next_question_for_stage(
        self, session: SimulationSession, project_name: str | None = None
    ) -> str:
        """Retrieve or generate the interview question for the active simulation stage."""
        if session.current_stage_index >= len(session.stages):
            return "Interview simulation complete. You may submit for final scoring."

        current_stage = session.stages[session.current_stage_index]

        if current_stage == SimulationStage.HR:
            return "Introduce yourself and explain why you are interested in this VLSI Design Verification role."
        elif current_stage == SimulationStage.DIGITAL_DESIGN:
            return "Explain setup time and hold time violations. How do you resolve a hold violation in post-layout STA?"
        elif current_stage == SimulationStage.SYSTEM_VERILOG:
            return "What is the difference between shallow copy and deep copy in SystemVerilog OOP? When is deep copy mandatory?"
        elif current_stage == SimulationStage.UVM:
            return "Explain how the UVM factory mechanism works and how `set_type_override_by_type` enables test-level component replacement."
        elif current_stage == SimulationStage.PROTOCOL:
            return "In AXI4, explain why the read address channel and read data channel are decoupled, and how RID matches ARID."
        elif current_stage == SimulationStage.PROJECT_DEEP_DIVE:
            proj = project_name or "your primary UVC verification project"
            defense_qs = self.authenticity_checker.generate_defense_questions_for_project(proj, proj)
            return defense_qs[0].question_text
        elif current_stage == SimulationStage.DEBUGGING:
            return "You notice a scoreboard mismatch where transactions are arriving out of order. Walk me through your debug checklist."
        elif current_stage == SimulationStage.BEHAVIORAL:
            return "Describe a scenario where you faced a challenging technical bug close to a deadline. How did you prioritize and solve it?"

        return f"Explain your verification approach for {current_stage.value}."

    def submit_turn_response(
        self,
        session: SimulationSession,
        user_response: str,
        was_correct: bool,
        depth_score: float = 0.8,
        clarity_score: float = 0.85,
        feedback: str | None = None,
    ) -> SimulationTurn:
        """Process candidate response, evaluate turn, advance simulation stage, and record gaps."""
        now_iso = datetime.now(UTC).isoformat()
        current_stage = session.stages[session.current_stage_index]

        turn = SimulationTurn(
            turn_number=len(session.turns) + 1,
            stage=current_stage,
            question=self.get_next_question_for_stage(session),
            user_response=user_response,
            evaluated_correctness=was_correct,
            depth_score=depth_score,
            clarity_score=clarity_score,
            feedback=feedback or ("Strong answer with good technical depth." if was_correct else "Needs deeper technical precision."),
            timestamp=now_iso,
        )
        session.turns.append(turn)

        # If answer was incorrect, register weak area
        if not was_correct:
            self.career_repo.insert_weak_area(
                WeakArea(
                    topic=current_stage.value,
                    description=f"Simulation gap in {current_stage.value}: '{turn.question[:100]}'",
                    evidence_source=f"Simulation {session.session_id} ({session.company})",
                    severity="high" if current_stage in [SimulationStage.UVM, SimulationStage.SYSTEM_VERILOG] else "medium",
                    confidence=0.35,
                    created_at=now_iso,
                )
            )

        # Advance stage
        session.current_stage_index += 1
        if session.current_stage_index >= len(session.stages):
            session.is_completed = True
            # Calculate overall simulation score
            correct_count = sum(1 for t in session.turns if t.evaluated_correctness)
            session.overall_score = round((correct_count / len(session.turns)) * 100.0, 1)

        return turn
