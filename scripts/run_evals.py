import argparse
import json
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.agents.graph_flow import build_graph
from app.agents.state import AgentState
from app.config import GROQ_MODEL
from app.graph.embeddings import build_context
from app.sandbox.runner import capture_trace
from app.tracing import traced_run
from langfuse import get_client
from scripts.seed_bugs import load_definitions, seed

RESULTS_PATH = os.path.join(os.path.dirname(__file__), "..", "evals", "results.json")


def run_bug(bug: dict, model: str) -> dict:
    repo_path = seed(bug)
    trace = capture_trace(repo_path, bug["test_target"])
    context = build_context(repo_path, trace)

    state = AgentState(trace=trace, repo_path=repo_path, context=context, model=model)
    result = traced_run(build_graph(), state)

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

    # the langfuse client batches spans in the background - flush before the
    # short-lived script process exits or the last run's traces get dropped
    get_client().flush()


if __name__ == "__main__":
    main()
