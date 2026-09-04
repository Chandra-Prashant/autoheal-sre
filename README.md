# autoheal-sre

A self-healing code repair agent, built as a college project. You give it a
Python test failure (a stack trace, or a failing pytest node), and it tries
to fix the actual bug: it parses the codebase with tree-sitter to build a
real call graph (not naive text chunking), retrieves the functions actually
relevant to the failure, proposes a patch through a small multi-agent
LangGraph loop, runs that patch in an isolated Docker sandbox, and only
considers it a fix once the tests pass for real. If they don't pass, the
real test output gets fed back to the agent and it tries again, up to 3
times.

This is intentionally scoped down from a "real startup" version of this
idea. Python only, one in-memory call graph, one local vector store, no
async task queue. See **Non-goals** below for what was deliberately left
out.

## How it works

```
trace  ->  diagnose  ->  plan  ->  code  ->  verify  ->  (pass? -> PR : retry code, up to 3x)
```

- **diagnose** (`app/agents/diagnostic.py`) - given the trace and retrieved
  code context, asks the LLM to explain the root cause. No fix yet.
- **plan** (`app/agents/planner.py`) - given the diagnosis, asks for a short,
  concrete plan: which function(s) to touch and what should change.
- **code** (`app/agents/coder.py`) - turns the plan into a unified diff. On
  a retry, it also gets the previous patch and the real stderr from the
  failed sandbox run, so it's not guessing blind a second time.
- **verify** (`app/agents/verifier.py` + `app/sandbox/runner.py`) - applies
  the patch to a throwaway copy of the repo and runs its tests inside a
  Docker container with no network, a 512MB memory cap, a read-only
  filesystem (except the working directory), and a 30 second timeout.
  Whatever happens in there, happens in there.
- If verification fails and there are attempts left, `test_output` flows
  back into **code** and it tries again. After 3 failed attempts, or on
  success, the loop ends.
- **PR generation** (`app/github/pr.py`) - once a patch passes, it can be
  pushed to a branch and opened as a real PR via PyGithub. This part is
  built and tested but not yet wired to an automatic trigger (see
  *Current state* below).

The retrieval step (`app/graph/`) is the part I actually care about most:
`ast_parser.py` walks a tree-sitter AST to find real function and class
boundaries, `call_graph.py` builds a NetworkX graph of who calls whom, and
`embeddings.py` does semantic search over that graph with Chroma, then
expands the top hits with their direct callers/callees. So if a trace
points at function A, and A's actual bug lives in a function B that A
calls, the agent gets B's source too - not just A in isolation. This is
tested directly (see the eval bugs below, bug 04 in particular).

## Project structure

```
app/
  main.py            FastAPI app, currently just a /health endpoint
  config.py           env var loading, the Groq client factory
  graph/
    ast_parser.py      tree-sitter function/class extraction
    call_graph.py       NetworkX call graph build + query
    embeddings.py        Chroma indexing + call-graph-aware retrieval
  agents/
    state.py            AgentState (pydantic)
    diagnostic.py, planner.py, coder.py, verifier.py
    graph_flow.py        LangGraph wiring, the retry loop
  sandbox/
    runner.py            Docker SDK container lifecycle
    Dockerfile            the sandbox image (python:3.11-slim + pytest)
  github/
    pr.py                PyGithub PR creation
evals/
  bugs/
    sample_repo/         a small gold-standard utils library
    definitions.json      15 seeded bugs as find/replace transforms
    seeded/               generated bug copies (gitignored, regenerate with seed_bugs.py)
  results.json          pass@1 / pass@3 from the last full eval run
scripts/
  seed_bugs.py           seeds bugs from definitions.json into evals/bugs/seeded/
  run_evals.py            runs the full loop against every seeded bug, writes results.json
tests/
  mirrors app/, plus tests/fixtures and tests/scripts for the eval tooling
```

## Setup

```
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # fill in the keys below
```

`.env` needs:

- `GROQ_API_KEY` - used for every LLM call, via `langchain-groq`. The model
  is `openai/gpt-oss-120b` (see *Current state*, this wasn't the original
  plan).
- `GITHUB_TOKEN` - a **classic** PAT with the `repo` scope, for PR creation.
  See *Current state* for why it has to be classic, not fine-grained.
- `LANGFUSE_PUBLIC_KEY` / `LANGFUSE_SECRET_KEY` - optional. If set, every
  graph run gets traced (node name, model, token usage, latency per node).
  If unset, the Langfuse client just logs an auth warning and no-ops - the
  agent loop still runs fine without them.

You also need a running Docker daemon (Docker Desktop, or equivalent) -
the sandbox and most of the eval tooling won't work without it. First run
builds a small `autoheal-sandbox:latest` image (python:3.11-slim + pytest).

## Running it

```
uvicorn app.main:app --reload
```

