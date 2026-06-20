"""M11 — serializador do checkpointer endurecido para produção (HITL durável).

O estado do grafo (`AvaliaState`) contém modelos Pydantic e enums de `avalia.*`. O serde padrão
do LangGraph (`JsonPlusSerializer`) os roundtrip, mas avisa que tipos "não registrados" serão
**bloqueados em versões futuras** / sob `LANGGRAPH_STRICT_MSGPACK=true` (atrito registrado no M3).
Isso ameaça o `interrupt`/`resume` do `human_gate` (RF-24), sobretudo com o `PostgresSaver` de
produção, que serializa o estado de verdade.

Solução: registrar explicitamente TODOS os tipos de `avalia.*` que podem aparecer num checkpoint
na allowlist do serde — coletados por introspecção dos módulos de domínio/config/estado (robusto a
novos tipos: basta o módulo estar na lista). NÃO afrouxa a segurança (não usa `allow-all`): só os
tipos do PRÓPRIO avaliador são permitidos; o conteúdo do alvo nunca é desserializado aqui (RNF-05).

Rastreabilidade: RF-24; plan §3.8a; atrito do M3.
"""

from __future__ import annotations

import inspect
from enum import Enum
from functools import lru_cache
from types import ModuleType

from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
from pydantic import BaseModel

from avalia.config import evaluator_config
from avalia.domain import contracts, enums, evidence, submission, taxonomy, tsm, weights
from avalia.graph import state as graph_state

# Módulos cujos modelos/enums podem entrar no estado do grafo (e logo num checkpoint). Importados
# diretamente (sem importlib — que o guard RNF-05 proíbe em src/, por ser via de carregar o alvo).
_AVALIA_TYPE_MODULES: tuple[ModuleType, ...] = (
    enums,
    evidence,
    taxonomy,
    contracts,
    tsm,
    submission,
    weights,
    evaluator_config,
    graph_state,
)


@lru_cache(maxsize=1)
def avalia_checkpoint_types() -> tuple[type, ...]:
    """Todos os tipos `avalia.*` (Pydantic/Enum) que podem ser serializados num checkpoint."""
    out: list[type] = []
    for module in _AVALIA_TYPE_MODULES:
        for _, obj in inspect.getmembers(module, inspect.isclass):
            if obj.__module__ == module.__name__ and issubclass(obj, BaseModel | Enum):
                out.append(obj)
    return tuple(out)


@lru_cache(maxsize=1)
def avalia_checkpoint_serde() -> JsonPlusSerializer:
    """Serde do checkpointer com os tipos `avalia.*` registrados — seguro sob modo estrito e
    com `PostgresSaver` (HITL durável). Use-o em QUALQUER checkpointer de produção."""
    return JsonPlusSerializer(allowed_msgpack_modules=list(avalia_checkpoint_types()))
