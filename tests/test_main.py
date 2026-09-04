import os

from fastapi.testclient import TestClient

from app import main

client = TestClient(main.app)


def test_health():
    assert client.get("/health").json() == {"status": "ok"}


def test_index_serves_the_frontend():
    res = client.get("/")
    assert res.status_code == 200
    assert "text/html" in res.headers["content-type"]


def test_bugs_lists_all_seeded_definitions():
    res = client.get("/bugs")
    assert res.status_code == 200
    body = res.json()
    assert len(body) == 15
    assert all({"id", "category", "description"} <= b.keys() for b in body)


def test_fix_errors_without_github_config(monkeypatch):
    monkeypatch.setattr(main, "GITHUB_REPO", None)
    monkeypatch.setattr(main, "GITHUB_TOKEN", None)

    res = client.get("/fix?bug_id=01-moving-average-off-by-one")

    assert "event: error" in res.text
    assert "GITHUB_REPO" in res.text


def test_fix_errors_on_unknown_bug_id(monkeypatch):
    monkeypatch.setattr(main, "GITHUB_REPO", "me/repo")
    monkeypatch.setattr(main, "GITHUB_TOKEN", "tok")

    res = client.get("/fix?bug_id=does-not-exist")

    assert "event: error" in res.text
    assert "unknown bug id" in res.text


def _fake_node_updates():
    yield {"diagnose": {"diagnosis": "off by one"}}
    yield {"plan": {"plan": "fix the range"}}
    yield {"code": {"patch": "the-diff", "attempt": 1}}
    yield {"verify": {"passed": True, "test_output": "ok"}}


def test_fix_streams_node_updates_and_records_a_run_on_success(monkeypatch, tmp_path):
    monkeypatch.setattr(main, "GITHUB_REPO", "me/repo")
    monkeypatch.setattr(main, "GITHUB_TOKEN", "tok")
    monkeypatch.setattr(main, "_clone_repo", lambda repo_full_name: str(tmp_path))
    monkeypatch.setattr(main, "apply_bug", lambda dest, bug: None)
    monkeypatch.setattr(main, "capture_trace", lambda repo_path, target: "boom")
    monkeypatch.setattr(main, "build_context", lambda repo_path, trace: ["ctx"])
    monkeypatch.setattr(main, "traced_stream", lambda graph, state: _fake_node_updates())

    res = client.get("/fix?bug_id=01-moving-average-off-by-one")

    assert "event: node" in res.text
    assert "event: result" in res.text
    assert '"passed": true' in res.text
    assert "the-diff" in res.text

    run_id = next(iter(main.RUNS))
    assert main.RUNS[run_id]["patch"] == "the-diff"


def test_fix_cleans_up_and_reports_failure_after_exhausting_attempts(monkeypatch, tmp_path):
    def failing_updates():
        yield {"diagnose": {"diagnosis": "d"}}
        yield {"plan": {"plan": "p"}}
        yield {"code": {"patch": "bad-diff", "attempt": 3}}
        yield {"verify": {"passed": False, "test_output": "still broken"}}

    monkeypatch.setattr(main, "GITHUB_REPO", "me/repo")
    monkeypatch.setattr(main, "GITHUB_TOKEN", "tok")
    monkeypatch.setattr(main, "_clone_repo", lambda repo_full_name: str(tmp_path))
    monkeypatch.setattr(main, "apply_bug", lambda dest, bug: None)
    monkeypatch.setattr(main, "capture_trace", lambda repo_path, target: "boom")
    monkeypatch.setattr(main, "build_context", lambda repo_path, trace: ["ctx"])
    monkeypatch.setattr(main, "traced_stream", lambda graph, state: failing_updates())

    res = client.get("/fix?bug_id=01-moving-average-off-by-one")

    assert '"passed": false' in res.text
    assert "still broken" in res.text
    assert not os.path.exists(tmp_path)


def test_fix_custom_errors_without_a_repo(monkeypatch):
    monkeypatch.setattr(main, "GITHUB_TOKEN", "tok")

    res = client.get("/fix?trace=boom")

    assert "event: error" in res.text
    assert "owner/name" in res.text


def test_fix_custom_errors_on_a_malformed_repo(monkeypatch):
    monkeypatch.setattr(main, "GITHUB_TOKEN", "tok")

    res = client.get("/fix?repo=not-a-valid-repo&trace=boom")

    assert "event: error" in res.text
    assert "owner/name" in res.text


def test_fix_custom_errors_without_trace_text(monkeypatch):
    monkeypatch.setattr(main, "GITHUB_TOKEN", "tok")

    res = client.get("/fix?repo=me/other-repo")

    assert "event: error" in res.text
    assert "trace text" in res.text


def test_fix_custom_streams_node_updates_and_records_a_run_on_success(monkeypatch, tmp_path):
    monkeypatch.setattr(main, "GITHUB_TOKEN", "tok")
    monkeypatch.setattr(main, "_clone_repo", lambda repo_full_name: str(tmp_path))
    monkeypatch.setattr(main, "build_context", lambda repo_path, trace: ["ctx"])
    monkeypatch.setattr(main, "traced_stream", lambda graph, state: _fake_node_updates())

    before = set(main.RUNS)
    res = client.get("/fix?repo=me/other-repo&trace=boom")

    assert "event: node" in res.text
    assert "event: result" in res.text
    assert '"passed": true' in res.text

    run_id = next(iter(set(main.RUNS) - before))
    assert main.RUNS[run_id]["target_repo"] == "me/other-repo"


def test_approve_rejects_an_unknown_run_id():
    res = client.post("/pr", json={"run_id": "nope"})
    assert res.status_code == 404


def test_approve_applies_the_patch_and_opens_a_pr(monkeypatch, tmp_path):
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()
    patched_dir = tmp_path / "patched"
    patched_dir.mkdir()

    main.RUNS["r1"] = {
        "repo_path": str(repo_dir),
        "target_repo": "me/repo",
        "patch": "the-diff",
        "title": "autoheal: fix bug",
        "body": "diagnosis + plan",
    }
    monkeypatch.setattr(main, "apply_patch", lambda repo_path, patch: str(patched_dir))
    monkeypatch.setattr(main, "open_pr", lambda repo_path, full_name, title, body: "https://github.com/me/repo/pull/1")

    res = client.post("/pr", json={"run_id": "r1"})

    assert res.status_code == 200
    assert res.json() == {"url": "https://github.com/me/repo/pull/1"}
    assert "r1" not in main.RUNS
