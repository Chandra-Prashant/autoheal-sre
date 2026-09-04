from langchain_core.messages import SystemMessage, HumanMessage

from app.config import GROQ_MODEL, get_llm
from app.agents.state import AgentState
from app.tracing import log_usage, node_span

SYSTEM = (
    "You are a senior Python engineer diagnosing a test failure. "
    "Given a stack trace and the relevant source code, explain the root "
    "cause in a few sentences. Be specific about which function and line "
    "is at fault and why. Do not propose a fix yet, just diagnose."
)


def diagnose(state: AgentState) -> dict:
    code_context = "\n\n".join(state.context) or "(no code context retrieved)"
    prompt = f"Stack trace:\n{state.trace}\n\nRelevant code:\n{code_context}"

    model = state.model or GROQ_MODEL
    llm = get_llm(model=model)
    with node_span(state, "diagnose", as_type="generation") as gen:
        resp = llm.invoke([SystemMessage(content=SYSTEM), HumanMessage(content=prompt)])
        log_usage(gen, resp, model)
    return {"diagnosis": resp.content}
