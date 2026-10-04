"""Consolidated 17-point Final Interview Pack generator for pre-interview revision."""

from datetime import UTC, datetime

from pydantic import BaseModel, ConfigDict

from app.career.assessment import AdaptiveAssessmentEngine
from app.career.bank import QuestionBankService
from app.career.repository import CareerRepository
from app.career.simulation import ProjectAuthenticityChecker
from app.db.models import InterviewQuestion, KnowledgeItem, WeakArea
from app.db.repository import JobRepository


class CodingQuestionItem(BaseModel):
    """Specific coding, assertion, or constraint problem expected in interview."""

    model_config = ConfigDict(extra="forbid")

    title: str
    category: str
    problem_statement: str
    reference_code_solution: str


class InterviewPack(BaseModel):
    """Consolidated 17-point pre-interview revision pack synthesized deterministically for a target job."""

    model_config = ConfigDict(extra="forbid")

    # 1. Company & 2. Role
    company: str
    role: str
    job_id: int

    # 3. Job Description Summary
    job_description_summary: str

    # 4. Required Skills
    required_skills: list[str]

    # 5. Historical Questions
    historical_questions: list[InterviewQuestion]

    # 6. Frequently Repeated Questions
    frequently_repeated_questions: list[InterviewQuestion]

    # 7. Previously Missed Questions
    previously_missed_questions: list[InterviewQuestion]

    # 8. Weak Areas
    active_weak_areas: list[WeakArea]

    # 9. Important Concepts
    important_concepts: list[KnowledgeItem]

    # 10. Project Deep-Dive Questions
    project_deep_dive_questions: list[str]

    # 11. Expected Coding Questions
    expected_coding_questions: list[CodingQuestionItem]

    # 12. Expected Debugging Questions
    expected_debugging_questions: list[str]

    # 13. HR Questions
    hr_questions: list[str]

    # 14. Resume-Specific Questions
    resume_specific_questions: list[str]

    # 15. Final Revision Checklist
    final_revision_checklist: list[str]

    # 16. Readiness Score & Gate Status
    readiness_score: float
    readiness_level: str

    # 17. Last-Minute Topics
    last_minute_topics: list[str]

    generated_at: str


# Curated expected coding challenges in DV fresher interviews
CURATED_DV_CODING_QUESTIONS: list[CodingQuestionItem] = [
    CodingQuestionItem(
        title="SVA Request-Acknowledge Handshake Assertion",
        category="SystemVerilog Assertions",
        problem_statement="Write a concurrent assertion to prove that when `req` rises, `ack` must be asserted within 1 to 3 clock cycles, and `req` must remain high until `ack` is asserted.",
        reference_code_solution=(
            "property p_req_ack;\n"
            "  @(posedge clk) disable iff (!rst_n)\n"
            "  $rose(req) |-> (req throughout (##[1:3] ack));\n"
            "endproperty\n"
            "assert_req_ack: assert property(p_req_ack) else $error(\"REQ-ACK handshake violated!\");"
        ),
    ),
    CodingQuestionItem(
        title="Constrained-Random Address Alignment Constraint",
        category="Constrained Randomization",
        problem_statement="Write a SystemVerilog class constraint for an address `addr` such that it is 4-byte aligned (bottom 2 bits 0), inside address range [0x1000 : 0x8000], excluding range [0x3000 : 0x4000].",
        reference_code_solution=(
            "class transaction;\n"
            "  rand bit [31:0] addr;\n"
            "  constraint c_addr_align {\n"
            "    addr[1:0] == 2'b00;\n"
            "    addr inside {[32'h1000 : 32'h8000]};\n"
            "    !(addr inside {[32'h3000 : 32'h4000]});\n"
            "  }\n"
            "endclass"
        ),
    ),
    CodingQuestionItem(
        title="UVM Driver Run Phase Implementation",
        category="UVM Driver",
        problem_statement="Write the `run_phase` method for a `uvm_driver` driving a packet `my_item` through a virtual interface `vif` using standard sequence item port handshake.",
        reference_code_solution=(
            "virtual task run_phase(uvm_phase phase);\n"
            "  forever begin\n"
            "    seq_item_port.get_next_item(req);\n"
            "    drive_item(req);\n"
            "    seq_item_port.item_done();\n"
            "  end\n"
            "endtask\n"
            "task drive_item(my_item item);\n"
            "  @(posedge vif.clk);\n"
            "  vif.valid <= 1'b1;\n"
            "  vif.data  <= item.data;\n"
            "  wait(vif.ready == 1'b1);\n"
            "  @(posedge vif.clk);\n"
            "  vif.valid <= 1'b0;\n"
            "endtask"
        ),
    ),
    CodingQuestionItem(
        title="Functional Covergroup with Cross Coverage",
        category="Functional Coverage",
        problem_statement="Define a covergroup covering AXI burst types (FIXED, INCR, WRAP) and burst length (1 to 16) with cross coverage between burst type and length.",
        reference_code_solution=(
            "covergroup axi_cg @(posedge clk);\n"
            "  cp_type: coverpoint tr.burst_type {\n"
            "    bins fixed = {2'b00};\n"
            "    bins incr  = {2'b01};\n"
            "    bins wrap  = {2'b10};\n"
            "  }\n"
            "  cp_len: coverpoint tr.burst_len {\n"
            "    bins single = {0};\n"
            "    bins short_burst = {[1:3]};\n"
            "    bins long_burst = {[4:15]};\n"
            "  }\n"
            "  cross_type_len: cross cp_type, cp_len;\n"
            "endgroup"
        ),
    ),
]


