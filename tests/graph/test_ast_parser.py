import os

from app.graph.ast_parser import parse_file

FIXTURES = os.path.join(os.path.dirname(__file__), "..", "fixtures", "sample_pkg")


def test_parses_top_level_functions():
    funcs = parse_file(os.path.join(FIXTURES, "utils.py"))
    names = {f.qualname for f in funcs}
    assert names == {"add", "double"}

    double = next(f for f in funcs if f.qualname == "double")
    assert double.calls == ["add"]


def test_parses_methods_with_qualified_names():
    funcs = parse_file(os.path.join(FIXTURES, "service.py"))
    names = {f.qualname for f in funcs}
    assert names == {"Service.run", "Service.validate"}

    run = next(f for f in funcs if f.qualname == "Service.run")
    assert run.calls == ["validate", "double"]
