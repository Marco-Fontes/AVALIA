"""Papel do modelo numa chamada de juízo (RNF-12). Módulo próprio para evitar import circular
entre `gateway` e `structured`; `avalia.model_gateway.gateway` reexporta `ModelRole`."""

from __future__ import annotations

from enum import StrEnum


class ModelRole(StrEnum):
    """Papel do modelo numa chamada (RNF-12)."""

    PRIMARY = "primary"
    FALLBACK = "fallback"
