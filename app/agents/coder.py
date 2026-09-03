import re

from langchain_core.messages import SystemMessage, HumanMessage

from app.config import get_llm
from app.agents.state import AgentState

SYSTEM = (
    "You are a senior Python engineer implementing a planned bug fix. "
    "Given the diagnosis, the plan, and the relevant source code, output "
    "ONLY a unified diff that implements the plan - no explanation, no "
    "markdown fences, just the diff.\n\n"
    "The diff MUST be in strict unified diff format, applicable with "
    "`patch -p1`:\n"
    "- file headers: `--- a/path/to/file.py` and `+++ b/path/to/file.py`\n"
    "- hunk headers MUST include real line numbers and counts, e.g. "
    "`@@ -12,7 +12,8 @@` - never a bare `@@`\n"
    "- unchanged context lines start with a single space, removed lines "
    "with `-`, added lines with `+`\n"
    "- include a couple of unchanged context lines around each change so "
    "the hunk applies unambiguously\n\n"
    "Example of a correctly formatted hunk:\n"
    "--- a/calc.py\n"
    "+++ b/calc.py\n"
    "@@ -1,2 +1,2 @@\n"
    " def add(a, b):\n"
    "-    return a - b\n"
    "+    return a + b\n"
)

FENCE_RE = re.compile(r"^```(?:diff|patch)?\n(.*)\n```$", re.DOTALL)


def _strip_fences(text: str) -> str:
    text = text.strip()
    match = FENCE_RE.match(text)
    return match.group(1) if match else text


def code(state: AgentState) -> dict:
    code_context = "\n\n".join(state.context) or "(no code context retrieved)"
    parts = [f"Diagnosis:\n{state.diagnosis}", f"Plan:\n{state.plan}", f"Relevant code:\n{code_context}"]
    if state.attempt > 0:
        # feed the real sandbox stderr from the last failed attempt back in
        parts.append(f"Previous patch:\n{state.patch}")
        parts.append(f"That patch failed verification with this output:\n{state.test_output}\nFix it.")
    prompt = "\n\n".join(parts)

    llm = get_llm(model=state.model)
    resp = llm.invoke([SystemMessage(content=SYSTEM), HumanMessage(content=prompt)])
    return {"patch": _strip_fences(resp.content), "attempt": state.attempt + 1}
