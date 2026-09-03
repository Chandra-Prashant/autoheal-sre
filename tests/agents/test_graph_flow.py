import os

import docker
import pytest
from langgraph.graph import END

from app.config import GROQ_API_KEY
from app.agents.graph_flow import build_graph, _route_after_verify
from app.agents.state import AgentState

FIXTURE = os.path.join(os.path.dirname(__file__), "..", "fixtures", "buggy_repo")


def test_route_after_verify_stops_when_passed():
    state = AgentState(trace="t", repo_path="x", passed=True, attempt=1, max_attempts=3)
    assert _route_after_verify(state) == END


def test_route_after_verify_stops_at_max_attempts():
    state = AgentState(trace="t", repo_path="x", passed=False, attempt=3, max_attempts=3)
    assert _route_after_verify(state) == END


def test_route_after_verify_retries_when_failing_under_cap():
    state = AgentState(trace="t", repo_path="x", passed=False, attempt=1, max_attempts=3)
    assert _route_after_verify(state) == "code"


def _live_infra_available() -> bool:
    if not GROQ_API_KEY:
        return False
    try:
        docker.from_env().ping()
        return True
    except Exception:
        return False


@pytest.mark.skipif(not _live_infra_available(), reason="requires a real GROQ_API_KEY and a running Docker daemon")
def test_fixes_a_real_bug_end_to_end():
    graph = build_graph()
    with open(os.path.join(FIXTURE, "calc.py")) as f:
        calc_src = f.read()

    state = AgentState(
        trace="test_calc.py::test_add FAILED - AssertionError: add(2, 3) returned -1, expected 5",
        repo_path=FIXTURE,
        context=[f"calc.py:\n{calc_src}"],
    )
    result = graph.invoke(state)

    assert result["diagnosis"]
    assert result["plan"]
    assert result["passed"] is True
    assert result["attempt"] <= result["max_attempts"]
