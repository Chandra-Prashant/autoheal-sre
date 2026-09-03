import os

import docker
import pytest

from app.agents.state import AgentState
from app.agents.verifier import verify

FIXTURE = os.path.join(os.path.dirname(__file__), "..", "fixtures", "buggy_repo")

FIX_PATCH = """--- a/calc.py
+++ b/calc.py
@@ -1,2 +1,2 @@
 def add(a, b):
-    return a - b
+    return a + b
"""


def _docker_available() -> bool:
    try:
        docker.from_env().ping()
        return True
    except Exception:
        return False


pytestmark = pytest.mark.skipif(not _docker_available(), reason="requires a running Docker daemon")


def test_verify_fails_with_the_buggy_patch():
    state = AgentState(trace="boom", repo_path=FIXTURE, patch="--- a/calc.py\n+++ b/calc.py\n")
    result = verify(state)
    assert result["passed"] is False


def test_verify_passes_with_a_correct_patch():
    state = AgentState(trace="boom", repo_path=FIXTURE, patch=FIX_PATCH)
    result = verify(state)
    assert result["passed"] is True


def test_verify_reports_a_malformed_patch_without_crashing():
    state = AgentState(trace="boom", repo_path=FIXTURE, patch="not a real diff")
    result = verify(state)
    assert result["passed"] is False
    assert "patch failed to apply" in result["test_output"]
