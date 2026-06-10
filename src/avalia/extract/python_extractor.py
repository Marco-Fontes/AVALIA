"""T-102 — Extrator Python por `ast` (leitura estática pura).

Invariante RNF-05/S-04 (intrínseco): analisa o alvo APENAS por `ast.parse` sobre o texto-
fonte. Nenhum carregamento dinâmico de módulo, execução/avaliação de código, compilação-
para-execução ou subprocesso do alvo é permitido. O alvo é texto inerte. Cada fato extraído
carrega `EvidenceRef` com o SÍMBOLO (nunca só linha).

Heurísticas (documentadas, determinísticas): prompts por nome/kwarg; ferramentas por
decorador; arestas por add_edge/add_conditional_edges; loops com/sem teto; estado
compartilhado por TypedDict/classe *State/param `state`; sinais de robustez por
try/except/retry/timeout/stream/cache.

Rastreabilidade: RF-14, RNF-07, RNF-05/S-04; alimenta RF-DIM-*; resolução #1.
"""

from __future__ import annotations

import ast

from avalia.domain.evidence import EvidenceRef
from avalia.domain.tsm import (
    AgentNode,
    ConfigItem,
    Edge,
    ErrorHandling,
    LoopInfo,
    ModelAssignment,
    PromptRef,
    SharedStateRef,
    ToolDef,
)
from avalia.extract.base import ExtractionResult

_PROMPT_NAME_HINTS = ("prompt", "system", "instruction", "instructions", "template", "persona")
_PROMPT_KW = ("system", "system_prompt", "prompt", "instructions")
_TOOL_DECORATORS = ("tool", "function_tool", "tool_node")
_RETRY_DECORATORS = ("retry", "retries")
_CACHE_DECORATORS = ("lru_cache", "cache", "cached")
_EDGE_METHODS = ("add_edge", "add_conditional_edges")
_AGENT_NAME_HINTS = ("agent", "assistant", "worker", "expert", "planner", "researcher", "node")
_UNBOUNDED_ITERS = ("count", "cycle", "repeat")


def _deco_name(node: ast.expr) -> str:
    """Nome-base de um decorador/chamada (Name | Attribute | Call)."""
    if isinstance(node, ast.Call):
        return _deco_name(node.func)
    if isinstance(node, ast.Attribute):
        return node.attr
    if isinstance(node, ast.Name):
        return node.id
    return ""


def _expr_str(node: ast.expr) -> str:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    try:
        return ast.unparse(node)
    except Exception:  # pragma: no cover - unparse é robusto no 3.12
        return "<expr>"


def _prompt_role(hint: str) -> str:
    h = hint.lower()
    if "system" in h:
        return "system"
    if "user" in h:
        return "user"
    return "unknown"


def _has_own_break(loop: ast.For | ast.While) -> bool:
    """True se há `break` pertencente A ESTE loop (ignora loops aninhados no corpo)."""
    for stmt in loop.body:
        if isinstance(stmt, ast.For | ast.While):
            continue  # breaks de loops aninhados não quebram este
        for n in ast.walk(stmt):
            if isinstance(n, ast.Break):
                return True
    return False


