from app.agents.state import AgentState


def diagnose(state: AgentState) -> dict:
    # real LLM call wired in stage 5
    return {"diagnosis": f"stub diagnosis for: {state.trace[:80]}"}
