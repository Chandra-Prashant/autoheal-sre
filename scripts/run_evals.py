import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.agents.graph_flow import build_graph
from app.agents.state import AgentState
from app.config import GROQ_MODEL
from app.graph.call_graph import CallGraph
from app.graph.embeddings import FunctionIndex, retrieve_context
from scripts.seed_bugs import load_definitions, seed

RESULTS_PATH = os.path.join(os.path.dirname(__file__), "..", "evals", "results.json")


def capture_trace(repo_path: str, test_target: str) -> str:
    result = subprocess.run(
        ["python", "-m", "pytest", "-q", "-p", "no:cacheprovider", test_target],
        cwd=repo_path, capture_output=True, text=True,
    )
    return result.stdout + result.stderr


def build_context(repo_path: str, trace: str) -> list[str]:
    # exclude the test files themselves - we want the call graph over the
    # application code the bug lives in, not the test suite
    paths = [os.path.join(repo_path, f) for f in os.listdir(repo_path)
             if f.endswith(".py") and not f.startswith("test_")]

    graph = CallGraph()
    graph.build_from_files(paths)

    chroma_dir = tempfile.mkdtemp(prefix="autoheal-eval-chroma-")
    try:
        index = FunctionIndex(path=chroma_dir)
        index.index_graph(graph)
        nodes = retrieve_context(index, graph, trace, k=3, depth=1)
    finally:
        shutil.rmtree(chroma_dir, ignore_errors=True)

    # basename only - the sandbox applies the patch with the flat repo dir
    # as cwd, so a diff header with the full local path won't resolve
    return [f"{graph.g.nodes[n]['qualname']} ({os.path.basename(graph.g.nodes[n]['file'])}):\n{graph.g.nodes[n]['source']}"
            for n in nodes]


def run_bug(bug: dict, model: str) -> dict:
    repo_path = seed(bug)
    trace = capture_trace(repo_path, bug["test_target"])
    context = build_context(repo_path, trace)

    state = AgentState(trace=trace, repo_path=repo_path, context=context, model=model)
    result = build_graph().invoke(state)

    return {
        "id": bug["id"],
        "category": bug["category"],
        "passed": result["passed"],
        "attempts": result["attempt"],
        "pass_at_1": bool(result["passed"] and result["attempt"] == 1),
        "pass_at_3": bool(result["passed"]),
    }


def _write_results(results: list[dict], model: str) -> tuple[float, float]:
    # results.json holds one run per model (keyed by model name) so a run
    # with a different model never clobbers another model's baseline - only
    # a re-run of the SAME model replaces its own entry
    pass_at_1 = sum(r["pass_at_1"] for r in results) / len(results)
    pass_at_3 = sum(r["pass_at_3"] for r in results) / len(results)
    run = {"model": model, "pass_at_1": pass_at_1, "pass_at_3": pass_at_3, "results": results}

    if os.path.exists(RESULTS_PATH):
        with open(RESULTS_PATH) as f:
            data = json.load(f)
    else:
        data = {"runs": []}

    data["runs"] = [r for r in data.get("runs", []) if r.get("model") != model] + [run]

    with open(RESULTS_PATH, "w") as f:
        json.dump(data, f, indent=2)

    return pass_at_1, pass_at_3


def main():
    parser = argparse.ArgumentParser(description="run the full autoheal loop against every seeded bug")
    parser.add_argument("--model", default=GROQ_MODEL, help="Groq model to use (default: %(default)s)")
    args = parser.parse_args()

    bugs = load_definitions()
    results = []
    for bug in bugs:
        print(f"running {bug['id']}...", flush=True)
        r = run_bug(bug, args.model)
        print(f"  -> passed={r['passed']} attempts={r['attempts']}", flush=True)
        results.append(r)
        # write after every bug so a crash mid-run (e.g. a rate limit) doesn't
        # throw away everything done so far, and pace requests between bugs
        # to stay under Groq's free-tier tokens-per-minute limit
        _write_results(results, args.model)
        time.sleep(3)

    pass_at_1, pass_at_3 = _write_results(results, args.model)
    print(f"\nmodel: {args.model}")
    print(f"pass@1: {pass_at_1:.2f}  pass@3: {pass_at_3:.2f}")


if __name__ == "__main__":
    main()
