"""T-101 — Interface plugável `LanguageExtractor` + fragmentos de extração.

Porta entre o(s) extrator(es) e o construtor do TSM (T-103). Cada extrator recebe arquivos
(texto) e devolve `ExtractionResult` com fragmentos do TSM, cada fato com `EvidenceRef`.
Linguagem sem extrator → best-effort/baixa confiança, sem quebrar (registry).

Rastreabilidade: plan §3.1; resolução #1.
"""

from __future__ import annotations

from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field

from avalia.domain.tsm import (
    AgentNode,
    ConfigItem,
    Edge,
    ErrorHandling,
    LoopInfo,
    ModelAssignment,
    PromptRef,
    SharedStateRef,
    ToolDef,
)


class ExtractionResult(BaseModel):
    """Fragmentos do TSM produzidos por um extrator para um conjunto de arquivos."""

    model_config = ConfigDict(frozen=True)

    files: list[str] = Field(default_factory=list)
    agents: list[AgentNode] = Field(default_factory=list)
    prompts: list[PromptRef] = Field(default_factory=list)
    tools: list[ToolDef] = Field(default_factory=list)
    edges: list[Edge] = Field(default_factory=list)
    loops: list[LoopInfo] = Field(default_factory=list)
    model_assignments: list[ModelAssignment] = Field(default_factory=list)
    configs: list[ConfigItem] = Field(default_factory=list)
    error_handling: list[ErrorHandling] = Field(default_factory=list)
    shared_state: list[SharedStateRef] = Field(default_factory=list)
    unreadable_files: list[str] = Field(default_factory=list)


class LanguageExtractor(Protocol):
    """Extrator estático por linguagem. NÃO executa o alvo — só lê o texto-fonte."""

    language: str

    def extract(self, files: dict[str, str]) -> ExtractionResult:
        """Recebe caminho→texto-fonte; devolve fragmentos do TSM (com EvidenceRef)."""
        ...
