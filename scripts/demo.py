import argparse
import os
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.sandbox.runner import capture_trace
from scripts.seed_bugs import load_definitions, seed

DEFAULT_BUG = "01-moving-average-off-by-one"


def main():
    parser = argparse.ArgumentParser(description="seed a known bug and run the autoheal CLI against it - for demo recording")
    parser.add_argument("--bug", default=DEFAULT_BUG, help="bug id from evals/bugs/definitions.json (default: %(default)s)")
    args = parser.parse_args()

    bugs = {b["id"]: b for b in load_definitions()}
    if args.bug not in bugs:
        raise SystemExit(f"no bug with id {args.bug!r} - see evals/bugs/definitions.json")
    bug = bugs[args.bug]

    print(f"seeding {bug['id']}...")
    repo_path = seed(bug)

    print("capturing the real test failure:\n")
    trace = capture_trace(repo_path, bug["test_target"])
    print(trace)

    with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False) as f:
        f.write(trace)
        trace_file = f.name

    print(f"running: autoheal fix {trace_file} --repo {repo_path}\n")
    # stdout is fully buffered once it's not a tty (e.g. piped to a log or a
    # screen recorder) - flush so the prints above land before the child's
    sys.stdout.flush()
    subprocess.run(["autoheal", "fix", trace_file, "--repo", repo_path])


if __name__ == "__main__":
    main()
