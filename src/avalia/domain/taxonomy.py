"""T-003 — Taxonomia controlada de tipos de achado + identidade estável.

Crítica para RF-29 / RNF-01 (resolução #3). Cada `FindingType` é fechado e pertence a UMA
dimensão dona (FINDING_TYPE_DIMENSION). A identidade de um achado é a chave composta
(dimensão, FindingType, localização_normalizada), onde a localização é símbolo/nó — NUNCA
linha. `finding_identity` produz um hash ESTÁVEL entre execuções (hashlib, não o hash()
salgado do Python) → robusto a reformulação textual e a código que muda de lugar.

Rastreabilidade: RF-29, RNF-01; resolução #3; regra inviolável 4.
"""

from __future__ import annotations

import hashlib
import re
from enum import StrEnum

from avalia.domain.enums import Dimension


class FindingType(StrEnum):
    """Tipos de achado fechados por dimensão. Os juízes-LLM devem emitir um destes."""

    # --- Custo (RF-DIM-C*) ---
    MIX_MODELO_INADEQUADO = "mix_modelo_inadequado"
    SEM_LIMITE_TOKENS = "sem_limite_tokens"
    SEM_TETO_CUSTO = "sem_teto_custo"
    CHAMADAS_REDUNDANTES = "chamadas_redundantes"
    SEM_CACHE = "sem_cache"
    # --- Performance (RF-DIM-P*) ---
    SERIALIZACAO_DESNECESSARIA = "serializacao_desnecessaria"
    SEM_TIMEOUT = "sem_timeout"
    SEM_STREAMING = "sem_streaming"
    # --- Qualidade (RF-DIM-Q*) ---
    SEM_HARNESS_VERIFICACAO = "sem_harness_verificacao"
    RUBRICA_AUSENTE_OU_VAGA = "rubrica_ausente_ou_vaga"
    PROMPT_AMBIGUO = "prompt_ambiguo"
    # --- Assertividade (RF-DIM-A*) ---
    SEM_EXPRESSAO_CONFIANCA = "sem_expressao_confianca"
    SEM_ESCALONAMENTO_BAIXA_CONFIANCA = "sem_escalonamento_baixa_confianca"
    # --- Alucinação (RF-DIM-H*) ---
    PROMPT_SEM_CITACAO = "prompt_sem_citacao"
    SEM_GROUNDING = "sem_grounding"
    SEM_ABSTENCAO = "sem_abstencao"
    SEM_VERIFICACAO_FATUAL = "sem_verificacao_fatual"
    # --- Trajetória (RF-DIM-T*) ---
    LOOP_SEM_TETO = "loop_sem_teto"
    CAMINHO_MORTO = "caminho_morto"
    PASSOS_REDUNDANTES = "passos_redundantes"
    FERRAMENTA_SEM_DESCRICAO = "ferramenta_sem_descricao"
    ROTEAMENTO_INCOERENTE = "roteamento_incoerente"
    # --- Robustez (RF-DIM-R*) ---
    SEM_RETRY = "sem_retry"
    SEM_FALLBACK_MODELO = "sem_fallback_modelo"
    SEM_TRATAMENTO_ERRO = "sem_tratamento_erro"
    SEM_VALIDACAO_ENTRADA = "sem_validacao_entrada"
    GUARDRAIL_INJECAO_AUSENTE = "guardrail_injecao_ausente"
    # --- Contradições config↔código (CB-08, T-106) — atribuídas à dimensão afetada ---
    CONTRADICAO_MODELO_CONFIG = "contradicao_modelo_config"  # modelo declarado ≠ usado (Custo)
    CONTRADICAO_FLUXO_PROMPT = "contradicao_fluxo_prompt"  # prompt assume fluxo inexistente (Traj.)


