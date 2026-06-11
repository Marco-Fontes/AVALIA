"""CA-15 / CB-06 — comparação histórica ponta-a-ponta com o repositório de laudos.

Roda DETERMINISTICAMENTE (sem juiz): v1 (alvo pobre) e v2 (mesmo target_id, com retry/timeout/
cache/validação) → v2 mostra melhorias e achados resolvidos. 1ª versão → sem comparação (CB-06).
Nada executa o alvo (lido como texto); nenhum modelo real.
"""

from __future__ import annotations

import pytest

from avalia.domain.enums import Dimension
from avalia.domain.submission import Submission, TargetMetadata
from avalia.domain.taxonomy import FindingType
from avalia.graph.build_graph import build_avalia_graph
from avalia.persistence.repository import InMemoryReportRepository

pytestmark = pytest.mark.fast

_V1 = """
PROMPT = "Você é um assistente."


def agent(state):
    return call(model=m)
"""

_V2 = """
from functools import lru_cache


PROMPT = "Você é um assistente."


@retry
def agent(state):
    if not isinstance(state, dict):
        raise ValueError("entrada inválida")
    try:
        return call(model=m, timeout=10, max_tokens=256, fallback=alt)
    except Exception:
        return None


@lru_cache
def cached():
    return 1
"""


def _run(graph, source: str, version: str) -> dict:
    sub = Submission(
        artifact_files={"main.py": source},
        metadata=TargetMetadata(target_id="t", version=version),
    )
    return graph.invoke({"submission": sub}, config={"configurable": {"thread_id": version}})


def test_ca15_and_cb06_history_comparison():
    repo = InMemoryReportRepository()
    graph = build_avalia_graph(repository=repo)

    # v1: primeira versão → CB-06 (sem comparação + nota)
    report1 = _run(graph, _V1, "1")["report"]
    assert report1.comparison is None
    assert any("versão anterior" in lim.lower() for lim in report1.metadata.known_limitations)

    # v2: melhorias em robustez/performance/custo; achados resolvidos; vínculo ao laudo anterior
    report2 = _run(graph, _V2, "2")["report"]
    comp = report2.comparison
    assert comp is not None
    assert comp.improvements  # CA-15: melhorias listadas
    assert any(s.startswith("robustez:") for s in comp.improvements)
    assert comp.deltas[Dimension.ROBUSTEZ] > 0

    # SEM_RETRY (robustez), presente em v1, foi resolvido em v2 (identidade estável)
    sem_retry_id = next(
        f.identity
        for dr in report1.dimensions
        for f in dr.findings
        if f.finding_type is FindingType.SEM_RETRY
    )
    assert sem_retry_id in comp.resolved_findings
    assert comp.prev_report_id  # rastreável ao laudo v1
