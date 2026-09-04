from pydantic import BaseModel


class AgentState(BaseModel):
    trace: str
    repo_path: str
    context: list[str] = []
    model: str | None = None  # override app.config.GROQ_MODEL for this run

    # langfuse trace/span this run's nodes should attach to - LangGraph runs
    # nodes on a worker thread pool, which drops the otel contextvar, so we
    # thread the parent ids through state instead of relying on ambient context
    run_trace_id: str | None = None
    run_span_id: str | None = None

    diagnosis: str | None = None
    plan: str | None = None
    patch: str | None = None

    test_output: str | None = None
    passed: bool = False

    attempt: int = 0
    max_attempts: int = 3
