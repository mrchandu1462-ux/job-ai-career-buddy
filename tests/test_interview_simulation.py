"""Tests for multi-stage interview simulations and project authenticity defense."""

import pytest

from app.career.repository import CareerRepository
from app.career.simulation import (
    InterviewSimulationEngine,
    ProjectAuthenticityChecker,
    SimulationStage,
)
from app.db.connection import get_db


@pytest.fixture
def db_conn():
    with get_db(":memory:") as conn:
        yield conn


@pytest.fixture
def career_repo(db_conn):
    return CareerRepository(db_conn)


@pytest.fixture
def sim_engine(career_repo):
    return InterviewSimulationEngine(career_repo)


@pytest.fixture
def authenticity_checker(career_repo):
    return ProjectAuthenticityChecker(career_repo)


def test_project_authenticity_defense_generation(authenticity_checker):
    """Test generating deep-dive defense questions for candidate resume projects."""
    # AXI project
    axi_qs = authenticity_checker.generate_defense_questions_for_project(
        "AXI4 UVC VIP Development", "Built an AXI4 master agent and scoreboard in UVM."
    )
    assert len(axi_qs) >= 4
    assert any("Sequence vs Sequencer" in q.focus_aspect for q in axi_qs)
    assert any("Scoreboard & Transaction Matching" in q.focus_aspect for q in axi_qs)

    # Async FIFO project
    fifo_qs = authenticity_checker.generate_defense_questions_for_project(
        "Dual Clock Async FIFO Verification", "Verified CDC FIFO using SVA and constrained random."
    )
    assert len(fifo_qs) >= 3
    assert any("Full Condition Detection" in q.focus_aspect for q in fifo_qs)


def test_interview_simulation_full_flow(sim_engine, career_repo):
    """Test running a sequential multi-stage mock interview simulation."""
    stages = [
        SimulationStage.HR,
        SimulationStage.DIGITAL_DESIGN,
        SimulationStage.SYSTEM_VERILOG,
        SimulationStage.UVM,
    ]

    session = sim_engine.start_simulation(
        company="Intel",
        role="Design Verification Engineer",
        stages=stages,
    )

    assert session.session_id.startswith("sim-")
    assert session.is_completed is False
    assert len(session.stages) == 4

    # Stage 1: HR
    q1 = sim_engine.get_next_question_for_stage(session)
    assert "introduce yourself" in q1.lower()
    sim_engine.submit_turn_response(
        session,
        user_response="I am a 2025 graduate focused on semiconductor verification.",
        was_correct=True,
    )

    # Stage 2: Digital Design
    q2 = sim_engine.get_next_question_for_stage(session)
    assert "setup time" in q2.lower()
    sim_engine.submit_turn_response(
        session,
        user_response="Setup time is the minimum time data must be stable before the active clock edge.",
        was_correct=True,
    )

    # Stage 3: SystemVerilog - Candidate misses
    q3 = sim_engine.get_next_question_for_stage(session)
    assert "shallow copy" in q3.lower()
    sim_engine.submit_turn_response(
        session,
        user_response="I don't recall the deep copy syntax.",
        was_correct=False,
    )

    # Verify that the missed SV turn created a weak area
    weak_areas = career_repo.list_weak_areas(topic="SystemVerilog")
    assert len(weak_areas) >= 1

    # Stage 4: UVM
    q4 = sim_engine.get_next_question_for_stage(session)
    assert "factory" in q4.lower()
    sim_engine.submit_turn_response(
        session,
        user_response="Factory override replaces component types dynamically at runtime.",
        was_correct=True,
    )

    # Check simulation completion
    assert session.is_completed is True
    assert session.overall_score == 75.0
    assert len(session.turns) == 4
