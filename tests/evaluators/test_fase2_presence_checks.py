"""Fase 1 Tier 2 — componente de checks de presença de harness.

SEM_SAIDA_ESTRUTURADA, SEM_PROMPT_CACHE (Custo), SEM_CHECKPOINT_ESTADO, SEM_OBSERVABILIDADE.
Para cada: ausência do mecanismo dispara; presença não dispara. Pré-condição exige Python + alvo
com modelo/grafo (não dispara em alvo trivial). Nada executa o alvo.
"""

from __future__ import annotations

import pytest

from avalia.domain.enums import Dimension
from avalia.domain.taxonomy import FindingType
from avalia.extract.tsm_builder import build_tsm
from avalia.harness_checks import presence_findings

pytestmark = pytest.mark.fast

# Agente com chamada de modelo, SEM nenhum dos mecanismos do Tier 2 → py_model/py_graph satisfeitos.
_BARE_AGENT = """
def planner_agent(state):
    return client.create(model="gpt-4o", messages=state)
"""


def _types(tsm, dim: Dimension) -> set[FindingType]:
    findings, _ = presence_findings(tsm, dim)
    return {f.finding_type for f in findings}


def test_bare_agent_flags_all_four_mechanisms():
    tsm = build_tsm({"agent.py": _BARE_AGENT})
    got = (
        _types(tsm, Dimension.ROBUSTEZ)
        | _types(tsm, Dimension.CUSTO)
        | _types(tsm, Dimension.PERFORMANCE)
    )
    assert {
        FindingType.SEM_SAIDA_ESTRUTURADA,
        FindingType.SEM_CHECKPOINT_ESTADO,
        FindingType.SEM_PROMPT_CACHE,
        FindingType.SEM_OBSERVABILIDADE,
    } <= got


def test_structured_output_present_is_not_flagged():
    src = "def planner_agent(s):\n    return client.with_structured_output(Schema).invoke(s)\n"
    tsm = build_tsm({"agent.py": src})
    assert FindingType.SEM_SAIDA_ESTRUTURADA not in _types(tsm, Dimension.ROBUSTEZ)


def test_prompt_cache_present_is_not_flagged():
    src = 'def planner_agent(s):\n    return client.create(model="gpt-4o", cache_control={})\n'
    tsm = build_tsm({"agent.py": src})
    assert FindingType.SEM_PROMPT_CACHE not in _types(tsm, Dimension.CUSTO)


def test_checkpoint_present_is_not_flagged():
    src = "def planner_agent(s):\n    return s\n\n\nsaver = MemorySaver()\n"
    tsm = build_tsm({"agent.py": src})
    assert FindingType.SEM_CHECKPOINT_ESTADO not in _types(tsm, Dimension.ROBUSTEZ)


_OBSERVED_AGENT = """
import logging

log = logging.getLogger(__name__)


def planner_agent(s):
    return s
"""


def test_observability_present_is_not_flagged():
    tsm = build_tsm({"agent.py": _OBSERVED_AGENT})
    assert FindingType.SEM_OBSERVABILIDADE not in _types(tsm, Dimension.PERFORMANCE)


def test_trivial_target_without_model_or_graph_is_not_flagged():
    # Sem agente/modelo → pré-condição py_model/py_graph falha → nenhum check Tier 2 dispara.
    tsm = build_tsm({"util.py": "def add(a, b):\n    return a + b\n"})
    got = (
        _types(tsm, Dimension.ROBUSTEZ)
        | _types(tsm, Dimension.CUSTO)
        | _types(tsm, Dimension.PERFORMANCE)
    )
    tier2 = {
        FindingType.SEM_SAIDA_ESTRUTURADA,
        FindingType.SEM_CHECKPOINT_ESTADO,
        FindingType.SEM_PROMPT_CACHE,
        FindingType.SEM_OBSERVABILIDADE,
    }
    assert not (tier2 & got)
