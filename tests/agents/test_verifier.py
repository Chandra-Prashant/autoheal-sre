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


requires_docker = pytest.mark.skipif(not _docker_available(), reason="requires a running Docker daemon")


@requires_docker
def test_verify_fails_with_the_buggy_patch():
    state = AgentState(trace="boom", repo_path=FIXTURE, patch="--- a/calc.py\n+++ b/calc.py\n")
    result = verify(state)
    assert result["passed"] is False


@requires_docker
def test_verify_passes_with_a_correct_patch():
    state = AgentState(trace="boom", repo_path=FIXTURE, patch=FIX_PATCH)
    result = verify(state)
    assert result["passed"] is True


@requires_docker
def test_verify_reports_a_malformed_patch_without_crashing():
    state = AgentState(trace="boom", repo_path=FIXTURE, patch="not a real diff")
    result = verify(state)
    assert result["passed"] is False
    assert "patch failed to apply" in result["test_output"]


@requires_docker
def test_verify_fails_when_the_patch_fixes_one_test_but_breaks_another(tmp_path):
    # add() has the same off-by-sign bug as the shared fixture, but this repo
    # also has an unrelated, already-passing test (double()) that the patch
    # below "fixes" add() while accidentally breaking - the full suite should
    # catch that, not just the originally-failing add() test
    (tmp_path / "calc.py").write_text(
        "def add(a, b):\n"
        "    return a - b\n"
        "\n"
        "def double(n):\n"
        "    return n * 2\n"
    )
    (tmp_path / "test_calc.py").write_text(
        "from calc import add, double\n"
        "\n"
        "def test_add():\n"
        "    assert add(2, 3) == 5\n"
        "\n"
        "def test_double():\n"
        "    assert double(4) == 8\n"
    )
    patch = (
        "--- a/calc.py\n"
        "+++ b/calc.py\n"
        "@@ -1,5 +1,5 @@\n"
        " def add(a, b):\n"
        "-    return a - b\n"
        "+    return a + b\n"
        " \n"
        " def double(n):\n"
        "-    return n * 2\n"
        "+    return n * 3\n"
    )

    state = AgentState(trace="boom", repo_path=str(tmp_path), patch=patch)
    result = verify(state)

    assert result["passed"] is False
    assert "test_double" in result["test_output"]


def test_verify_rejects_a_patch_that_modifies_a_test_file():
    patch = (
        "--- a/test_calc.py\n"
        "+++ b/test_calc.py\n"
        "@@ -1,2 +1,2 @@\n"
        " def test_add():\n"
        "-    assert add(2, 3) == 5\n"
        "+    assert add(2, 3) == -1\n"
    )
    state = AgentState(trace="boom", repo_path=FIXTURE, patch=patch)

    result = verify(state)

    assert result["passed"] is False
    assert "test_calc.py" in result["test_output"]
    assert "source files" in result["test_output"]


def test_verify_rejects_a_patch_that_touches_a_test_file_among_others():
    patch = (
        "--- a/calc.py\n"
        "+++ b/calc.py\n"
        "@@ -1,2 +1,2 @@\n"
        " def add(a, b):\n"
        "-    return a - b\n"
        "+    return a + b\n"
        "--- a/test_calc.py\n"
        "+++ b/test_calc.py\n"
        "@@ -1,2 +1,2 @@\n"
        " def test_add():\n"
        "-    assert add(2, 3) == 5\n"
        "+    assert add(2, 3) == 5  # noqa\n"
    )
    state = AgentState(trace="boom", repo_path=FIXTURE, patch=patch)

    result = verify(state)

    assert result["passed"] is False
    assert "test_calc.py" in result["test_output"]
