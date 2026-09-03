from app.agents import diagnostic
from app.agents.state import AgentState


class FakeLLM:
    def __init__(self):
        self.messages = None

    def invoke(self, messages):
        self.messages = messages
        return type("Resp", (), {"content": "fake diagnosis"})()


def test_diagnose_calls_llm_with_trace_and_context(monkeypatch):
    fake = FakeLLM()
    monkeypatch.setattr(diagnostic, "get_llm", lambda: fake)

    state = AgentState(trace="ZeroDivisionError: division by zero",
                        repo_path="/tmp/repo",
                        context=["def divide(a, b): return a / b"])
    result = diagnostic.diagnose(state)

    assert result == {"diagnosis": "fake diagnosis"}
    prompt = fake.messages[1].content
    assert "ZeroDivisionError" in prompt
    assert "def divide" in prompt


def test_diagnose_handles_missing_context(monkeypatch):
    fake = FakeLLM()
    monkeypatch.setattr(diagnostic, "get_llm", lambda: fake)

    state = AgentState(trace="boom", repo_path="/tmp/repo")
    diagnostic.diagnose(state)

    assert "no code context retrieved" in fake.messages[1].content
