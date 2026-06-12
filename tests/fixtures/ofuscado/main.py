# Fixture (TEXTO INERTE — nunca executada, RNF-05): um arquivo legível normal.
# O arquivo ofuscado vizinho (obf.py) exercita a detecção de legibilidade (T-104/CB-02).
from typing import TypedDict


class State(TypedDict):
    q: str


SYSTEM_PROMPT = "Responda com base no contexto, citando as fontes."


def answerer(state):
    return state
