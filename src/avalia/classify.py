"""N2 `classify_target` (T-203) — topologia + tipo + confiança própria.

Topologia por ≥2 sinais (RF-04): (a) prompts/papéis distintos, (b) orquestração explícita
(arestas), (c) estado compartilhado. <2 sinais → agente_unico_borderline, **sem recusa**
(CA-02). Tipo funcional inferido por heurística; baixa confiança → fallback neutro a jusante
(RF-06/RF-16). A classificação deriva do TSM, não de autodeclaração (RF-08/RNF-09).

Rastreabilidade: RF-04, RF-05, RF-06, RF-07, RF-08; CA-02.
"""

from __future__ import annotations

from avalia.domain.contracts import TargetClassification
from avalia.domain.enums import Confidence, Topology
from avalia.domain.tsm import TargetStaticModel

_RAG_HINTS = ("context", "contexto", "fonte", "document", "retriev", "rag", "citação", "citacao")


def _infer_type(tsm: TargetStaticModel) -> str | None:
    if tsm.tools:
        return "agente_de_acao"
    blob = " ".join(p.text.lower() for p in tsm.prompts)
    if any(h in blob for h in _RAG_HINTS):
        return "rag"
    return None


def classify_target(tsm: TargetStaticModel) -> TargetClassification:
    signals: list[str] = []
    if len({p.text for p in tsm.prompts}) >= 2:
        signals.append("papeis_prompts_distintos")
    if tsm.edges:
        signals.append("orquestracao_explicita")
    if tsm.shared_state:
        signals.append("estado_compartilhado")

    if len(signals) >= 2:
        topology = Topology.MULTIAGENTE
        conf = Confidence.ALTO if len(signals) == 3 else Confidence.MEDIO
        caveats: list[str] = []
    else:
        topology = Topology.AGENTE_UNICO_BORDERLINE
        conf = Confidence.MEDIO
        caveats = [
            "Classificado como agente único / borderline: aspectos que dependem de "
            "interação entre agentes podem ser marcados não aplicáveis (RF-07/RF-21)."
        ]

    return TargetClassification(
        topology=topology,
        topology_signals=signals,
        system_type=_infer_type(tsm),
        classification_conf=conf,
        caveats=caveats,
    )
