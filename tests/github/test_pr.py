import pytest

from app.github import pr


class FakeRepo:
    def __init__(self):
        self.calls = []

    def create_pull(self, **kwargs):
        self.calls.append(kwargs)
        return type("PR", (), {"html_url": "https://github.com/me/repo/pull/1"})()


class FakeGithub:
    def __init__(self, auth=None):
        self.repo = FakeRepo()

    def get_repo(self, name):
        return self.repo


def test_open_pr_runs_git_and_creates_pull(monkeypatch, tmp_path):
    git_calls = []
    monkeypatch.setattr(pr.subprocess, "run", lambda cmd, cwd, check: git_calls.append(cmd))
    monkeypatch.setattr(pr, "GITHUB_TOKEN", "fake-token")
    fake_gh = FakeGithub()
    monkeypatch.setattr(pr, "Github", lambda auth=None: fake_gh)

    url = pr.open_pr(str(tmp_path), "me/repo", "fix the bug", "diagnosis + plan here")

    assert url == "https://github.com/me/repo/pull/1"
    assert ["git", "checkout", "-b"] == git_calls[0][:3]
    assert git_calls[1][:2] == ["git", "add"]
    assert git_calls[2][:3] == ["git", "commit", "-m"]
    assert git_calls[3][:2] == ["git", "push"]

    create = fake_gh.repo.calls[0]
    assert create["title"] == "fix the bug"
    assert create["body"] == "diagnosis + plan here"
    assert create["base"] == "main"
    assert create["head"].startswith("autoheal/fix-")


def test_open_pr_raises_without_a_token(monkeypatch, tmp_path):
    monkeypatch.setattr(pr, "GITHUB_TOKEN", None)
    with pytest.raises(RuntimeError):
        pr.open_pr(str(tmp_path), "me/repo", "title", "body")
