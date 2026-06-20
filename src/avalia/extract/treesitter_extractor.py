"""M10 — 2º extrator (TS/JS) via tree-sitter (Decisão Técnica #1; mitiga o Risco R1).

Extração **estrutural / best-effort** de sistemas multiagentes em JavaScript/TypeScript,
plugando na MESMA interface `LanguageExtractor` (T-101) e produzindo os mesmos fragmentos do TSM
que o extrator Python — **sem tocar o TSM nem os avaliadores** (resolução #1). É leitura estática
pura: `tree_sitter` constrói a árvore sintática a partir do TEXTO-fonte; nada importa, executa ou
avalia o alvo (RNF-05/S-04).

Escopo (deliberadamente raso): **sem inferência de tipos**. Cobre as categorias de maior sinal
que classificação e avaliadores consomem — agentes, prompts, arestas (`addEdge`/
`addConditionalEdges` do LangGraph.js), loops (com teto best-effort), atribuições de modelo,
estado compartilhado e sinais de robustez (try/catch, retry, timeout, streaming, fallback, cache,
validação). A confiança reduzida desta análise é **declarada** no laudo (RNF-08) pelo tsm_builder.

As gramáticas são importadas de forma PREGUIÇOSA: o módulo importa mesmo sem elas; se faltarem,
o registry simplesmente não registra os extratores e os arquivos caem em best-effort.

Rastreabilidade: RF-14, RNF-07, RNF-05/S-04, RNF-08; plan §3.1; Decisão #1; Risco R1.
"""

from __future__ import annotations

from functools import cache
from typing import Any

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

# Heurísticas (lowercase para casar com os identificadores do alvo).
_PROMPT_NAME_HINTS = ("prompt", "system", "instruction", "instructions", "template", "persona")
_PROMPT_KEYS = ("system", "systemprompt", "system_prompt", "prompt", "instructions")
_AGENT_NAME_HINTS = ("agent", "assistant", "worker", "expert", "planner", "researcher", "node")
_EDGE_METHODS = ("addedge", "addconditionaledges")
_MODEL_KEYS = ("model", "modelname", "model_name")
_TOKEN_KEYS = ("maxtokens", "max_tokens", "maxoutputtokens", "max_output_tokens")
_TIMEOUT_KEYS = ("timeout", "timeout_s", "requesttimeout", "request_timeout")
_STREAM_KEYS = ("stream", "streaming")
# Tokens ESPECÍFICOS (evita falso positivo de substring — lição do retr/tries do extrator Python).
_RETRY_TOKENS = ("retry", "retries", "pretry", "withretry", "maxretries", "max_retries", "backoff")
_FALLBACK_TOKENS = ("withfallbacks", "fallback", "fallbacks", "fallbackmodel", "fallback_model")
_VALIDATION_MEMBERS = ("parse", "safeparse", "validate")
_STRING_TYPES = ("string", "template_string")


@cache
def _parser_for(language: str) -> Any | None:
    """Parser tree-sitter para a linguagem (lazy). `None` se a gramática não estiver instalada."""
    try:
        import tree_sitter as ts

        if language == "javascript":
            import tree_sitter_javascript as gjs

            lang = ts.Language(gjs.language())
        elif language == "typescript":
            import tree_sitter_typescript as gts

            lang = ts.Language(gts.language_typescript())
        else:  # pragma: no cover - linguagem desconhecida
            return None
        return ts.Parser(lang)
    except Exception:  # pragma: no cover - gramática ausente/ABI incompatível → best-effort
        return None


def is_available(language: str) -> bool:
    return _parser_for(language) is not None


def _matches(name: str, hints: tuple[str, ...]) -> bool:
    low = name.lower()
    return any(h in low for h in hints)