class _FileVisitor(ast.NodeVisitor):
    def __init__(self, path: str, source: str) -> None:
        self.path = path
        self.lines = source.splitlines()
        self.scope: list[str] = []
        self.loop_idx = 0
        self.agents: list[AgentNode] = []
        self.prompts: list[PromptRef] = []
        self.tools: list[ToolDef] = []
        self.edges: list[Edge] = []
        self.loops: list[LoopInfo] = []
        self.model_assignments: list[ModelAssignment] = []
        self.configs: list[ConfigItem] = []
        self.error_handling: list[ErrorHandling] = []
        self.shared_state: list[SharedStateRef] = []

    # ---- helpers ----
    def _sym(self, name: str | None = None) -> str:
        parts = [*self.scope, name] if name else list(self.scope)
        return ".".join(p for p in parts if p) or "<module>"

    def _ev(self, node: ast.AST, symbol: str, kind: str) -> EvidenceRef:
        ln = getattr(node, "lineno", None)
        snippet = self.lines[ln - 1].strip()[:120] if ln and ln <= len(self.lines) else None
        return EvidenceRef(
            file_path=self.path,
            symbol=symbol,
            component_kind=kind,
            line_start=ln,
            line_end=getattr(node, "end_lineno", None),
            snippet=snippet or None,
        )

    # ---- escopos ----
    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        bases = [_deco_name(b) for b in node.bases]
        sym = self._sym(node.name)
        if "TypedDict" in bases:
            self.shared_state.append(
                SharedStateRef(
                    name=node.name, kind="typed_dict", evidence=self._ev(node, sym, "shared_state")
                )
            )
        elif node.name.endswith("State"):
            self.shared_state.append(
                SharedStateRef(
                    name=node.name, kind="state_class", evidence=self._ev(node, sym, "shared_state")
                )
            )
        self.agents.append(
            AgentNode(name=node.name, role="class", evidence=self._ev(node, sym, "agent"))
        )
        self.scope.append(node.name)
        self.generic_visit(node)
        self.scope.pop()

    def _visit_func(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        sym = self._sym(node.name)
        decos = [_deco_name(d) for d in node.decorator_list]
        params = [a.arg for a in node.args.args]
        if any(d in _TOOL_DECORATORS for d in decos):
            self.tools.append(
                ToolDef(
                    name=node.name,
                    description=ast.get_docstring(node),
                    params=params,
                    evidence=self._ev(node, sym, "tool"),
                )
            )
        if any(d in _RETRY_DECORATORS for d in decos):
            self.error_handling.append(
                ErrorHandling(
                    symbol=sym, kind="retry", evidence=self._ev(node, sym, "error_handling")
                )
            )
        if any(d in _CACHE_DECORATORS for d in decos):
            self.error_handling.append(
                ErrorHandling(
                    symbol=sym, kind="cache", evidence=self._ev(node, sym, "error_handling")
                )
            )
        if any(h in node.name.lower() for h in _AGENT_NAME_HINTS):
            self.agents.append(
                AgentNode(name=node.name, role="function", evidence=self._ev(node, sym, "agent"))
            )
        if "state" in params:
            self.shared_state.append(
                SharedStateRef(
                    name=node.name, kind="state_param", evidence=self._ev(node, sym, "shared_state")
                )
            )
        self.scope.append(node.name)
        self.generic_visit(node)
        self.scope.pop()

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._visit_func(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._visit_func(node)

    # ---- statements ----
    def visit_Assign(self, node: ast.Assign) -> None:
        for tgt in node.targets:
            if not isinstance(tgt, ast.Name):
                continue
            name = tgt.id
            is_str = isinstance(node.value, ast.Constant) and isinstance(node.value.value, str)
            if any(h in name.lower() for h in _PROMPT_NAME_HINTS) and (
                is_str or isinstance(node.value, ast.JoinedStr)
            ):
                self.prompts.append(
                    PromptRef(
                        name=name,
                        text=_expr_str(node.value),
                        role=_prompt_role(name),
                        evidence=self._ev(node, self._sym(name), "prompt"),
                    )
                )
            elif name.isupper():
                self.configs.append(
                    ConfigItem(
                        key=name,
                        value_expr=_expr_str(node.value),
                        evidence=self._ev(node, self._sym(name), "config"),
                    )
                )
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        fname = _deco_name(node.func)
        if fname in _EDGE_METHODS:
            src = _expr_str(node.args[0]) if node.args else "?"
            tgt = (
                "<conditional>"
                if fname == "add_conditional_edges"
                else (_expr_str(node.args[1]) if len(node.args) > 1 else "?")
            )
            self.edges.append(
                Edge(source=src, target=tgt, evidence=self._ev(node, self._sym(), "edge"))
            )
        for kw in node.keywords:
            if kw.arg in _PROMPT_KW and isinstance(kw.value, ast.Constant | ast.JoinedStr):
                self.prompts.append(
                    PromptRef(
                        name=f"{fname}:{kw.arg}",
                        text=_expr_str(kw.value),
                        role=_prompt_role(kw.arg),
                        evidence=self._ev(node, self._sym(), "prompt"),
                    )
                )
            elif kw.arg == "model":
                self.model_assignments.append(
                    ModelAssignment(
                        node=self._sym(),
                        model_expr=_expr_str(kw.value),
                        evidence=self._ev(node, self._sym(), "model_assignment"),
                    )
                )
            elif kw.arg == "timeout":
                self.error_handling.append(
                    ErrorHandling(
                        symbol=self._sym(),
                        kind="timeout",
                        evidence=self._ev(node, self._sym(), "error_handling"),
                    )
                )
            elif kw.arg in ("stream", "streaming"):
                self.error_handling.append(
                    ErrorHandling(
                        symbol=self._sym(),
                        kind="streaming",
                        evidence=self._ev(node, self._sym(), "error_handling"),
                    )
                )
        self.generic_visit(node)

    def visit_Try(self, node: ast.Try) -> None:
        self.error_handling.append(
            ErrorHandling(
                symbol=self._sym(),
                kind="try_except",
                evidence=self._ev(node, self._sym(), "error_handling"),
            )
        )
        self.generic_visit(node)

    def visit_For(self, node: ast.For) -> None:
        self.loop_idx += 1
        has_cap = True
        reason = "itera sobre coleção/range finito"
        if isinstance(node.iter, ast.Call) and _deco_name(node.iter.func) in _UNBOUNDED_ITERS:
            has_cap = False
            reason = f"itera sobre {_deco_name(node.iter.func)}() sem limite"
        self.loops.append(
            LoopInfo(
                symbol=f"{self._sym()}:for#{self.loop_idx}",
                kind="for",
                has_cap=has_cap,
                cap_reason=reason,
                evidence=self._ev(node, self._sym(), "loop"),
            )
        )
        self.generic_visit(node)

    def visit_While(self, node: ast.While) -> None:
        self.loop_idx += 1
        is_true = isinstance(node.test, ast.Constant) and bool(node.test.value) is True
        has_break = _has_own_break(node)
        if is_true and not has_break:
            has_cap = False
            reason = "while True sem break — loop potencialmente infinito"
        else:
            has_cap = True
            reason = "tem break" if has_break else "condição de parada variável"
        self.loops.append(
            LoopInfo(
                symbol=f"{self._sym()}:while#{self.loop_idx}",
                kind="while",
                has_cap=has_cap,
                cap_reason=reason,
                evidence=self._ev(node, self._sym(), "loop"),
            )
        )
        self.generic_visit(node)


class PythonExtractor:
    """Extrator estático Python (`ast`). Implementa `LanguageExtractor`."""

    language = "python"

    def extract(self, files: dict[str, str]) -> ExtractionResult:
        agg = _FileVisitor("", "")
        seen_files: list[str] = []
        unreadable: list[str] = []
        for path, source in files.items():
            seen_files.append(path)
            try:
                tree = ast.parse(source, filename=path)
            except SyntaxError:
                unreadable.append(path)  # ofuscado/inválido → marca, não quebra (RF-03)
                continue
            v = _FileVisitor(path, source)
            v.visit(tree)
            agg.agents += v.agents
            agg.prompts += v.prompts
            agg.tools += v.tools
            agg.edges += v.edges
            agg.loops += v.loops
            agg.model_assignments += v.model_assignments
            agg.configs += v.configs
            agg.error_handling += v.error_handling
            agg.shared_state += v.shared_state
        return ExtractionResult(
            files=seen_files,
            agents=agg.agents,
            prompts=agg.prompts,
            tools=agg.tools,
            edges=agg.edges,
            loops=agg.loops,
            model_assignments=agg.model_assignments,
            configs=agg.configs,
            error_handling=agg.error_handling,
            shared_state=agg.shared_state,
            unreadable_files=unreadable,
        )
