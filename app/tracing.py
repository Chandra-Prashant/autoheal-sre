from contextlib import contextmanager

from langfuse import get_client

__all__ = ["node_span", "log_usage", "traced_run", "traced_stream"]


@contextmanager
def node_span(state, name: str, as_type: str = "span"):
    # LangGraph runs each node on a worker thread, which loses the ambient
    # otel trace context - attach explicitly via the ids stashed on state
    # instead of relying on start_as_current_observation to find a parent
    trace_context = None
    if state.run_trace_id:
        trace_context = {"trace_id": state.run_trace_id, "parent_span_id": state.run_span_id}
    with get_client().start_as_current_observation(name=name, as_type=as_type, trace_context=trace_context) as obs:
        yield obs


def log_usage(obs, resp, model: str) -> None:
    usage = getattr(resp, "usage_metadata", None) or {}
    obs.update(
        model=model,
        usage_details={
            "input": usage.get("input_tokens", 0),
            "output": usage.get("output_tokens", 0),
            "total": usage.get("total_tokens", 0),
        },
    )


def traced_run(graph, state) -> dict:
    client = get_client()
    span = client.start_observation(name="autoheal_run", as_type="span")
    state = state.model_copy(update={"run_trace_id": span.trace_id, "run_span_id": span.id})
    try:
        return graph.invoke(state)
    finally:
        span.end()
        client.flush()


def traced_stream(graph, state):
    # same idea as traced_run, but yields each node's update as it completes
    # instead of blocking for the final result - for the frontend's live
    # progress view
    client = get_client()
    span = client.start_observation(name="autoheal_run", as_type="span")
    state = state.model_copy(update={"run_trace_id": span.trace_id, "run_span_id": span.id})
    try:
        yield from graph.stream(state)
    finally:
        span.end()
        client.flush()
