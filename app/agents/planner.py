from app.agents.state import AgentState


def plan(state: AgentState) -> dict:
    # real LLM call wired in stage 5
    return {"plan": f"stub plan based on diagnosis: {state.diagnosis}"}