# Cada FindingType pertence a UMA dimensão dona (RF-29). Mapa exaustivo — validado abaixo.
FINDING_TYPE_DIMENSION: dict[FindingType, Dimension] = {
    FindingType.MIX_MODELO_INADEQUADO: Dimension.CUSTO,
    FindingType.SEM_LIMITE_TOKENS: Dimension.CUSTO,
    FindingType.SEM_TETO_CUSTO: Dimension.CUSTO,
    FindingType.CHAMADAS_REDUNDANTES: Dimension.CUSTO,
    FindingType.SEM_CACHE: Dimension.CUSTO,
    FindingType.SERIALIZACAO_DESNECESSARIA: Dimension.PERFORMANCE,
    FindingType.SEM_TIMEOUT: Dimension.PERFORMANCE,
    FindingType.SEM_STREAMING: Dimension.PERFORMANCE,
    FindingType.SEM_HARNESS_VERIFICACAO: Dimension.QUALIDADE,
    FindingType.RUBRICA_AUSENTE_OU_VAGA: Dimension.QUALIDADE,
    FindingType.PROMPT_AMBIGUO: Dimension.QUALIDADE,
    FindingType.SEM_EXPRESSAO_CONFIANCA: Dimension.ASSERTIVIDADE,
    FindingType.SEM_ESCALONAMENTO_BAIXA_CONFIANCA: Dimension.ASSERTIVIDADE,
    FindingType.PROMPT_SEM_CITACAO: Dimension.ALUCINACAO,
    FindingType.SEM_GROUNDING: Dimension.ALUCINACAO,
    FindingType.SEM_ABSTENCAO: Dimension.ALUCINACAO,
    FindingType.SEM_VERIFICACAO_FATUAL: Dimension.ALUCINACAO,
    FindingType.LOOP_SEM_TETO: Dimension.TRAJETORIA,
    FindingType.CAMINHO_MORTO: Dimension.TRAJETORIA,
    FindingType.PASSOS_REDUNDANTES: Dimension.TRAJETORIA,
    FindingType.FERRAMENTA_SEM_DESCRICAO: Dimension.TRAJETORIA,
    FindingType.ROTEAMENTO_INCOERENTE: Dimension.TRAJETORIA,
    FindingType.SEM_RETRY: Dimension.ROBUSTEZ,
    FindingType.SEM_FALLBACK_MODELO: Dimension.ROBUSTEZ,
    FindingType.SEM_TRATAMENTO_ERRO: Dimension.ROBUSTEZ,
    FindingType.SEM_VALIDACAO_ENTRADA: Dimension.ROBUSTEZ,
    FindingType.GUARDRAIL_INJECAO_AUSENTE: Dimension.ROBUSTEZ,
    # Contradições (CB-08, T-106): cada uma na dimensão afetada (regra 4).
    FindingType.CONTRADICAO_MODELO_CONFIG: Dimension.CUSTO,
    FindingType.CONTRADICAO_FLUXO_PROMPT: Dimension.TRAJETORIA,
}

# Garantia em tempo de import: nenhum FindingType órfão (toda a taxonomia tem dona).
_missing = set(FindingType) - set(FINDING_TYPE_DIMENSION)
if _missing:  # pragma: no cover - guarda de desenvolvimento
    raise RuntimeError(f"FindingType sem dimensão dona: {sorted(t.value for t in _missing)}")


def dimension_of(finding_type: FindingType) -> Dimension:
    """Dimensão dona de um tipo de achado (RF-29)."""
    return FINDING_TYPE_DIMENSION[finding_type]


_WS = re.compile(r"\s+")


def normalize_location(file_path: str, symbol: str) -> str:
    """Localização normalizada para identidade — símbolo/nó, NUNCA linha (resolução #3).

    Normaliza separadores de caminho e espaços para que a chave seja estável entre SOs e
    a reformatações irrelevantes. A linha de propósito não entra.
    """
    path = _WS.sub("", file_path.replace("\\", "/").strip())
    sym = _WS.sub(" ", symbol.strip())
    return f"{path}::{sym}"


def finding_identity(dimension: Dimension, finding_type: FindingType, location: str) -> str:
    """Hash ESTÁVEL da chave composta (dimensão, FindingType, localização_normalizada).

    Usa SHA-256 (determinístico entre processos) em vez de hash() (salgado por execução),
    garantindo que o mesmo achado case entre versões mesmo com reformulação textual.
    """
    payload = f"{dimension.value}|{finding_type.value}|{location}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
