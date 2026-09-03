from pydantic import BaseModel


class AgentState(BaseModel):
    trace: str
    repo_path: str
    context: list[str] = []

    diagnosis: str | None = None
    plan: str | None = None
    patch: str | None = None

    test_output: str | None = None
    passed: bool = False

    attempt: int = 0
    max_attempts: int = 3
