from app.agents.state import AgentState


def code(state: AgentState) -> dict:
    # real LLM call wired in stage 6 - on a retry, state.test_output holds
    # the stderr from the previous failed attempt so the patch can improve
    return {"patch": f"stub patch, attempt {state.attempt + 1}", "attempt": state.attempt + 1}
