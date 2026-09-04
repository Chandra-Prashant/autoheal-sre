import argparse

from app import cli


def _args(tmp_path, model=None):
    trace_file = tmp_path / "trace.txt"
    trace_file.write_text("boom")
    return argparse.Namespace(trace_file=str(trace_file), repo="repo", model=model)


def test_fix_prints_patch_and_returns_0_on_success(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(cli, "build_context", lambda repo, trace: ["ctx"])
    monkeypatch.setattr(cli, "build_graph", lambda: object())
    monkeypatch.setattr(cli, "traced_run", lambda graph, state: {"passed": True, "attempt": 1, "patch": "the-diff"})

    code = cli.fix(_args(tmp_path))

    out = capsys.readouterr().out
    assert code == 0
    assert "fixed on attempt 1" in out
    assert "the-diff" in out


def test_fix_returns_1_and_prints_failure_output(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(cli, "build_context", lambda repo, trace: ["ctx"])
    monkeypatch.setattr(cli, "build_graph", lambda: object())
    monkeypatch.setattr(cli, "traced_run", lambda graph, state: {
        "passed": False, "attempt": 3, "test_output": "still broken"
    })

    code = cli.fix(_args(tmp_path))

    err = capsys.readouterr().err
    assert code == 1
    assert "gave up after 3" in err
    assert "still broken" in err


def test_fix_warns_when_context_retrieval_is_empty(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(cli, "build_context", lambda repo, trace: [])
    monkeypatch.setattr(cli, "build_graph", lambda: object())
    monkeypatch.setattr(cli, "traced_run", lambda graph, state: {"passed": True, "attempt": 1, "patch": "d"})

    cli.fix(_args(tmp_path))

    assert "no relevant functions" in capsys.readouterr().err
