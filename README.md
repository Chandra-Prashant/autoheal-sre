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

## Architecture

```
                     stack trace / failing pytest node
                                    |
                                    v
                      ┌─────────────────────────┐
                      │  app/graph/ast_parser.py │   tree-sitter walks the repo,
                      │  + call_graph.py          │   extracts function/class
                      └────────────┬──────────────┘   boundaries + who-calls-whom
                                    |
                                    v
                      ┌─────────────────────────┐
                      │  app/graph/embeddings.py │   Chroma semantic search over
                      │                            │   the failing function, then
                      └────────────┬──────────────┘   graph-expanded to callers/callees
                                    |
                                    v
                      ┌─────────────────────────────────────┐
                      │   app/agents/graph_flow.py (LangGraph)│
                      │                                        │
                      │   diagnose -> plan -> code -> verify   │
                      │       ^                        |       │
                      │       └──── retry (max 3x) ─────┘       │
                      └────────────────────┬───────────────────┘
                                            |
                              pass? ────────┴──────── fail after 3x?
                                |                            |
                                v                            v
                  app/github/pr.py (on approval)     last test_output returned,
                  push branch + open real PR           loop just stops, no PR
```

Every node writes to `AgentState` (`app/agents/state.py`) and reads what it
needs from there - it's the one pydantic object threaded through the whole
graph, including the Langfuse trace/span ids once tracing is on. Nothing is
kept in global state between runs; a fresh `AgentState` gets built per
invocation, which is also why concurrent runs don't step on each other (see
*What happens if two fixes run at once* below).

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

| Category | Bugs | Pass@1 | Pass@3 |
|---|---|---|---|
| Off-by-one | 5 | 3/5 (60%) | 4/5 (80%) |
| Unbound variable | 3 | 1/3 (33%) | 2/3 (67%) |
| Wrong exception type | 4 | 2/4 (50%) | 3/4 (75%) |
| Missing null check | 3 | 0/3 (0%) | 2/3 (67%) |
| **Overall** | **15** | **6/15 (40%)** | **11/15 (73%)** |

Numbers are from the run recorded in `evals/results.json` - that file is
the source of truth if this table ever goes stale after a re-run.

## Safeguards

Two checks exist specifically so a "passing" patch can't quietly do the
wrong thing:

- **Full suite, not just the failing test.** `run_tests()` in
  `app/sandbox/runner.py` runs plain `pytest -q` with no path filter, so a
  patch that fixes the named failure but breaks something else gets caught
  as a failed attempt, not a false success.
- **Patches can't touch test files.** `verify()` in
  `app/agents/verifier.py` parses the diff's `--- a/... +++ b/...` headers
  before applying anything. If any touched file matches `test_*.py`,
  `*_test.py`, or lives under a `tests/` directory, the attempt is rejected
  with a message telling the coder tests can't be modified, and that
  feedback flows back into the retry loop the same way a real test failure
  would. This exists because an unconstrained model asked to "make the
  test pass" will sometimes take the easy way out and edit the test
  instead of the code.

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
- **PR generation is gated behind manual approval**, not automatic. A
  passing `verify` doesn't push anything by itself - the CLI just prints
  the diff, and the frontend requires the explicit "Approve & push" click.
  This was a deliberate choice, not a missing feature (see below).

## Questions I'd expect about this

**Why tree-sitter and a call graph instead of just chunking the repo for
RAG?** Fixed-size text chunking cuts functions in half and has no idea
that function A calls function B - it can only find what's textually
similar to the failing code, not what's structurally relevant. Bug 04 in
the eval set is a direct test of this: the bug is in `chunk_list`, but the
trace only names `paginate`. Pure text similarity between the trace and
the codebase wouldn't reliably surface `chunk_list` at all, since nothing
in the error text mentions it by name. The call graph does, because it
knows `paginate` calls `chunk_list`.

