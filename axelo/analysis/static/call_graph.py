from __future__ import annotations
from collections import defaultdict, deque
from axelo.models.analysis import FunctionSignature


class CallGraph:
    """
    从 AST 元数据构建函数调用图，支持：
    - 从候选函数反向追溯调用链到网络请求
    - 提取从入口到候选函数的调用路径
    """

    def __init__(self, functions: dict[str, FunctionSignature]) -> None:
        self.functions = functions
        # caller → set of callees
        self._edges: dict[str, set[str]] = defaultdict(set)
        # callee → set of callers
        self._rev_edges: dict[str, set[str]] = defaultdict(set)
        self._build()

    def _build(self) -> None:
        for func_id, func in self.functions.items():
            for callee in func.calls:
                self._edges[func_id].add(callee)
                self._rev_edges[callee].add(func_id)

    def get_callers(self, func_id: str, depth: int = 3) -> list[str]:
        """BFS 向上追溯调用链，返回最多 depth 层的调用者"""
        visited: set[str] = set()
        queue = deque([(func_id, 0)])
        result: list[str] = []
        while queue:
            node, d = queue.popleft()
            if d >= depth or node in visited:
                continue
            visited.add(node)
            for caller in self._rev_edges.get(node, set()):
                result.append(caller)
                queue.append((caller, d + 1))
        return result

    def get_callees(self, func_id: str, depth: int = 3) -> list[str]:
        """BFS 向下展开被调用的函数"""
        visited: set[str] = set()
        queue = deque([(func_id, 0)])
        result: list[str] = []
        while queue:
            node, d = queue.popleft()
            if d >= depth or node in visited:
                continue
            visited.add(node)
            for callee in self._edges.get(node, set()):
                result.append(callee)
                queue.append((callee, d + 1))
        return result

    def shortest_path(self, src: str, dst: str) -> list[str] | None:
        """BFS 求 src → dst 的最短调用路径"""
        if src == dst:
            return [src]
        visited = {src}
        queue: deque[list[str]] = deque([[src]])
        while queue:
            path = queue.popleft()
            node = path[-1]
            for callee in self._edges.get(node, set()):
                if callee == dst:
                    return path + [callee]
                if callee not in visited:
                    visited.add(callee)
                    queue.append(path + [callee])
        return None

    def subgraph_for_candidates(self, candidate_ids: list[str]) -> dict[str, list[str]]:
        """提取候选函数周围的子图（调用链摘要），用于喂给 AI"""
        result: dict[str, list[str]] = {}
        for func_id in candidate_ids:
            callers = self.get_callers(func_id, depth=2)
            callees = self.get_callees(func_id, depth=2)
            result[func_id] = callers + callees
        return result