gets you `GET /health` -> `{"status": "ok"}`. That's the only endpoint so
far - there's no webhook or trigger route wired up yet that runs the full
diagnose-plan-code-verify loop over HTTP. Right now the loop is driven
directly in Python, either through the eval harness (`scripts/run_evals.py`)
or by building an `AgentState` and calling `app.agents.graph_flow.build_graph()
.invoke(...)` yourself. Wiring a real trigger endpoint is the obvious next
step but wasn't part of this pass.

## Tests

```
pytest
```

Runs the test suite for the tool itself (`tests/`, mirrors `app/`). A few
things to know:

- `tests/fixtures/` and `evals/bugs/seeded/` are excluded from collection
  (see `pyproject.toml`) - they're target repos meant to be fed *into* the
  pipeline, not run as this project's own tests.
- Most agent tests mock the LLM so they're fast and don't burn API quota.
  A handful are real integration tests that skip themselves automatically
  if `GROQ_API_KEY` is missing or Docker isn't reachable
  (`test_fixes_a_real_bug_end_to_end` in particular runs the whole loop
  for real, against a real sandboxed bug).

## Eval set

`evals/bugs/sample_repo/` is a small hand-written utils library (list,
string, dict, stack, math, flow-control, and validation helpers) with 15
bugs seeded into it via `evals/bugs/definitions.json`, split across four
categories: off-by-one, unbound variable, wrong exception type, and missing
null check.

One bug (04) is deliberately a cross-function case: `paginate` calls
`chunk_list` to do the actual splitting, and the seeded bug lives entirely
in `chunk_list`. The failing test names `paginate`, and `paginate`'s own
code is completely correct - the only way to fix it right is to pull
`chunk_list`'s source in through the call graph, which is exactly what
`retrieve_context()` is supposed to do. This is the closest thing this
project has to a proof that the AST/call-graph retrieval is actually doing
something useful, rather than just being a fancier way to paste one
function into a prompt.

To seed the bugs and run the full loop against all of them:

```
python scripts/seed_bugs.py          # writes evals/bugs/seeded/<bug-id>/
python scripts/run_evals.py          # runs the loop against each, writes evals/results.json
```

Each run captures the *real* pytest failure output as the trace (not a
hand-written string), builds a call graph + Chroma index over just that
seeded copy, retrieves context the same way the real pipeline would, and
records whether the agent got it right on the first attempt (`pass@1`) or
within the 3-attempt budget (`pass@3`).

Last full run: **pass@1: 0.40, pass@3: 0.73** (6/15 and 11/15 respectively).
See `evals/results.json` for the per-bug breakdown.

## Current state / known limitations

Being upfront about where the rough edges are:

- **Model swap.** The plan was `llama-3.3-70b-versatile` via Groq. That
  model isn't available on this project's API key (404 `model_not_found`),
  so every agent uses `openai/gpt-oss-120b` instead. See `app/config.py`.
- **GitHub token gotcha.** A fine-grained PAT with "Pull requests: Read and
  write" granted still 403'd on `create_pull` (confirmed with a raw API
  call, not a PyGithub bug). A classic PAT with the `repo` scope worked
  immediately. If PR creation is 403ing, this is why.
- **The coder doesn't always produce a valid diff.** The model occasionally
  emits a unified diff without real line numbers in the hunk headers (a
  bare `@@` instead of `@@ -12,7 +12,8 @@`), which `patch -p1` flatly
  rejects. The system prompt is explicit about this, with a worked example,
  and it helps a lot, but it doesn't fully eliminate it - this is most of
  why `pass@1` is meaningfully lower than `pass@3`.
- **Groq's free tier has a real daily token cap** (200k TPD as of writing),
  and running the full 15-bug eval a few times in one day is enough to hit
  it. There's no queuing or backoff-across-days here, it just fails loudly
  when the budget's gone.
- **No trigger endpoint yet.** `app/main.py` only exposes `/health`. The
  loop runs fine end-to-end, but only via the eval harness or by calling
  `graph_flow.build_graph()` directly - there's no webhook that takes a CI
  failure and runs the whole thing automatically.
- **Langfuse tracing covers node name, model, tokens, and latency per
  node**, grouped under one trace per graph run. The one wrinkle: LangGraph
  runs nodes on a worker thread pool, which drops Langfuse's ambient
  context, so each node attaches to its parent trace explicitly via ids
  stashed on `AgentState` (see `app/tracing.py`) rather than relying on
  `@observe`.
- **PR generation isn't triggered automatically.** `open_pr()` works and is
  tested (including a real PR opened against a throwaway repo during
  development), but nothing in the loop calls it yet - right now you'd call
  it yourself after a `verify` success.

## Non-goals

Explicitly out of scope for this project, mentioned here in case it's
useful context for anyone reading the code and wondering why something
"obvious" is missing:

- Multi-language support (Python only)
- Neo4j or any graph database server (the call graph is in-memory NetworkX)
- Celery + Redis / any async task queue
- A full Ragas-style eval harness (`evals/results.json` is deliberately
  simple)
- A Streamlit/Next.js dashboard (CLI + the FastAPI docs page is the plan
  for a demo, once there's a trigger endpoint to demo)
