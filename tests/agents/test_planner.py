from app.agents import planner
from app.agents.state import AgentState


class FakeLLM:
    def __init__(self):
        self.messages = None

    def invoke(self, messages):
        self.messages = messages
        return type("Resp", (), {"content": "fake plan"})()


def test_plan_calls_llm_with_diagnosis_and_context(monkeypatch):
    fake = FakeLLM()
    monkeypatch.setattr(planner, "get_llm", lambda: fake)

    state = AgentState(trace="boom", repo_path="/tmp/repo",
                        diagnosis="off-by-one in the loop bound",
                        context=["def foo(): pass"])
    result = planner.plan(state)

    assert result == {"plan": "fake plan"}
    prompt = fake.messages[1].content
    assert "off-by-one" in prompt
    assert "def foo" in prompt
