"""T-105 — Priorização de arquivos por SINAL (RF-12, CB-05).

Ranqueia os arquivos do alvo por densidade de sinal de avaliação, para que, acima do teto de
cobertura (`max_analyzed_files`), os arquivos de maior sinal sejam analisados integralmente e o
restante seja amostrado (declarado em `AnalysisCoverage`). Heurística determinística por nome +
cues de conteúdo. Ordem de sinal (plan §3.1):
grafo/orquestração > prompts > ferramentas > config > harness > resto.

A função é PURA e estável (desempate por caminho) → suporta reprodutibilidade (RNF-01).

Rastreabilidade: RF-12, CB-05; CA-13; plan §3.1.
"""

from __future__ import annotations

_GRAPH_CUES = ("stategraph", "add_edge", "add_conditional_edges", "add_node", "workflow", "graph(")
_PROMPT_CUES = ("prompt", "system_prompt", "instructions", "persona", "template")
_TOOL_CUES = ("@tool", "function_tool", "tool_node", "def tool", "tools=")
_CONFIG_CUES = ("config", "settings", "os.environ", "getenv", "model=")
_HARNESS_HINTS = ("test_", "_test", "/tests/", "/test/", "conftest")


def _signal(path: str, source: str) -> int:
    """Pontuação de sinal do arquivo (maior = mais prioritário)."""
    low = path.replace("\\", "/").lower()
    body = source.lower()
    # Harness é sinal baixo (importante para Qualidade, mas não é o coração da arquitetura).
    if any(h in low for h in _HARNESS_HINTS):
        return 10
    score = 0
    if any(c in body for c in _GRAPH_CUES):
        score += 100
    if any(c in body for c in _PROMPT_CUES) or "prompt" in low:
        score += 60
    if any(c in body for c in _TOOL_CUES):
        score += 40
    if any(c in body for c in _CONFIG_CUES) or low.rsplit("/", 1)[-1].startswith(
        ("config", "settings")
    ):
        score += 20
    return score


def rank_files(files: dict[str, str]) -> list[str]:
    """Caminhos ordenados por sinal decrescente; desempate estável por caminho."""
    return sorted(files, key=lambda p: (-_signal(p, files[p]), p))