class _Walker:
    """Percorre a árvore tree-sitter mantendo o escopo (símbolo) e coletando fragmentos do TSM."""

    def __init__(self, path: str, source: bytes) -> None:
        self.path = path
        self.source = source
        self.lines = source.decode("utf-8", "replace").splitlines()
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
    def _txt(self, node: Any) -> str:
        return self.source[node.start_byte : node.end_byte].decode("utf-8", "replace")

    def _sym(self, name: str | None = None) -> str:
        parts = [*self.scope, name] if name else list(self.scope)
        return ".".join(p for p in parts if p) or "<module>"

    def _ev(self, node: Any, symbol: str, kind: str) -> EvidenceRef:
        ln = node.start_point[0] + 1
        snippet = self.lines[ln - 1].strip()[:120] if 0 < ln <= len(self.lines) else None
        return EvidenceRef(
            file_path=self.path,
            symbol=symbol,
            component_kind=kind,
            line_start=ln,
            line_end=node.end_point[0] + 1,
            snippet=snippet or None,
        )

    def _str_value(self, node: Any) -> str:
        """Texto de um literal string/template (sem aspas/backticks)."""
        raw = self._txt(node)
        return raw.strip("\"'`")

    def _add_eh(self, node: Any, kind: str) -> None:
        self.error_handling.append(
            ErrorHandling(
                symbol=self._sym(),
                kind=kind,
                evidence=self._ev(node, self._sym(), "error_handling"),
            )
        )

    def _field(self, node: Any, name: str) -> Any | None:
        return node.child_by_field_name(name)

    def _param_names(self, fn_node: Any) -> list[str]:
        params = self._field(fn_node, "parameters")
        if params is None:
            # arrow sem parênteses (`state => ...`): 1º filho identifier é o parâmetro.
            first = fn_node.named_children[0] if fn_node.named_children else None
            return [self._txt(first)] if first is not None and first.type == "identifier" else []
        names: list[str] = []
        for child in params.named_children:
            if child.type == "identifier":
                names.append(self._txt(child))
            else:  # required_parameter/optional_parameter (TS): pega o identifier interno
                ident = self._field(child, "pattern") or child
                if ident is not None and ident.type == "identifier":
                    names.append(self._txt(ident))
        return names

    # ---- dispatch ----
    def walk(self, node: Any) -> None:
        pushed = self._enter_scope(node)
        handler = getattr(self, f"_on_{node.type}", None)
        if handler is not None:
            handler(node)
        for child in node.named_children:
            self.walk(child)
        if pushed:
            self.scope.pop()

    def _enter_scope(self, node: Any) -> bool:
        if node.type in ("function_declaration", "method_definition", "class_declaration"):
            name_node = self._field(node, "name")
            name = self._txt(name_node) if name_node is not None else None
            self.scope.append(name or "<anon>")
            return True
        # arrow/função atribuída a const (ex.: `const agent = async (state) => {...}`): o escopo
        # interno (loops/prompts) deve usar o nome da variável.
        if node.type == "variable_declarator":
            name_node = self._field(node, "name")
            value = self._field(node, "value")
            if (
                name_node is not None
                and name_node.type == "identifier"
                and value is not None
                and value.type in ("arrow_function", "function_expression")
            ):
                self.scope.append(self._txt(name_node))
                return True
        return False

    # ---- node handlers ----
    def _on_class_declaration(self, node: Any) -> None:
        name_node = self._field(node, "name")
        name = self._txt(name_node) if name_node is not None else "<anon>"
        sym = self._sym()  # já dentro do escopo (push em _enter_scope)
        self.agents.append(
            AgentNode(name=name, role="class", evidence=self._ev(node, sym, "agent"))
        )
        low = name.lower()
        if low.endswith("state"):
            self.shared_state.append(
                SharedStateRef(
                    name=name, kind="state_class", evidence=self._ev(node, sym, "shared_state")
                )
            )
        if low.endswith("cache"):
            self._add_eh(node, "cache")

    def _on_function_declaration(self, node: Any) -> None:
        self._maybe_agent_and_state(node)

    def _on_method_definition(self, node: Any) -> None:
        self._maybe_agent_and_state(node)

    def _maybe_agent_and_state(self, node: Any) -> None:
        name = self.scope[-1] if self.scope else "<anon>"
        sym = self._sym()
        if _matches(name, _AGENT_NAME_HINTS):
            self.agents.append(
                AgentNode(name=name, role="function", evidence=self._ev(node, sym, "agent"))
            )
        if "state" in self._param_names(node):
            self.shared_state.append(
                SharedStateRef(
                    name=name, kind="state_param", evidence=self._ev(node, sym, "shared_state")
                )
            )

    def _on_variable_declarator(self, node: Any) -> None:
        name_node = self._field(node, "name")
        value = self._field(node, "value")
        if name_node is None or name_node.type != "identifier":
            return
        name = self._txt(name_node)
        # const agent = async (state) => {...}: aqui o escopo já tem `name` (push em _enter_scope).
        if value is not None and value.type in ("arrow_function", "function_expression"):
            sym = self._sym()
            if _matches(name, _AGENT_NAME_HINTS):
                self.agents.append(
                    AgentNode(name=name, role="function", evidence=self._ev(node, sym, "agent"))
                )
            if "state" in self._param_names(value):
                self.shared_state.append(
                    SharedStateRef(
                        name=name, kind="state_param", evidence=self._ev(node, sym, "shared_state")
                    )
                )
            return
        # const PROMPT-ish = "..." / `...`
        if value is not None and value.type in _STRING_TYPES and _matches(name, _PROMPT_NAME_HINTS):
            self.prompts.append(
                PromptRef(
                    name=name,
                    text=self._str_value(value),
                    role=_prompt_role(name),
                    evidence=self._ev(node, self._sym(name), "prompt"),
                )
            )
        # const UPPER = ... → item de config (mesma convenção do extrator Python)
        elif name.isupper() and value is not None:
            self.configs.append(
                ConfigItem(
                    key=name,
                    value_expr=self._txt(value)[:200],
                    evidence=self._ev(node, self._sym(name), "config"),
                )
            )

    def _on_pair(self, node: Any) -> None:
        key_node = self._field(node, "key")
        value = self._field(node, "value")
        if key_node is None:
            return
        key = self._txt(key_node).strip("\"'").lower()
        if value is not None and value.type in _STRING_TYPES and key in _PROMPT_KEYS:
            self.prompts.append(
                PromptRef(
                    name=key,
                    text=self._str_value(value),
                    role=_prompt_role(key),
                    evidence=self._ev(node, self._sym(), "prompt"),
                )
            )
        elif key in _MODEL_KEYS and value is not None:
            self.model_assignments.append(
                ModelAssignment(
                    node=self._sym(),
                    model_expr=self._txt(value).strip("\"'`"),
                    evidence=self._ev(node, self._sym(), "model_assignment"),
                )
            )
        elif key in _TOKEN_KEYS:
            self._add_eh(node, "token_limit")
        elif key in _TIMEOUT_KEYS:
            self._add_eh(node, "timeout")
        elif key in _STREAM_KEYS:
            self._add_eh(node, "streaming")
        elif key == "cache":
            self._add_eh(node, "cache")

    def _on_call_expression(self, node: Any) -> None:
        fn = self._field(node, "function")
        prop = ""
        if fn is not None and fn.type == "member_expression":
            p = self._field(fn, "property")
            prop = self._txt(p).lower() if p is not None else ""
        elif fn is not None and fn.type == "identifier":
            prop = self._txt(fn).lower()
        args = self._field(node, "arguments")
        if prop in _EDGE_METHODS:
            self._record_edge(node, prop, args)
        if prop in _RETRY_TOKENS:
            self._add_eh(node, "retry")
        if prop in _FALLBACK_TOKENS:
            self._add_eh(node, "fallback_modelo")
        if prop in _VALIDATION_MEMBERS:
            self._add_eh(node, "input_validation")
        if prop in _STREAM_KEYS:
            self._add_eh(node, "streaming")

    def _record_edge(self, node: Any, method: str, args: Any) -> None:
        str_args = [
            a for a in (args.named_children if args is not None else []) if a.type in _STRING_TYPES
        ]
        src = self._str_value(str_args[0]) if str_args else "?"
        if method == "addconditionaledges":
            tgt = "<conditional>"
        else:
            tgt = self._str_value(str_args[1]) if len(str_args) > 1 else "?"
        self.edges.append(
            Edge(source=src, target=tgt, evidence=self._ev(node, self._sym(), "edge"))
        )

    def _on_try_statement(self, node: Any) -> None:
        self._add_eh(node, "try_except")
        # retry imperativo: catch com continue dentro de loop
        catch = next((c for c in node.named_children if c.type == "catch_clause"), None)
        if catch is not None and _has_descendant(catch, "continue_statement"):
            self._add_eh(node, "retry")

    def _on_while_statement(self, node: Any) -> None:
        self.loop_idx += 1
        cond = self._field(node, "condition")
        is_true = cond is not None and _has_descendant(cond, "true")
        has_break = _has_own_break(node)
        if is_true and not has_break:
            has_cap, reason = False, "while(true) sem break — loop potencialmente infinito"
        else:
            has_cap, reason = True, ("tem break" if has_break else "condição de parada variável")
        self.loops.append(
            LoopInfo(
                symbol=f"{self._sym()}:while#{self.loop_idx}",
                kind="while",
                has_cap=has_cap,
                cap_reason=reason,
                evidence=self._ev(node, self._sym(), "loop"),
            )
        )

    def _on_for_statement(self, node: Any) -> None:
        self._record_capped_loop(node, "for", "for com cláusulas de parada")

    def _on_for_in_statement(self, node: Any) -> None:
        self._record_capped_loop(node, "for", "itera sobre coleção (for...of/in)")

    def _record_capped_loop(self, node: Any, kind: str, reason: str) -> None:
        self.loop_idx += 1
        self.loops.append(
            LoopInfo(
                symbol=f"{self._sym()}:{kind}#{self.loop_idx}",
                kind=kind,
                has_cap=True,
                cap_reason=reason,
                evidence=self._ev(node, self._sym(), "loop"),
            )
        )

    def _on_interface_declaration(self, node: Any) -> None:
        self._maybe_state_type(node)

    def _on_type_alias_declaration(self, node: Any) -> None:
        self._maybe_state_type(node)

    def _maybe_state_type(self, node: Any) -> None:
        name_node = self._field(node, "name")
        if name_node is None:
            return
        name = self._txt(name_node)
        if name.lower().endswith("state"):
            self.shared_state.append(
                SharedStateRef(
                    name=name,
                    kind="state_class",
                    evidence=self._ev(node, self._sym(name), "shared_state"),
                )
            )


