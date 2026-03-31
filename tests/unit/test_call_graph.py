"""调用图单元测试"""
import pytest
from axelo.models.analysis import FunctionSignature
from axelo.analysis.static.call_graph import CallGraph


def _build_graph() -> CallGraph:
    funcs = {
        "f:main":    FunctionSignature(func_id="f:main",    name="main",    calls=["f:sign", "f:send"]),
        "f:sign":    FunctionSignature(func_id="f:sign",    name="sign",    calls=["f:hmac", "f:ts"]),
        "f:hmac":    FunctionSignature(func_id="f:hmac",    name="hmac",    calls=[]),
        "f:ts":      FunctionSignature(func_id="f:ts",      name="ts",      calls=[]),
        "f:send":    FunctionSignature(func_id="f:send",    name="send",    calls=["f:fetch"]),
        "f:fetch":   FunctionSignature(func_id="f:fetch",   name="fetch",   calls=[]),
    }
    return CallGraph(funcs)


class TestCallGraph:
    def test_get_callees(self):
        g = _build_graph()
        callees = g.get_callees("f:main", depth=1)
        assert "f:sign" in callees
        assert "f:send" in callees

    def test_get_callers(self):
        g = _build_graph()
        callers = g.get_callers("f:hmac", depth=2)
        assert "f:sign" in callers

    def test_shortest_path_direct(self):
        g = _build_graph()
        path = g.shortest_path("f:sign", "f:hmac")
        assert path == ["f:sign", "f:hmac"]

    def test_shortest_path_indirect(self):
        g = _build_graph()
        path = g.shortest_path("f:main", "f:hmac")
        assert path is not None
        assert path[0] == "f:main"
        assert path[-1] == "f:hmac"

    def test_shortest_path_unreachable(self):
        g = _build_graph()
        path = g.shortest_path("f:fetch", "f:hmac")
        assert path is None

    def test_subgraph_for_candidates(self):
        g = _build_graph()
        subgraph = g.subgraph_for_candidates(["f:sign"])
        assert "f:sign" in subgraph
        related = subgraph["f:sign"]
        assert "f:hmac" in related or "f:main" in related
