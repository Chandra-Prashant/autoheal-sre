from langchain_core.messages import SystemMessage, HumanMessage

from app.config import get_llm
from app.agents.state import AgentState

SYSTEM = (
    "You are a senior Python engineer planning a fix for a diagnosed bug. "
    "Given the diagnosis and the relevant source code, write a short, "
    "concrete plan: which function(s) to change and what the change should "
    "do. This is a plan, not a diff - no code yet."
)


def plan(state: AgentState) -> dict:
    code_context = "\n\n".join(state.context) or "(no code context retrieved)"
    prompt = f"Diagnosis:\n{state.diagnosis}\n\nRelevant code:\n{code_context}"

    llm = get_llm()
    resp = llm.invoke([SystemMessage(content=SYSTEM), HumanMessage(content=prompt)])
    return {"plan": resp.content}
