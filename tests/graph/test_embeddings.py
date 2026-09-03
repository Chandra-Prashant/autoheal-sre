import os

from app.graph.call_graph import CallGraph
from app.graph.embeddings import FunctionIndex, retrieve_context

FIXTURES = os.path.join(os.path.dirname(__file__), "..", "fixtures", "sample_pkg")


def build_index(tmp_path):
    cg = CallGraph()
    cg.build_from_dir(FIXTURES)
    idx = FunctionIndex(path=str(tmp_path / "chroma"))
    idx.index_graph(cg)
    return cg, idx


def test_query_finds_semantically_relevant_function(tmp_path):
    _, idx = build_index(tmp_path)
    results = idx.query("function that sums two numbers", n_results=1)
    assert results[0].endswith("sample_pkg/utils.py::add")


def test_retrieve_context_expands_via_call_graph(tmp_path):
    cg, idx = build_index(tmp_path)
    nodes = retrieve_context(idx, cg, "doubling a number", k=1, depth=1)
    qualnames = {cg.g.nodes[n]["qualname"] for n in nodes}
    # the seed hit (double) plus its neighbors in the call graph
    assert "double" in qualnames
    assert "add" in qualnames
