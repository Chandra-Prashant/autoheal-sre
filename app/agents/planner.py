from langchain_core.messages import SystemMessage, HumanMessage

from app.config import GROQ_MODEL, get_llm
from app.agents.state import AgentState
from app.tracing import log_usage, node_span

SYSTEM = (
    "You are a senior Python engineer planning a fix for a diagnosed bug. "
    "Given the diagnosis and the relevant source code, write a short, "
    "concrete plan: which function(s) to change and what the change should "
    "do. This is a plan, not a diff - no code yet."
)


def plan(state: AgentState) -> dict:
    code_context = "\n\n".join(state.context) or "(no code context retrieved)"
    prompt = f"Diagnosis:\n{state.diagnosis}\n\nRelevant code:\n{code_context}"

    model = state.model or GROQ_MODEL
    llm = get_llm(model=model)
    with node_span(state, "plan", as_type="generation") as gen:
        resp = llm.invoke([SystemMessage(content=SYSTEM), HumanMessage(content=prompt)])
        log_usage(gen, resp, model)
    return {"plan": resp.content}
