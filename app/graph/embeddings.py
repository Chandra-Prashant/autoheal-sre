import chromadb

from app.config import CHROMA_DIR
from app.graph.call_graph import CallGraph


class FunctionIndex:
    def __init__(self, path: str = CHROMA_DIR):
        client = chromadb.PersistentClient(path=path)
        self.collection = client.get_or_create_collection("functions")

    def index_graph(self, graph: CallGraph):
        ids, docs, metas = [], [], []
        for node, data in graph.g.nodes(data=True):
            ids.append(node)
            docs.append(f"{data['qualname']}\n{data['source']}")
            metas.append({
                "file": data["file"],
                "qualname": data["qualname"],
                "start_line": data["start_line"],
                "end_line": data["end_line"],
            })
        if ids:
            self.collection.upsert(ids=ids, documents=docs, metadatas=metas)

    def query(self, text: str, n_results: int = 5) -> list[str]:
        if self.collection.count() == 0:
            return []
        n_results = min(n_results, self.collection.count())
        res = self.collection.query(query_texts=[text], n_results=n_results)
        return res["ids"][0]


def retrieve_context(index: FunctionIndex, graph: CallGraph, text: str, k: int = 5, depth: int = 1) -> set[str]:
    # semantic search finds the functions that plausibly relate to the
    # error/trace, then the call graph pulls in their direct callers/callees
    # so the agent sees the actual usage context, not an isolated snippet
    nodes = set(index.query(text, n_results=k))
    for seed in list(nodes):
        if seed in graph.g:
            nodes |= set(graph.context(seed, depth=depth).nodes)
    return nodes
