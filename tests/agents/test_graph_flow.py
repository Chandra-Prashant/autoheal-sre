from app.agents.graph_flow import build_graph
from app.agents.state import AgentState


def test_runs_end_to_end_and_retries_until_pass():
    graph = build_graph()
    result = graph.invoke(AgentState(trace="AssertionError: x != y", repo_path="/tmp/repo"))

    assert result["diagnosis"]
    assert result["plan"]
    assert result["passed"] is True
    # verify's stub passes on attempt 2, so code must have run twice
    assert result["attempt"] == 2


def test_stops_at_max_attempts_if_never_passing():
    graph = build_graph()
    state = AgentState(trace="boom", repo_path="/tmp/repo", max_attempts=1)
    result = graph.invoke(state)

    assert result["passed"] is False
    assert result["attempt"] == 1
