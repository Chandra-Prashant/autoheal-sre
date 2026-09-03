import os

import docker
import pytest

from app.sandbox.runner import apply_patch, run_tests

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


def test_apply_patch_fixes_the_file_in_a_copy():
    workdir = apply_patch(FIXTURE, FIX_PATCH)
    try:
        with open(os.path.join(workdir, "calc.py")) as f:
            assert "a + b" in f.read()
        # original fixture is untouched
        with open(os.path.join(FIXTURE, "calc.py")) as f:
            assert "a - b" in f.read()
    finally:
        import shutil
        shutil.rmtree(workdir, ignore_errors=True)


def test_apply_patch_rejects_a_bad_patch():
    with pytest.raises(ValueError):
        apply_patch(FIXTURE, "not a real diff")


def test_run_tests_fails_on_the_buggy_repo():
    passed, output = run_tests(FIXTURE)
    assert passed is False
    assert "assert" in output.lower()


def test_run_tests_passes_after_patching():
    workdir = apply_patch(FIXTURE, FIX_PATCH)
    try:
        passed, output = run_tests(workdir)
        assert passed is True
    finally:
        import shutil
        shutil.rmtree(workdir, ignore_errors=True)
