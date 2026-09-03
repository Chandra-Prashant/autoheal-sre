import os

from app.graph.call_graph import CallGraph

FIXTURES = os.path.join(os.path.dirname(__file__), "..", "fixtures", "sample_pkg")


def build():
    cg = CallGraph()
    cg.build_from_dir(FIXTURES)
    return cg


def test_builds_nodes_for_every_function():
    cg = build()
    qualnames = {data["qualname"] for _, data in cg.g.nodes(data=True)}
    assert qualnames == {"add", "double", "Service.run", "Service.validate"}


def test_links_calls_across_files():
    cg = build()
    double = cg.find("double")[0]
    add = cg.find("add")[0]
    assert add in cg.callees(double)
    assert double in cg.callers(add)


def test_links_calls_within_a_class():
    cg = build()
    run = cg.find("run")[0]
    validate = cg.find("validate")[0]
    assert validate in cg.callees(run)


def test_context_includes_neighbors():
    cg = build()
    double = cg.find("double")[0]
    ctx = cg.context(double, depth=1)
    qualnames = {cg.g.nodes[n]["qualname"] for n in ctx.nodes}
    assert "add" in qualnames
    assert "Service.run" in qualnames
