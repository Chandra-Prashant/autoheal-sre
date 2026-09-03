from app.agents import coder
from app.agents.state import AgentState


class FakeLLM:
    def __init__(self, content):
        self.content = content
        self.messages = None

    def invoke(self, messages):
        self.messages = messages
        return type("Resp", (), {"content": self.content})()


def test_code_produces_patch_and_increments_attempt(monkeypatch):
    fake = FakeLLM("--- a/foo.py\n+++ b/foo.py\n@@\n-bad\n+good\n")
    monkeypatch.setattr(coder, "get_llm", lambda **kw: fake)

    state = AgentState(trace="boom", repo_path="/tmp/repo",
                        diagnosis="off-by-one", plan="fix the loop bound",
                        context=["def foo(): pass"])
    result = coder.code(state)

    assert result["patch"] == fake.content.strip()
    assert result["attempt"] == 1
    prompt = fake.messages[1].content
    assert "off-by-one" in prompt
    assert "fix the loop bound" in prompt
    assert "def foo" in prompt


def test_code_strips_markdown_fences(monkeypatch):
    fenced = "```diff\n--- a/foo.py\n+++ b/foo.py\n@@\n-bad\n+good\n```"
    fake = FakeLLM(fenced)
    monkeypatch.setattr(coder, "get_llm", lambda **kw: fake)

    state = AgentState(trace="boom", repo_path="/tmp/repo", diagnosis="d", plan="p")
    result = coder.code(state)

    assert result["patch"] == "--- a/foo.py\n+++ b/foo.py\n@@\n-bad\n+good"
    assert "```" not in result["patch"]


def test_code_includes_previous_failure_on_retry(monkeypatch):
    fake = FakeLLM("patch v2")
    monkeypatch.setattr(coder, "get_llm", lambda **kw: fake)

    state = AgentState(trace="boom", repo_path="/tmp/repo", diagnosis="d", plan="p",
                        attempt=1, patch="patch v1", test_output="AssertionError: still broken")
    coder.code(state)

    prompt = fake.messages[1].content
    assert "patch v1" in prompt
    assert "still broken" in prompt
