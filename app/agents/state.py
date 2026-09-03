from pydantic import BaseModel


class AgentState(BaseModel):
    trace: str
    repo_path: str
    context: list[str] = []
    model: str | None = None  # override app.config.GROQ_MODEL for this run

    diagnosis: str | None = None
    plan: str | None = None
    patch: str | None = None

    test_output: str | None = None
    passed: bool = False

    attempt: int = 0
    max_attempts: int = 3