**Why LangGraph instead of just calling the LLM in a loop yourself?**
Honestly, a hand-rolled loop with a counter could do most of the same job.
What LangGraph actually buys here is the conditional-edge routing (pass vs
retry vs give-up-after-3 as explicit graph edges, not nested if/else) and
a state object that's easy to trace end to end - each node reads/writes
one `AgentState`, which made wiring Langfuse tracing across nodes running
on a thread pool a lot more tractable than it would've been with ad hoc
function calls.

**Why cap retries at 3?** Cost and time, mostly - each attempt is a real
LLM call plus a real Docker run, and Groq's daily token cap makes
unlimited retries a genuinely bad idea, not just a theoretical one (see
*Current state*). 3 was picked because it's usually enough for the model
to correct a small misunderstanding using the real stderr from the
previous attempt, without either looping forever on a bug it fundamentally
can't reason its way to, or burning a disproportionate amount of quota on
one hard case.

**Why does 3 attempts only get to 73%, not higher?** Two separate reasons.
Some bugs are probably just hard for a 120B open model to reason about
correctly even with the right context - more attempts wouldn't help if the
model keeps making the same category of mistake. The other reason is
mechanical: the diff-format issue mentioned above, where a malformed hunk
header gets a syntactically fine-looking patch rejected before it's even
tested. That second one is a real, fixable weakness in the coder's output
format, not a reasoning failure - worth calling out as the more actionable
of the two if asked what I'd improve first.

**Is this safe to point at a real production repo?** The execution side,
yes - nothing runs outside the sandbox, which has no network access, capped
memory/CPU, a short timeout, and a read-only filesystem outside the
working directory. The write side is intentionally conservative: PR
creation requires a human clicking "Approve & push" after seeing the diff,
never happens automatically on a passing verify, and the verifier
separately rejects any patch that touches a test file so a fix can't just
delete or rewrite the test it's supposed to satisfy.

**What happens if two fixes run at once?** Each request builds its own
fresh `AgentState` and clones the target repo into its own temp directory
(`app/sandbox/runner.py`), so two concurrent runs don't share mutable
state or write into the same working directory. What isn't handled is load
- there's no queue, so enough concurrent requests would just compete for
the same Docker daemon and the same Groq rate limit. Fine for a demo,
not something this has been built or tested for.

**Does this only work on the 15 seeded bugs?** No - the seeded bugs exist
so there's a known-answer set to measure pass@1/pass@3 against, not because
the pipeline is hardcoded to them. The CLI (`autoheal fix <trace-file>
--repo <path>`) runs the same call-graph retrieval and agent loop against
any Python repo and any trace you give it, and the demo frontend's Custom
tab (see *Running it*) exposes the same thing over HTTP - any `owner/name`
repo and any pasted trace, no seeding involved. The seeded-bug dropdown is
still there because it's the fastest way to get a reliable demo without
hunting for a real failure first, not because it's the only path through
the pipeline.

**Why not deploy this / ship it as an installer?** Two practical reasons.
The sandbox step needs a real Docker daemon, which most simple free
hosting doesn't support without extra setup (Docker-in-Docker or a VM-based
host), and a public endpoint would mean anyone hitting it burns the same
shared Groq quota this project already runs into solo. Packaging it as a
standalone installer has a similar problem - Docker can't be bundled into
an installer, so a user would still need Docker Desktop installed
separately, and the tool needs its own Groq/GitHub keys to function, which
can't be baked into something handed out generically. Running it locally
from source with your own keys is the realistic way to use this right now.

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
- Automatic PR pushing on a passing verify. This isn't a gap to close
  later - a human approving the diff before anything reaches GitHub is a
  deliberate part of the design, not a step that got skipped.
- A general-purpose webhook trigger (e.g. a Sentry integration that
  auto-detects a live crash and kicks off a fix with no human in the loop).
  The architecture doesn't preclude adding one - `GET /fix` already shows
  the shape of an HTTP entry point - but building and trusting an
  always-on production trigger is a different, bigger project than this
  one.
