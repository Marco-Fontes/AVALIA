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

# T4.3 — classificador robusto a META-vocabulário (corrige `tipo=rag` espúrio do dogfood).
# RAG só é inferido por ESTRUTURA de recuperação (nó/ferramenta/aresta) OU por ≥2 GRUPOS de
# vocabulário em prompts — nunca por 1 palavra-chave isolada. Termos genéricos como "index"
# (que casa `index_artifact`) são deliberadamente EXCLUÍDOS dos sinais estruturais (RF-06; MS-09).
_RAG_STRUCT = (
    "retriev",
    "vector",
    "embedding",
    "vectorstore",
    "vectordb",
    "faiss",
    "chroma",
    "pinecone",
    "weaviate",
    "qdrant",
    "knn",
)
# Grupos de vocabulário (sinônimos contam como 1 grupo, para não inflar a contagem).
_RAG_VOCAB_GROUPS: tuple[tuple[str, ...], ...] = (
    ("context", "contexto"),
    ("fonte", "source"),
    ("document",),
    ("cita",),  # citação/citacao/cite
    ("grounding", "fundament"),
    ("recuper", "retriev"),
    ("rag",),
)


def _structural_blob(tsm: TargetStaticModel) -> str:
    """Nomes/símbolos estruturais (não prosa): ferramentas, agentes e arestas."""
    parts = [t.name for t in tsm.tools]
    parts += [a.name for a in tsm.agents]
    parts += [f"{e.source} {e.target}" for e in tsm.edges]
    return " ".join(parts).lower()


def _rag_vocab_groups(tsm: TargetStaticModel) -> int:
    blob = " ".join(p.text.lower() for p in tsm.prompts)
    return sum(1 for group in _RAG_VOCAB_GROUPS if any(term in blob for term in group))


def _infer_type(tsm: TargetStaticModel) -> str | None:
    """Tipo funcional do alvo (RF-06). Inferência fraca (vocabulário-só, 1 sinal) → None, para
    `select_weights` cair no perfil neutro (RF-16) em vez de aplicar pesos de RAG indevidos."""
    if tsm.tools:
        return "agente_de_acao"
    has_retrieval_structure = any(h in _structural_blob(tsm) for h in _RAG_STRUCT)
    if has_retrieval_structure or _rag_vocab_groups(tsm) >= 2:
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