class InterviewPackGenerator:
    """Generates the authoritative 17-point consolidated interview preparation pack."""

    def __init__(
        self,
        job_repo: JobRepository,
        career_repo: CareerRepository,
        assessment_engine: AdaptiveAssessmentEngine,
        bank_service: QuestionBankService,
    ):
        self.job_repo = job_repo
        self.career_repo = career_repo
        self.assessment_engine = assessment_engine
        self.bank_service = bank_service
        self.authenticity_checker = ProjectAuthenticityChecker(career_repo)

    def generate_interview_pack(self, job_id: int) -> InterviewPack:
        """Synthesize all 17 components into a comprehensive pre-interview pack."""
        job = self.job_repo.get_normalized_job(job_id)
        if not job:
            raise ValueError(f"Job #{job_id} not found.")

        now_iso = datetime.now(UTC).isoformat()

        # 1-4. Company, Role, Summary, Skills
        company = job.company
        role = job.title
        jd_summary = (
            job.description[:300] + "..." if job.description and len(job.description) > 300 else (
                job.description or f"Design Verification role at {company} targeting entry-level semiconductor verification."
            )
        )
        skills = job.skills or ["SystemVerilog", "UVM", "Verilog", "AXI", "CDC"]

        # 5-7. Historical, Repeated, Missed Questions
        matched_qs = self.career_repo.get_questions_for_job(job)
        repeated_qs = [q for q in matched_qs if q.times_asked >= 2]
        missed_qs = [q for q in matched_qs if q.was_correct is False]

        # 8. Weak Areas
        active_weak_areas = self.career_repo.list_weak_areas(resolved=False)
        job_weak_areas = [
            w for w in active_weak_areas
            if any(s.lower() in w.topic.lower() or w.topic.lower() in s.lower() for s in skills)
        ] or active_weak_areas[:3]

        # 9. Important Concepts
        concepts: list[KnowledgeItem] = []
        for s in skills[:3]:
            concepts.extend(self.career_repo.get_knowledge_items_by_topic(s))

        # 10. Project Deep-Dive Questions
        proj_defense = self.authenticity_checker.generate_defense_questions_for_project(
            "AXI UVC Testbench & Async FIFO Verification", "UVM verification of AXI4 and dual clock FIFO"
        )
        project_deep_dive = [p.question_text for p in proj_defense]

        # 11. Coding Questions
        coding_qs = CURATED_DV_CODING_QUESTIONS

        # 12. Debugging Questions
        debugging_qs = [
            "Scoreboard error: Transaction count mismatch between generator and monitor. How do you trace drops?",
            "Simulation hang in run_phase: Objections not dropping. How do you locate the lingering sequence?",
            "X-propagation debug: Uninitialized register causing cascade failure in arithmetic unit.",
            "Assertion failure on AXI ready timeout: How do you isolate whether DUT or VIP is stalling?",
        ]

        # 13. HR Questions
        hr_qs = [
            f"Why do you want to join {company} specifically?",
            "Walk me through your transition from academic theory to hands-on verification.",
            "Describe a time you received critical code review feedback and how you adapted.",
            "Where do you see your verification career in 3 years (e.g. subsystem verification, VIP development)?",
        ]

        # 14. Resume-Specific Questions
        resume_qs = [
            "Explain the exact testbench architecture you built in your B.Tech final semester project.",
            "What code coverage percentage did your testbench achieve, and how did you close remaining holes with directed tests?",
            "How did you model protocol functional coverage in SystemVerilog?",
        ]

        # 15. Final Revision Checklist
        checklist = [
            "Verify all UVM phase execution orders (top-down vs bottom-up).",
            "Review 2-FF synchronizer MTBF and Gray code pointer conversion for Async FIFO.",
            "Practice writing SVA consecutive repetition [*n] and implication operators.",
            "Rehearse 2-minute elevator pitch on your primary UVC verification project.",
            "Confirm you understand AXI VALID/READY handshake and AWID/ARID transaction tagging.",
        ]

        # 16. Readiness Score & Gate Status
        readiness = self.assessment_engine.compute_job_readiness(job_id)

        # 17. Last-Minute Topics
        last_minute = [w.topic for w in job_weak_areas] or ["UVM RAL", "Clock Domain Crossing", "AXI Burst Calculations"]

        return InterviewPack(
            company=company,
            role=role,
            job_id=job_id,
            job_description_summary=jd_summary,
            required_skills=skills,
            historical_questions=matched_qs,
            frequently_repeated_questions=repeated_qs,
            previously_missed_questions=missed_qs,
            active_weak_areas=job_weak_areas,
            important_concepts=concepts[:5],
            project_deep_dive_questions=project_deep_dive,
            expected_coding_questions=coding_qs,
            expected_debugging_questions=debugging_qs,
            hr_questions=hr_qs,
            resume_specific_questions=resume_qs,
            final_revision_checklist=checklist,
            readiness_score=readiness.overall_readiness_score,
            readiness_level=readiness.readiness_level,
            last_minute_topics=last_minute,
            generated_at=now_iso,
        )
