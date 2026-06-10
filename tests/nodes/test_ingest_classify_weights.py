"""T-201/203/204 — testes dos nós N0–N3 (ingest, classify, select_weights).

Valida CA-01 (erro sem laudo), CA-02 (borderline + confiança), renormalização (RF-21).
"""

from __future__ import annotations

import pytest

from avalia.classify import classify_target
from avalia.config.evaluator_config import EvaluatorConfig
from avalia.config.weight_profiles import load_weight_profiles
from avalia.domain.enums import Confidence, Dimension, RunStatus, Topology
from avalia.domain.submission import Submission, TargetMetadata
from avalia.domain.weights import WeightSource
from avalia.extract.tsm_builder import build_tsm
from avalia.ingest import ingest_validate
from avalia.weights_select import renormalize, select_weights

pytestmark = pytest.mark.fast

_META = TargetMetadata(target_id="t1", version="v1")

_MULTI = """
from typing import TypedDict


class S(TypedDict):
    q: str


A_PROMPT = "Você é o planejador."
B_PROMPT = "Você é o executor."


def build(g):
    g.add_edge("a", "b")
"""

_SINGLE = 'SYSTEM_PROMPT = "Você é um assistente único."\n'


def test_ingest_error_without_source_no_report():
    # CA-01: submissão sem código-fonte → status=error, mensagem cita componente
    sub = Submission(artifact_files={"README.md": "# só docs"}, metadata=_META)
    out = ingest_validate(sub)
    assert out.status is RunStatus.ERROR
    assert "código-fonte" in out.error_message
    assert "codigo_fonte" in out.inventory.missing


def test_ingest_ok_with_source():
    sub = Submission(artifact_files={"main.py": _SINGLE}, metadata=_META)
    out = ingest_validate(sub)
    assert out.status is RunStatus.OK
    assert "codigo_fonte" in out.inventory.present


def test_classify_multiagent_with_confidence():
    tsm = build_tsm({"main.py": _MULTI})
    c = classify_target(tsm)
    assert c.topology is Topology.MULTIAGENTE
    assert c.classification_conf in (Confidence.MEDIO, Confidence.ALTO)
    assert len(c.topology_signals) >= 2


def test_classify_single_is_borderline_not_refused():
    # CA-02: um prompt, sem orquestração → borderline, confiança explícita, sem recusa
    tsm = build_tsm({"main.py": _SINGLE})
    c = classify_target(tsm)
    assert c.topology is Topology.AGENTE_UNICO_BORDERLINE
    assert c.classification_conf is not None
    assert c.caveats  # ressalva registrada (RF-07)


def test_select_weights_neutral_fallback_when_type_unknown():
    tsm = build_tsm({"main.py": _MULTI})
    c = classify_target(tsm)
    sel = select_weights(c, EvaluatorConfig(), load_weight_profiles())
    assert sel.profile.source is WeightSource.FALLBACK_NEUTRO
    assert abs(sum(sel.profile.weights.values()) - 1.0) < 1e-6


def test_user_override_takes_precedence_and_renormalizes():
    tsm = build_tsm({"main.py": _MULTI})
    c = classify_target(tsm)
    cfg = EvaluatorConfig(weights={Dimension.CUSTO: 2.0, Dimension.ROBUSTEZ: 2.0})
    sel = select_weights(c, cfg, load_weight_profiles())
    assert sel.profile.source is WeightSource.SOBRESCRITO
    assert abs(sum(sel.profile.weights.values()) - 1.0) < 1e-6


def test_renormalize_excludes_and_sums_to_one():
    weights = dict.fromkeys(Dimension, 1.0)  # 7 iguais
    applicable = [Dimension.CUSTO, Dimension.ROBUSTEZ, Dimension.TRAJETORIA]
    out = renormalize(weights, applicable)
    assert set(out) == set(applicable)
    assert abs(sum(out.values()) - 1.0) < 1e-9
