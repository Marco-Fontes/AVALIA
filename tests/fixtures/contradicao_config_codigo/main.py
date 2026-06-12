# Fixture (TEXTO INERTE — nunca executada, RNF-05) com DUAS contradições internas (CB-08):
#  (1) a config declara MODEL_NAME="claude-opus", mas o código chama model="gpt-4o";
#  (2) o prompt encaminha para "verificador", que não existe como nó/aresta/agente.
from typing import TypedDict


class GraphState(TypedDict):
    q: str


MODEL_NAME = "claude-opus"  # modelo DECLARADO na config

ROUTER_PROMPT = "Após responder, encaminhe para verificador para a checagem final."


def planner(state):
    return state


def answerer(state):
    # contradição (1): usa um modelo DIFERENTE do declarado em MODEL_NAME
    return chat(model="gpt-4o", messages=[])  # noqa: F821 — alvo inerte, não executado


def build(g):
    g.add_edge("planner", "answerer")
