import argparse
import sys

from app.agents.graph_flow import build_graph
from app.agents.state import AgentState
from app.graph.embeddings import build_context
from app.tracing import traced_run


def fix(args) -> int:
    with open(args.trace_file) as f:
        trace = f.read()

    context = build_context(args.repo, trace)
    if not context:
        print("warning: call graph retrieval found no relevant functions - "
              "check --repo points at the code the trace came from", file=sys.stderr)

    state = AgentState(trace=trace, repo_path=args.repo, context=context, model=args.model)
    result = traced_run(build_graph(), state)

    if result["passed"]:
        print(f"fixed on attempt {result['attempt']}/{state.max_attempts}\n")
        print(result["patch"])
        return 0

    print(f"gave up after {result['attempt']} attempt(s)\n", file=sys.stderr)
    print(result.get("test_output", ""), file=sys.stderr)
    return 1


def main():
    parser = argparse.ArgumentParser(prog="autoheal")
    sub = parser.add_subparsers(dest="command", required=True)

    fix_p = sub.add_parser("fix", help="diagnose and patch a bug from a captured test failure")
    fix_p.add_argument("trace_file", help="path to a file with the pytest failure output / traceback")
    fix_p.add_argument("--repo", required=True, help="path to the repo the trace was captured from")
    fix_p.add_argument("--model", default=None, help="override the default Groq model for this run")

    args = parser.parse_args()
    sys.exit(fix(args) if args.command == "fix" else 1)


if __name__ == "__main__":
    main()
