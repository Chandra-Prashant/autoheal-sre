import json
import os
import shutil
import subprocess
import tempfile
import uuid

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel

from app.agents.graph_flow import build_graph
from app.agents.state import AgentState
from app.config import GITHUB_REPO, GITHUB_TOKEN
from app.github.pr import open_pr
from app.graph.embeddings import build_context
from app.sandbox.runner import apply_patch, capture_trace
from app.tracing import traced_stream
from scripts.seed_bugs import apply_bug, load_definitions

app = FastAPI(title="autoheal-sre")

STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")

# demo runs live in memory only - single process, no persistence needed for
# a college-project demo. keyed by run_id, holding what /pr needs once a run
# passes and the user clicks Approve & Push
RUNS: dict[str, dict] = {}


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/")
def index():
    return FileResponse(os.path.join(STATIC_DIR, "index.html"))


@app.get("/bugs")
def bugs():
    return [{"id": b["id"], "category": b["category"], "description": b["description"]}
            for b in load_definitions()]


def _scrub(text: str) -> str:
    return text.replace(GITHUB_TOKEN, "***") if GITHUB_TOKEN else text


def _clone_target_repo() -> str:
    if not GITHUB_REPO or not GITHUB_TOKEN:
        raise RuntimeError("GITHUB_REPO and GITHUB_TOKEN must both be set in .env")

    dest = tempfile.mkdtemp(prefix="autoheal-demo-")
    url = f"https://x-access-token:{GITHUB_TOKEN}@github.com/{GITHUB_REPO}.git"
    result = subprocess.run(["git", "clone", "--depth", "1", url, dest], capture_output=True, text=True)
    if result.returncode != 0:
        shutil.rmtree(dest, ignore_errors=True)
        raise RuntimeError(f"git clone failed: {_scrub(result.stderr)}")

    subprocess.run(["git", "config", "user.email", "autoheal@example.com"], cwd=dest, check=True)
    subprocess.run(["git", "config", "user.name", "autoheal-sre"], cwd=dest, check=True)
    return dest


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


def _run_fix(bug_id: str, model: str | None):
    bugs_by_id = {b["id"]: b for b in load_definitions()}
    bug = bugs_by_id.get(bug_id)
    if not bug:
        yield _sse("error", {"message": f"unknown bug id {bug_id!r}"})
        return

    if not GITHUB_REPO or not GITHUB_TOKEN:
        yield _sse("error", {"message": "GITHUB_REPO and GITHUB_TOKEN must both be set in .env"})
        return

    yield _sse("stage", {"message": f"cloning {GITHUB_REPO}..."})
    try:
        repo_path = _clone_target_repo()
    except RuntimeError as e:
        yield _sse("error", {"message": str(e)})
        return

    yield _sse("stage", {"message": f"seeding bug {bug_id}..."})
    try:
        apply_bug(repo_path, bug)
    except ValueError as e:
        shutil.rmtree(repo_path, ignore_errors=True)
        yield _sse("error", {"message": str(e)})
        return

    yield _sse("stage", {"message": "capturing the real test failure..."})
    trace = capture_trace(repo_path, bug["test_target"])

    yield _sse("stage", {"message": "building call graph and retrieving context..."})
    context = build_context(repo_path, trace)

    state = AgentState(trace=trace, repo_path=repo_path, context=context, model=model)
    merged = state.model_dump()

    for update in traced_stream(build_graph(), state):
        for node, data in update.items():
            merged.update(data)
            yield _sse("node", {
                "node": node,
                "attempt": merged.get("attempt"),
                "passed": merged.get("passed"),
                "diagnosis": merged.get("diagnosis"),
                "plan": merged.get("plan"),
                "test_output": merged.get("test_output"),
            })

    if merged.get("passed"):
        run_id = uuid.uuid4().hex
        RUNS[run_id] = {
            "repo_path": repo_path,
            "patch": merged["patch"],
            "title": f"autoheal: fix {bug_id}",
            "body": f"Diagnosis:\n{merged.get('diagnosis')}\n\nPlan:\n{merged.get('plan')}",
        }
        yield _sse("result", {
            "passed": True, "run_id": run_id,
            "attempt": merged["attempt"], "patch": merged["patch"],
        })
    else:
        shutil.rmtree(repo_path, ignore_errors=True)
        yield _sse("result", {
            "passed": False, "attempt": merged.get("attempt"),
            "test_output": merged.get("test_output"),
        })


@app.get("/fix")
def fix(bug_id: str, model: str | None = None):
    return StreamingResponse(_run_fix(bug_id, model), media_type="text/event-stream")


class ApproveRequest(BaseModel):
    run_id: str


@app.post("/pr")
def approve(req: ApproveRequest):
    run = RUNS.pop(req.run_id, None)
    if not run:
        raise HTTPException(404, "unknown or already-used run_id")

    try:
        patched = apply_patch(run["repo_path"], run["patch"])
    except ValueError as e:
        shutil.rmtree(run["repo_path"], ignore_errors=True)
        raise HTTPException(400, str(e))

    try:
        url = open_pr(patched, GITHUB_REPO, run["title"], run["body"])
    except Exception as e:
        raise HTTPException(500, _scrub(str(e)))
    finally:
        shutil.rmtree(patched, ignore_errors=True)
        shutil.rmtree(run["repo_path"], ignore_errors=True)

    return {"url": url}
