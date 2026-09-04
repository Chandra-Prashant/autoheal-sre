import os
import re
import shutil

from app.agents.state import AgentState
from app.sandbox.runner import apply_patch, run_tests
from app.tracing import node_span

# unified diff file headers look like "--- a/path/to/file.py" / "+++ b/path/to/file.py"
_DIFF_FILE_RE = re.compile(r"^(?:---|\+\+\+) [ab]/(.+)$", re.MULTILINE)


def _patched_files(patch: str) -> set[str]:
    return {m.group(1).strip() for m in _DIFF_FILE_RE.finditer(patch)}


def _is_test_file(path: str) -> bool:
    name = os.path.basename(path)
    parts = path.replace("\\", "/").split("/")
    return name.startswith("test_") or name.endswith("_test.py") or "tests" in parts


def verify(state: AgentState) -> dict:
    with node_span(state, "verify") as span:
        touched_tests = sorted(f for f in _patched_files(state.patch or "") if _is_test_file(f))
        if touched_tests:
            msg = (f"patch modifies test file(s): {', '.join(touched_tests)}. "
                   "The fix must only touch source files - tests cannot be changed to make them pass.")
            span.update(output={"passed": False, "rejected": "modifies_test_file"})
            return {"passed": False, "test_output": msg}

        try:
            workdir = apply_patch(state.repo_path, state.patch)
        except ValueError as e:
            span.update(output={"passed": False})
            return {"passed": False, "test_output": str(e)}

        try:
            # no test path given - runs the full suite, so a patch that fixes
            # the originally-failing test but breaks another one still fails
            passed, output = run_tests(workdir)
        finally:
            shutil.rmtree(workdir, ignore_errors=True)

        span.update(output={"passed": passed})
    return {"passed": passed, "test_output": output}
