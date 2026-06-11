"""Alvo sintético de AGENTE ÚNICO / borderline (DADO estático — NUNCA executado, RNF-05).

Cenário: um único prompt, sem orquestração entre agentes e sem estado compartilhado
(→ < 2 sinais → agente_unico_borderline; suporta CA-02).
"""

SYSTEM_PROMPT = "Você é um assistente. Responda diretamente à pergunta do usuário."


def run(question: str) -> str:
    return SYSTEM_PROMPT
