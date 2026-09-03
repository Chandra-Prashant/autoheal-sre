from langgraph.graph import END, StateGraph

from app.agents.coder import code
from app.agents.diagnostic import diagnose
from app.agents.planner import plan
from app.agents.state import AgentState
from app.agents.verifier import verify


def _route_after_verify(state: AgentState) -> str:
    if state.passed or state.attempt >= state.max_attempts:
        return END
    return "code"


def build_graph():
    g = StateGraph(AgentState)
    g.add_node("diagnose", diagnose)
    g.add_node("plan", plan)
    g.add_node("code", code)
    g.add_node("verify", verify)

    g.set_entry_point("diagnose")
    g.add_edge("diagnose", "plan")
    g.add_edge("plan", "code")
    g.add_edge("code", "verify")
    g.add_conditional_edges("verify", _route_after_verify, {"code": "code", END: END})

    return g.compile()
