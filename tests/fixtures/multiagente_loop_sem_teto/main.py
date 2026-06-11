"""Alvo sintético MULTIAGENTE com loop sem teto (DADO estático — NUNCA executado, RNF-05).

Cenário: 2 papéis com prompts distintos + orquestração + estado compartilhado (→ multiagente)
e um `while True` sem break no nó solver (→ LOOP_SEM_TETO, faixa 50–74; suporta CA-09).
"""

from typing import TypedDict


class PipelineState(TypedDict):
    question: str
    answer: str


PLANNER_SYSTEM_PROMPT = "Você é o planejador. Decomponha a tarefa do usuário em passos claros."
SOLVER_SYSTEM_PROMPT = "Você é o executor. Resolva cada passo usando as ferramentas disponíveis."


def planner_agent(state):
    return state


def solver_agent(state):
    iterations = 0
    while True:  # loop sem teto: sem break e sem limite de iterações
        iterations += 1
        state = step(state)


def step(state):
    return state


def build_graph(graph):
    graph.add_node("planner", planner_agent)
    graph.add_node("solver", solver_agent)
    graph.add_edge("planner", "solver")
    graph.add_edge("solver", "planner")
    return graph
