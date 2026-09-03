import os

import pytest

from scripts.seed_bugs import load_definitions, seed


def test_every_bug_definition_applies_cleanly():
    # guards definitions.json against drifting out of sync with sample_repo -
    # each find-string must match the corresponding file exactly once
    for bug in load_definitions():
        dest = seed(bug)
        with open(os.path.join(dest, bug["file"])) as f:
            src = f.read()
        assert bug["replace"] in src
        assert bug["find"] not in src


def test_seed_raises_when_find_string_is_missing():
    bad_bug = {
        "id": "not-a-real-bug",
        "file": "math_utils.py",
        "find": "this text does not appear anywhere",
        "replace": "irrelevant",
    }
    with pytest.raises(ValueError):
        seed(bad_bug)
