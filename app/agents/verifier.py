from app.agents.state import AgentState


def verify(state: AgentState) -> dict:
    # real Docker sandbox run wired in stage 7 - stubbed to pass on the
    # 2nd attempt so the retry loop has something to exercise
    passed = state.attempt >= 2
    output = "stub: all tests passed" if passed else f"stub: tests still failing on attempt {state.attempt}"
    return {"passed": passed, "test_output": output}
