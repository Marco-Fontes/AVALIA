"""ModelGateway — única porta de acesso a LLM do AVALIA (RNF-12, #2b).

Todo acesso a modelo de JULGAMENTO passa por aqui (regra inviolável 3). O gateway só fala
com modelos do próprio AVALIA — NUNCA executa, importa ou instancia o ALVO (RNF-05).
"""

from __future__ import annotations

from avalia.model_gateway.gateway import (
    ModelGateway,
    ModelRole,
    StructuredOutputUnsupported,
)

__all__ = ["ModelGateway", "ModelRole", "StructuredOutputUnsupported"]
