import shutil

from app.agents.state import AgentState
from app.sandbox.runner import apply_patch, run_tests
from app.tracing import node_span


def verify(state: AgentState) -> dict:
    with node_span(state, "verify") as span:
        try:
            workdir = apply_patch(state.repo_path, state.patch)
        except ValueError as e:
            span.update(output={"passed": False})
            return {"passed": False, "test_output": str(e)}

        try:
            passed, output = run_tests(workdir)
        finally:
            shutil.rmtree(workdir, ignore_errors=True)

        span.update(output={"passed": passed})
    return {"passed": passed, "test_output": output}
