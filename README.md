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
  pushed to a branch and opened as a real PR via PyGithub. It's not
  automatic - in the demo UI (see *Running it*) this is gated behind an
  explicit "Approve & push" button, so a passing patch never gets pushed
  without a human looking at the diff first.

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
  main.py            FastAPI app: /health, /bugs, /fix (SSE), /pr, and /
  static/
    index.html          the one-page demo UI (plain HTML/JS, no build step)
  cli.py               autoheal fix CLI entry point (see pyproject.toml)
  config.py           env var loading, the Groq client factory
  tracing.py            Langfuse spans, threaded through AgentState
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
  demo.py                 seeds one bug and runs the autoheal CLI against it, for recording
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
- `GITHUB_REPO` - the repo the demo frontend's **Seeded bug** mode clones
  and seeds a bug into (`owner/repo`). Its default branch content needs to
  match `evals/bugs/sample_repo`, since seeding applies the same find/replace
  bug transform the eval harness uses - if the content doesn't line up,
  seeding fails loudly with a clear error instead of silently doing the
  wrong thing. It's also used to pre-fill the repo field in the frontend's
  **Custom** mode, but that's just a convenience default - Custom mode lets
  you type over it and point at any repo `GITHUB_TOKEN` can clone and push
  a branch to.
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

gets you `GET /health` and a one-page demo UI at `/` with two modes:

- **Seeded bug** - pick one of the 15 seeded bugs from the dropdown, hit
  "Run fix". `GITHUB_REPO` gets cloned fresh and the bug's find/replace
  transform is applied before the loop runs, same as `run_evals.py`.
- **Custom** - paste any `owner/name` repo and a trace/error you already
  have, hit "Fix it". No seeding step - the repo is cloned as-is and the
  pasted text is used directly as the trace. Useful for trying the loop
  against something other than the 15 seeded bugs, as long as the repo is
  one `GITHUB_TOKEN` can clone and push a branch to.

Both modes stream the same live progress (diagnose/plan/code/verify, one
event per node) and land on the same result view: a diff and an
"Approve & push" button on success, the last test output after 3 exhausted
attempts on failure. This is `app/static/index.html` talking to `GET /bugs`,
`GET /fix?bug_id=...` or `GET /fix?repo=...&trace=...` (server-sent events)
and `POST /pr` - there's still no general-purpose webhook that takes an
arbitrary CI failure over HTTP automatically, both modes are triggered by
hand from the UI.

Alternatively, drive the loop from the CLI:

```
pip install -e .
autoheal fix <trace-file> --repo <path-to-the-repo-the-trace-came-from>
```

`<trace-file>` is just a text file with a pytest failure / traceback in it
- copy-paste real pytest output, there's nothing special about the format.
The CLI builds the call graph + Chroma index over `--repo` itself, retrieves
context the same way the eval harness does, then runs the full retry loop
and prints the final diff (or the last failure output, if it gave up).
`--model` optionally overrides the default Groq model for that one run.

For a quick end-to-end demo without hand-picking a bug or a trace file:

```
python scripts/demo.py            # seeds bug 01 (moving-average off-by-one),
                                   # captures the real failure, runs autoheal fix
python scripts/demo.py --bug 09   # or any other id from evals/bugs/definitions.json
```

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
- **No automatic HTTP trigger.** `GET /fix` runs the loop over HTTP and now
  accepts either `bug_id` (seeded mode) or `repo` + `trace` (custom mode,
  see *Running it*), so it's no longer limited to the 15 seeded bugs - but
  it's still a manually-triggered demo endpoint, not a webhook. Nothing
  calls `/fix` on its own in response to a real CI failure.
- **Seeded mode assumes `GITHUB_REPO`'s content matches
  `evals/bugs/sample_repo`.** It's a real HTTP round trip (clone -> seed ->
  diagnose/plan/code/verify, streamed live via SSE -> Approve & push ->
  PyGithub), not a mock, so that assumption has to hold or the seeding
  step's find-string check fails immediately with a clear error. Custom
  mode has no such assumption - it clones whatever repo you type in as-is
  and uses the pasted trace directly, no seeding step involved.
- **`open_pr()` resolves the target repo's actual default branch** via the
  GitHub API rather than assuming `main` - found the hard way during a live
  smoke test against `autoheal-sre-evals`, whose default branch is `master`.
  PR creation would have 404'd against any repo not defaulting to `main`.
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
- A Streamlit/Next.js dashboard, or anything resembling a production admin
  UI. `app/static/index.html` is a single plain HTML/JS page with no build
  step, built specifically to demo the loop against the seeded eval bugs -
  it's not a general dashboard and wasn't meant to become one.
