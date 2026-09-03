from dataclasses import dataclass, field

from tree_sitter import Language, Parser
import tree_sitter_python as tsp

PY_LANGUAGE = Language(tsp.language())


@dataclass
class Function:
    name: str
    qualname: str
    file: str
    start_line: int
    end_line: int
    source: str
    calls: list[str] = field(default_factory=list)


def _call_name(node) -> str | None:
    # a call's `function` child is either a bare identifier (`foo()`)
    # or an attribute (`self.foo()`, `obj.foo()`) - we only care about
    # the trailing name, resolution against qualnames happens in call_graph.
    fn = node.child_by_field_name("function")
    if fn is None:
        return None
    if fn.type == "identifier":
        return fn.text.decode()
    if fn.type == "attribute":
        attr = fn.child_by_field_name("attribute")
        return attr.text.decode() if attr else None
    return None


def _find_calls(node, out: list[str]):
    if node.type == "call":
        name = _call_name(node)
        if name:
            out.append(name)
    for child in node.children:
        _find_calls(child, out)


def _extract(node, src: bytes, file: str, class_name: str | None, out: list[Function]):
    for child in node.children:
        if child.type == "function_definition":
            name_node = child.child_by_field_name("name")
            body = child.child_by_field_name("body")
            name = name_node.text.decode()
            qualname = f"{class_name}.{name}" if class_name else name
            calls: list[str] = []
            if body is not None:
                _find_calls(body, calls)
            out.append(Function(
                name=name,
                qualname=qualname,
                file=file,
                start_line=child.start_point[0] + 1,
                end_line=child.end_point[0] + 1,
                source=src[child.start_byte:child.end_byte].decode(),
                calls=calls,
            ))
            # methods can't nest further function defs we care about here
        elif child.type == "class_definition":
            name_node = child.child_by_field_name("name")
            body = child.child_by_field_name("body")
            if body is not None:
                _extract(body, src, file, name_node.text.decode(), out)
        else:
            _extract(child, src, file, class_name, out)


def parse_file(path: str) -> list[Function]:
    with open(path, "rb") as f:
        src = f.read()
    parser = Parser(PY_LANGUAGE)
    tree = parser.parse(src)
    out: list[Function] = []
    _extract(tree.root_node, src, path, None, out)
    return out