def _prompt_role(hint: str) -> str:
    h = hint.lower()
    if "system" in h:
        return "system"
    if "user" in h:
        return "user"
    return "unknown"


def _has_descendant(node: Any, type_name: str) -> bool:
    stack = [node]
    while stack:
        n = stack.pop()
        if n.type == type_name:
            return True
        stack.extend(n.named_children)
    return False


def _has_own_break(loop: Any) -> bool:
    """`break` deste loop (ignora loops aninhados)."""
    body = loop.child_by_field_name("body")
    if body is None:
        return False
    for stmt in body.named_children:
        if stmt.type in ("while_statement", "for_statement", "for_in_statement"):
            continue
        if _has_descendant(stmt, "break_statement"):
            return True
    return False


class _TreeSitterExtractor:
    """Base dos extratores tree-sitter (JS/TS compartilham o mesmo walker)."""

    language: str

    def extract(self, files: dict[str, str]) -> ExtractionResult:
        parser = _parser_for(self.language)
        seen: list[str] = []
        unreadable: list[str] = []
        agg = _Walker("", b"")
        if parser is None:  # gramática ausente → tudo best-effort (não quebra)
            return ExtractionResult(files=list(files), unreadable_files=list(files))
        for path, source in files.items():
            seen.append(path)
            tree = parser.parse(source.encode("utf-8"))
            root = tree.root_node
            if root.child_count == 0:  # nada parseável → ilegível (T-104)
                unreadable.append(path)
                continue
            w = _Walker(path, source.encode("utf-8"))
            w.walk(root)
            agg.agents += w.agents
            agg.prompts += w.prompts
            agg.tools += w.tools
            agg.edges += w.edges
            agg.loops += w.loops
            agg.model_assignments += w.model_assignments
            agg.configs += w.configs
            agg.error_handling += w.error_handling
            agg.shared_state += w.shared_state
        return ExtractionResult(
            files=seen,
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


class JavaScriptExtractor(_TreeSitterExtractor):
    language = "javascript"


class TypeScriptExtractor(_TreeSitterExtractor):
    language = "typescript"
