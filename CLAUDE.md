# AVALIA — Regras de Projeto (Claude Code)

**AVALIA é o AVALIADOR.** O sistema multiagente avaliado é o **alvo** — apenas entrada.
**Fase 1 = análise estática. NUNCA executa o alvo** (RNF-05/S-04), nem em teste.

## Fontes da verdade (imutáveis nesta fase)
`spec.md` v0.4 · `plan.md` v1.3 · `tasks.md` v1.3. Decisões EC-01..EC-10 são fixas.
Mudança que conflite com elas ou que implemente Fase 2 (S-05) → **PARE e confirme com o humano**.

## Stack
Python 3.12 · LangGraph (StateGraph) · Pydantic v2 · Postgres (checkpointer + repositório de laudos) ·
LangChain `with_structured_output` (sem PydanticAI) · tree-sitter/`ast` (extrator Python).
Acesso a modelo **só via `ModelGateway`** (default Opus→Sonnet, configurável; back-ends Anthropic/OpenRouter).

## 7 regras invioláveis (cada uma tem enforcement — ver §6 do guia de config)
1. Nenhum caminho executa/importa/`exec`/`eval` o código do alvo (RNF-05) → hook `guard_no_target_exec` + teste-guarda.
2. Modelo nunca é constante no código; vem de config (RNF-06) → guard de modelo (Fase B).
3. Todo acesso a LLM passa pelo `ModelGateway` (RNF-12) → guard de gateway (Fase B).
4. Todo `Finding` usa `FindingType` da taxonomia fechada; identidade = (dimensão, FindingType, símbolo/nó, **nunca linha**) (RF-29).
5. Juiz-LLM: `temperature=0`, rubrica versionada, conteúdo do alvo **delimitado como dado não confiável** (RNF-01, R8).
6. Determinístico vs. juiz: fato do TSM nunca é "julgado"; opinião nunca é tratada como determinística (plan §3.2).
7. Dimensão comportamental sempre declara `static_limitations` (RF-13/RNF-04).

## DoD global (toda tarefa)
(a) contrato Pydantic v2 validado; (b) teste da tarefa passa (mock do `ModelGateway`, nunca modelo real, nunca executa o alvo);
(c) rastreabilidade ao requisito (RF/RNF/CA/CB) citada no código/teste; (d) `ruff` + guarda RNF-05 verdes.

## Convenções de arquitetura
- **TSM (Target Static Model)** é a fonte única de fatos; avaliadores leem o mesmo objeto imutável.
- Evidência = arquivo + **símbolo/nó** (linha é evidência, não identidade).
- Pesos/limiares/modelos são **dados/config**, nunca constantes (RNF-06).

## Comandos canônicos
- Testes: `py -m pytest -q`  · rápidos: `py -m pytest -q -m fast`
- Lint/format: `py -m ruff check .` · `py -m ruff format .`
- Tipos: `py -m mypy src`
- Guarda RNF-05: `py -m pytest tests/guards -q`

## Ambiente
Windows. Python via launcher `py` (3.12). Repo fora de versionar `.claude/settings.local.json`.
Hooks em Python (cross-platform). Não usar `.sh`.
