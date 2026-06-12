"""T-804 — Gancho `TestCaseGenerator` da Fase 2 (O8). VAZIO na Fase 1.

A Fase 2 consumirá o `TargetStaticModel` (já disponível na Fase 1) para gerar autonomamente
casos de teste — evitando retrabalho. Aqui só o contrato é declarado; não há implementação e
nenhum caminho da Fase 1 o invoca. NÃO executa o alvo (RNF-05/S-04).
"""

from __future__ import annotations

from typing import Any, ClassVar, Protocol, runtime_checkable

from avalia.domain.tsm import TargetStaticModel


@runtime_checkable
class TestCaseGenerator(Protocol):
    """Gerador de casos de teste a partir do TSM (Fase 2). Sem implementação na Fase 1."""

    __test__: ClassVar[bool] = False  # não é uma classe de teste pytest (nome começa com "Test")

    def generate(self, tsm: TargetStaticModel) -> list[Any]:
        """Geraria casos de teste a partir dos fatos estáticos — apenas Fase 2."""
        ...
