import shutil

from app.agents.state import AgentState
from app.sandbox.runner import apply_patch, run_tests


def verify(state: AgentState) -> dict:
    try:
        workdir = apply_patch(state.repo_path, state.patch)
    except ValueError as e:
        return {"passed": False, "test_output": str(e)}

    try:
        passed, output = run_tests(workdir)
    finally:
        shutil.rmtree(workdir, ignore_errors=True)

    return {"passed": passed, "test_output": output}
