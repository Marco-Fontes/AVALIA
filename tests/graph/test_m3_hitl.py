"""CA-10 / CA-11 — divergência reconciliada (auto) e escalada ao humano (HITL), ponta-a-ponta.

`ScriptedGateway` induz divergência (faixas distintas) na Robustez e controla a reconciliação:
convergente (CA-10, sem humano) ou persistente (CA-11, escala via `human_gate` + runner).
Gateway MOCKADO; nada chama modelo real nem executa o alvo.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from avalia.config.evaluator_config import RetryPolicy
from avalia.domain.contracts import HumanDecision
from avalia.domain.enums import Band, Confidence, Dimension
from avalia.domain.submission import Submission, TargetMetadata
from avalia.graph.build_graph import build_avalia_graph
from avalia.hitl.approval import StaticApprovalProvider
from avalia.hitl.runner import run_evaluation
from avalia.judge.framework import JudgeVerdict

pytestmark = pytest.mark.fast

_FIX = Path(__file__).resolve().parents[1] / "fixtures"
_META = TargetMetadata(target_id="alvo", version="v1")


def _load(name: str) -> dict[str, str]:
    return {f.name: f.read_text(encoding="utf-8") for f in (_FIX / name).glob("*.py")}


def _v(band: Band, conf: Confidence = Confidence.ALTO) -> JudgeVerdict:
    return JudgeVerdict(score=70, band=band, confidence=conf, reasoning="r")


class _ScriptedClient:
    def __init__(self, gw, node_type):
        self._gw = gw
        self._node_type = node_type

    def invoke(self, messages):
        return self._gw.next_verdict(self._node_type)


class ScriptedGateway:
    """Fila de JudgeVerdict por node_type; `default` para os demais juízes (convergentes)."""

    def __init__(self, scripts: dict[str, list[JudgeVerdict]], default: JudgeVerdict):
        self._scripts = {k: list(v) for k, v in scripts.items()}
        self._default = default

    def with_structured_output(self, node_type, role, schema):
        return _ScriptedClient(self, node_type)

    def retry_for(self, node_type):
        return RetryPolicy(max_attempts=2)

    def next_verdict(self, node_type):
        queue = self._scripts.get(node_type)
        return queue.pop(0) if queue else self._default


def _robustez_gateway(reconcile_bands: list[Band]) -> ScriptedGateway:
    # painel inicial diverge (PRONTO vs INSUFICIENTE); reconciliação = reconcile_bands
    script = {
        "juiz_robustez": [_v(Band.PRONTO), _v(Band.INSUFICIENTE), *[_v(b) for b in reconcile_bands]]
    }
    return ScriptedGateway(script, default=_v(Band.PRONTO))


def _sub() -> Submission:
    return Submission(artifact_files=_load("multiagente_loop_sem_teto"), metadata=_META)


def test_ca10_divergence_reconciled_automatically_no_hitl():
    # reconciliação converge → resolvida sem humano, registrada (CA-10)
    gw = _robustez_gateway([Band.ADEQUADO_COM_RESSALVAS, Band.ADEQUADO_COM_RESSALVAS])
    result = build_avalia_graph(gateway=gw).invoke(
        {"submission": _sub()}, config={"configurable": {"thread_id": "ca10"}}
    )
    assert "__interrupt__" not in result  # não acionou o humano
    report = result["report"]
    robustez_div = [d for d in report.divergences if d.dimension is Dimension.ROBUSTEZ]
    assert robustez_div and robustez_div[0].resolved_by.value == "auto"


def test_ca11_persistent_divergence_escalates_to_human():
    # reconciliação persiste → human_gate; runner resolve via decisão estática (CA-11)
    gw = _robustez_gateway([Band.PRONTO, Band.INSUFICIENTE])
    graph = build_avalia_graph(gateway=gw)
    provider = StaticApprovalProvider(
        [
            HumanDecision(
                dimension=Dimension.ROBUSTEZ,
                chosen_band=Band.INSUFICIENTE,
                note="mantenho a ressalva",
            )
        ]
    )
    result = run_evaluation(
        graph, {"submission": _sub()}, approval_provider=provider, thread_id="ca11"
    )
    report = result["report"]
    robustez_div = [d for d in report.divergences if d.dimension is Dimension.ROBUSTEZ]
    assert robustez_div and robustez_div[0].resolved_by.value == "humano"
    assert robustez_div[0].resolution_note == "mantenho a ressalva"
    # divergência escalada reduz a confiança reportada da dimensão (decisão M3)
    robustez_dim = next(dr for dr in report.dimensions if dr.dimension is Dimension.ROBUSTEZ)
    assert robustez_dim.confidence is not Confidence.ALTO
    assert any(
        "decisão humana" in lim.lower() or "humano" in lim.lower()
        for lim in report.metadata.known_limitations
    )
