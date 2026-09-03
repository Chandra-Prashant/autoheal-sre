import glob
import os

import networkx as nx

from app.graph.ast_parser import Function, parse_file


def node_id(fn: Function) -> str:
    return f"{fn.file}::{fn.qualname}"


class CallGraph:
    def __init__(self):
        self.g = nx.DiGraph()
        # bare name -> node ids, used to resolve call sites since a call
        # like `foo()` doesn't know which file/class defined `foo`
        self._by_name: dict[str, list[str]] = {}

    def build_from_dir(self, root: str, pattern: str = "**/*.py"):
        paths = glob.glob(os.path.join(root, pattern), recursive=True)
        self.build_from_files(paths)

    def build_from_files(self, paths: list[str]):
        all_funcs: list[Function] = []
        for path in paths:
            all_funcs.extend(parse_file(path))

        for fn in all_funcs:
            node = node_id(fn)
            self.g.add_node(node, file=fn.file, name=fn.name, qualname=fn.qualname,
                             start_line=fn.start_line, end_line=fn.end_line, source=fn.source)
            self._by_name.setdefault(fn.name, []).append(node)

        for fn in all_funcs:
            caller = node_id(fn)
            for callee_name in fn.calls:
                for callee in self._by_name.get(callee_name, []):
                    if callee != caller:
                        self.g.add_edge(caller, callee)

    def callers(self, node: str) -> list[str]:
        return list(self.g.predecessors(node))

    def callees(self, node: str) -> list[str]:
        return list(self.g.successors(node))

    def find(self, name: str) -> list[str]:
        return self._by_name.get(name, [])

    def context(self, node: str, depth: int = 1) -> nx.DiGraph:
        nodes = {node}
        frontier = {node}
        for _ in range(depth):
            nxt = set()
            for n in frontier:
                nxt |= set(self.g.predecessors(n)) | set(self.g.successors(n))
            nodes |= nxt
            frontier = nxt
        return self.g.subgraph(nodes)
