# AVALIA — Registro de Execução (Fase 4 / Implementação)

**Atualizado:** 2026-06-18 · **Iteração atual:** M11 — endurecimento de produção (serde durável + docs, ver §7).
**Fontes da verdade (imutáveis):** [spec.md](spec.md) v0.4 · [plan.md](plan.md) v1.3 · [tasks.md](tasks.md) v1.3.

Este documento é o **log rastreável** do que já foi executado. Não altera as fontes da verdade —
apenas registra implementação, cobertura de requisitos e artefatos. Decisões de escopo
(EC-01..EC-10, resoluções #1..#5) permanecem intactas.

| Marco | Estado |
|---|---|
| **Fase A** — config Claude Code (guardrails) | ✅ concluído |
| **M0** — contratos + config (T-001..T-007) | ✅ concluído |
| **M1** — walking skeleton (laudo ponta-a-ponta) | ✅ concluído |
| **M2** — sete dimensões + agregação completa | ✅ concluído |
| **M3** — divergência + HITL (E4) | ✅ concluído |
| **M4** — histórico + comparação (E6) | ✅ concluído |
| **M5** — robustez de escala + streaming + ganchos Fase 2 | ✅ concluído |
| **M6** — observabilidade + meta-avaliação (E9) | ✅ concluído |
| **M7** — suíte de aceite fechada (E10 completo) | ✅ concluído |

**Fase 1 (avaliação estática) implementada de ponta a ponta** (M0–M7). Todos os CA-01..15 e
CB-01..10 têm teste de aceite explícito (black-box), além das guardas contínuas (RNF-05) e do CI.

**Porta de entrada de uso (MVP, fora do conjunto T-xxx — empacotamento, não muda escopo/Spec):**
`avalia <caminho-do-alvo>` (ou `python -m avalia ...`) varre o repositório do alvo (`loader.py`, só
leitura de texto — pula `.git`/caches/`node_modules`/binários/grandes), roda o grafo e grava
`laudo.md`/`laudo.json` + resumo no stdout. Determinístico por padrão; `--llm` liga o `ModelGateway`.
Ver [README.md](README.md). Arquivos: `src/avalia/{loader,cli,__main__}.py`, `[project.scripts]`;
testes `tests/cli/`. Nada executa o alvo (RNF-05) — a guarda contínua cobre os novos módulos.

Validação atual: `ruff check .` limpo · `ruff format --check .` limpo · `mypy src` limpo (69
arquivos) · **191 testes verdes** (`py -m pytest -q`; +4 Postgres gated por `AVALIA_PG_DSN`). Gate
leve `-m fast`: 169 verdes, smoke de meta-avaliação **deselecionado** (fora do CI crítico).
Suíte de aceite M7 (`tests/acceptance/`): 26 casos (CA/CB) + reprodutibilidade em dois regimes
(determinístico bit-idêntico e juiz estável por faixa, ancorado em fato).

---

## 1. Fase A — Configuração do Claude Code (guardrails ativos antes de `src/`)

Enforcement das 7 regras invioláveis por hooks (grátis, mecânico). Ver `.claude/settings.json`.

| ID | Hook | Evento | Função | Invariante | Teste |
|---|---|---|---|---|---|
| CC-H01 | `guard_no_target_exec.py` | PreToolUse Edit/Write | bloqueia exec/eval/import/runpy do alvo em `src/` | RNF-05/S-04 | `tests/guards/test_hooks.py` |
| CC-H07 | `guard_model_access.py` | PreToolUse Edit/Write | bloqueia slug de modelo / cliente LLM fora do gateway | RNF-06/RNF-12 | `tests/guards/test_hooks.py` |
| CC-H02 | `protect_secrets.py` *(novo)* | PreToolUse Edit/Write | bloqueia escrita de segredo / em `.env`,`*.pem`,`secrets/` | higiene de segredo | `tests/guards/test_protect_and_sql.py` |
| CC-H06 | `block_sql_destructive.py` *(novo)* | PreToolUse Bash/PowerShell | nega DROP/TRUNCATE/DELETE-sem-WHERE/`downgrade base` | protege T-601 | `tests/guards/test_protect_and_sql.py` |
| CC-H03 | `format.py` | PostToolUse | `ruff format` + `--fix` no arquivo editado | — | — |
| CC-H05 | `quality_gate.py` *(novo)* | Stop | gate leve: `ruff check` + `pytest -m fast` (anti-loop) | — | (auto no Stop) |
| CC-T01 | `test_no_target_exec.py` | pytest | varre `src/**` por execução do alvo (regressão RNF-05) | RNF-05/T-1006 | **ativo** (src/ não-vazio) |

> Os hooks CC-H02/H05/H06 foram pedidos no PASSO 0 desta iteração. Implementam a postura de
> segurança da Fase A; não são tarefas de produto (T-xxx) nem alteram as fontes da verdade.

---

## 2. M0 — Tarefas executadas (T-001..T-007)

DoD global de cada tarefa: (a) contrato Pydantic v2 validado; (b) teste da tarefa passa
(mock do gateway, sem modelo real, sem executar o alvo); (c) rastreabilidade citada no
código/teste; (d) `ruff` + guarda RNF-05 verdes.

| Tarefa | Dep | Entrega | Arquivos | Requisitos | Testes | DoD |
|---|---|---|---|---|---|---|
| **T-001** | — | esqueleto src-layout, deps (stack fechada), alvos format/lint/test, guardrails Fase A | `pyproject.toml`, `conftest.py`, `src/avalia/__init__.py`, `tests/fixtures/README.md` | infra (plan §2); LangSmith opcional | suíte coleta+roda | ✅ |
| **T-002** | T-001 | enums atômicos + `EvidenceRef` (exige símbolo) | `domain/enums.py`, `domain/evidence.py` | RF-14, RNF-07, RNF-03 | `tests/domain/test_enums_evidence.py` (6) | ✅ |
| **T-003** | T-002 | taxonomia `FindingType` fechada + `normalize_location` + `finding_identity` (hash estável) | `domain/taxonomy.py` | RF-29, RNF-01; resolução #3 | `tests/domain/test_taxonomy.py` (6) | ✅ |
| **T-004** | T-002, T-003 | contratos compostos + `EvaluationReport` (blocos 4.2.1–4.2.8) + slot opaco `dynamic_metrics` | `domain/contracts.py`, `domain/weights.py` | RF-09/10/11/14/19/25/27/29, RNF-02/03/07/08/10; S-05 | `tests/domain/test_contracts.py` (11) | ✅ |
| **T-005** | T-002 | `EvaluatorConfig` (pesos, limiares 50/75, piso conf., modelo primário+fallback+back-end+retry por nó); validação CB-07 | `config/evaluator_config.py` | RNF-06, CB-07, RF-18, RF-22, RNF-12; #2/#2b/#4 | `tests/config/test_evaluator_config.py` (7) | ✅ |
| **T-006** | T-002 | `weight_profiles.yaml` (rag/ação/atendimento/pipeline/**neutro**) + loader validado | `config/weight_profiles.yaml`, `config/weight_profiles.py` | RF-16, RNF-06; CA-03, CA-04 | `tests/config/test_weight_profiles.py` (5) | ✅ |
| **T-007** | T-005 | `ModelGateway` `(nó,papel)→ModelRef`; Anthropic/OpenRouter; default Opus→Sonnet (env/config); seam de structured output | `model_gateway/gateway.py`, `model_gateway/__init__.py` | RNF-06, RNF-12; #2/#2b | `tests/model_gateway/test_gateway.py` (6) | ✅ |

**Marco M0 (tasks §13):** ✅ — inclui o slot opaco `dynamic_metrics` (ajuste #4) e o
`ModelGateway` default Opus→Sonnet configurável (ajuste v1.3 / RNF-12).

---

## 2b. M1 — Walking skeleton (T-101..103, 201..204, 301/302, 308, 501, 701/703, 801, 602)

Menor fatia ponta-a-ponta que gera um **laudo real** de um alvo Python simples. Grafo reduzido
(LangGraph): N0→N1→N2→N3→[Trajetória]→N5→N7. Extrator `ast` (escolha desta iteração); juiz com
anti-injeção e fallback intrínsecos; veredito da Trajetória ancorado em fato (loop sem teto).

| Tarefa | Entrega | Arquivos | Requisitos | Testes |
|---|---|---|---|---|
| **T-101** | interface `LanguageExtractor` + registry | `extract/base.py`, `extract/registry.py` | plan §3.1; #1 | `tests/extract/` |
| **T-102** | extrator Python `ast` (leitura estática pura) | `extract/python_extractor.py` | RF-14, RNF-07, **RNF-05** | `tests/extract/` (6) |
| **T-103** | `TargetStaticModel` + builder (fonte única) | `domain/tsm.py`, `extract/tsm_builder.py` | RF-08, RF-12, RF-14 | `tests/extract/` |
| **T-201** | N0 ingest/validate (erro sem laudo) | `ingest.py`, `domain/submission.py` | RF-01/02, CB-07; CA-01 | `tests/nodes/`, `tests/graph/` |
| **T-203** | N2 classify (topologia ≥2 sinais, confiança) | `classify.py` | RF-04..08; CA-02 | `tests/nodes/`, `tests/graph/` |
| **T-204** | N3 select_weights + renormalização | `weights_select.py` | RF-16/17/21; CA-04/08 | `tests/nodes/` (7) |
| **T-301** | framework de check determinístico + hash | `evaluators/checks.py` | RNF-01, RF-26; CA-14 | `tests/evaluators/` |
| **T-302** | framework de juiz (anti-injeção + RNF-12) | `judge/framework.py`, `judge/rubrics.py`, `judge/base.py` | RF-10/20, RNF-01/12; R8 | `tests/judge/` (6) |
| **T-308** | avaliador Trajetória (fato-âncora) | `evaluators/trajetoria.py` | RF-DIM-T*; CA-09 | `tests/evaluators/` (4) |
| **T-501** | agregação + condições de aprovação (CA-09) | `aggregate.py` | RF-15/18/19/22; CA-09 | `tests/report/` (3) |
| **T-701/703** | build_report + render Markdown/JSON | `report/build.py`, `report/render.py` | RF-25/27, RNF-08/10 | `tests/report/` |
| **T-801/602** | grafo LangGraph + checkpointer (MemorySaver) | `graph/state.py`, `graph/nodes.py`, `graph/build_graph.py` | plan §1.1; RF-02; CA-01 | `tests/graph/` (5) |
| **T-310** | teste adversarial de anti-injeção | — | R8; RF-DIM-R3 | `tests/judge/` |
| **T-1008** | teste de resiliência (fallback de modelo) | — | RNF-12; CB-10 | `tests/judge/` |

**Validações de aceite cobertas no M1:** CA-01 (erro sem laudo), CA-02 (borderline), CA-05
(reasoning sempre presente), CA-09 (condição rastreável), RNF-05 (guarda T-1006 ativa sobre
`src/`), R8 (injeção não manipula veredito), RNF-12 (retry→fallback declarado→parcial).

**Fora do M1 (marcos seguintes):** fan-out das 7 dimensões e demais avaliadores (M2);
divergência/HITL (M3); histórico (M4); priorização/budget/streaming/ganchos Fase 2/tree-sitter
(M5); observabilidade (M6). T-308 hoje é determinístico-âncora; o juiz é injetável (demonstrado
no e2e com gateway mockado) e será cabeado em todos os avaliadores no fan-out (M2).

---

## 2c. M2 — Sete dimensões + agregação completa (T-303..307, 309, 311, 502, 503, 702)

Os 6 avaliadores restantes + fan-out paralelo das 7 dimensões com fan-in ordenado; juiz (T-302)
cabeado em todas as dimensões via gateway injetável; agregação completa.

| Tarefa | Entrega | Arquivos | Requisitos | Testes |
|---|---|---|---|---|
| **T-303** | Custo (C2 determinístico: tokens/cache/teto; C1/C3 juiz) | `evaluators/custo.py` | RF-DIM-C1/2/3 | `tests/evaluators/test_dimensions.py` |
| **T-304** | Performance (P2 timeout/streaming; P1 juiz) | `evaluators/performance.py` | RF-DIM-P1/2 | idem |
| **T-305** ⊛ | Qualidade (Q1 harness → CA-06 confiança baixa) | `evaluators/qualidade.py` | RF-DIM-Q1; RF-13; CA-06 | idem |
| **T-306** ⊛ | Assertividade (A2 escalonamento; A1 juiz) | `evaluators/assertividade.py` | RF-DIM-A1/2; RF-13 | idem |
| **T-307** ⊛ | Alucinação (citação; H1 juiz; CA-07) | `evaluators/alucinacao.py` | RF-DIM-H1; RF-13; CA-07 | idem |
| **T-309** | Robustez (retry/fallback/try/validação; anti-injeção juiz) | `evaluators/robustez.py` | RF-DIM-R1/2/3 | idem |
| **T-311** | Fan-out/fan-in das 7 dimensões + ordenação estável | `graph/build_graph.py`, `graph/nodes.py`, `aggregate.py`, `report/build.py` | plan §3.4/§5; RNF-01 | `tests/report/test_m2_aggregation.py`, `tests/graph/test_e2e.py` |
| **T-502** | exclusão por piso de confiança (multi-dimensão) | `aggregate.py` | RF-22 | `tests/report/test_m2_aggregation.py` |
| **T-503** | condições de aprovação de todas as dimensões, priorizadas | `aggregate.py` | RF-19; CA-09 | idem |
| **T-702** | recomendações consolidadas/priorizadas (7 dims) | `report/build.py` | RF-27 | `tests/graph/test_e2e.py` |

⊛ = comportamental (`static_limitations` obrigatório, RF-13). Suporte determinístico novo no
extrator: `token_limit`, `input_validation`, `fallback_modelo`, `has_harness`.

**Aceite coberto no M2:** CA-03 (perfil RAG pesa alucinação > neutro), CA-06 (sem harness →
confiança baixa), CA-07 (Alucinação declara limite Fase 1), CA-08 (Trajetória inaplicável em
agente único → renormalização), CA-09 (condição rastreável), T-311 (agregação independe da ordem).

**Decisões do M2:** juiz **opcional por injeção** (gateway mockado nos testes; default
determinístico); applicability decidida **no avaliador** (retorna `applicable=False`, agregação
exclui+renormaliza); achados respeitam a **dimensão dona** (ex.: `SEM_FALLBACK_MODELO` é da
Robustez — o Custo só o pondera no juiz, regra 4); score **ancorado nos achados determinísticos**,
juiz acrescenta opinião/achados sem inventar score.

---

## 2d. M3 — Divergência + HITL (E4: T-401..T-405)

Detecta divergência entre os julgamentos de uma dimensão, reconcilia automaticamente e só então
escala para um humano, sempre registrando no laudo (4.2.7).

| Tarefa | Entrega | Arquivos | Requisitos | Testes |
|---|---|---|---|---|
| **T-401** | `detect_candidates` (faixas distintas OU confiança < piso) | `divergence.py` | RF-20; resolução #4 | `tests/divergence/test_divergence.py` |
| **T-402** | reconciliação automática (re-julgamento estrito) | `divergence.py`, `judge/contributors.py` | RF-20; CA-10 | idem |
| **T-403** | `ApprovalProvider` + CLI + Static | `hitl/approval.py` | RF-24, RNF-11; resolução #5 | `tests/hitl/test_approval.py` |
| **T-404** | `human_gate` (interrupt/resume) + runner | `graph/nodes.py`, `hitl/runner.py` | RF-24; CA-11 | `tests/graph/test_m3_hitl.py` |
| **T-405** | registro de divergências no laudo + render | `report/build.py`, `report/render.py` | RNF-10; 4.2.7 | `tests/graph/test_m3_hitl.py` |

Contratos novos: `DivergenceCandidate` (pré-resolução), `HumanDecision`. Estado: `pending_divergences`,
`divergences`, `human_decisions`. Grafo: fan-in em `detect_divergence` → condicional → `human_gate`/`aggregate`.

**Aceite coberto:** CA-10 (reconciliada sem humano), CA-11 (persistente → `human_gate`, retoma com
decisão, `resolved_by=humano`). CA-12 permanece como teste negativo da Fase 1 (T-1006, já ativo).

**Decisões do M3:** resolução (auto/humana) é **registrada** e a divergência **escalada ao humano
reduz a confiança** da dimensão no laudo (via `model_copy`, sem mutar o canal append-only); o
**score permanece ancorado em fato** (regra 6). Divergência só existe quando o juiz roda (gateway
presente); o run determinístico passa por `detect_divergence` como no-op.

**Atrito registrado:** o interrupt/resume serializa o estado (modelos Pydantic) pelo checkpointer
do LangGraph, que avisa que versões futuras bloquearão tipos não-registrados (chip de tarefa criado
para registrar `avalia.domain.*` no serde — vale também para o `PostgresSaver` de produção).

---

## 2e. M4 — Histórico + comparação (E6: T-601, T-603, T-604, T-605)

Persiste cada laudo, recupera a versão anterior do mesmo alvo e calcula a comparação histórica.

| Tarefa | Entrega | Arquivos | Requisitos | Testes |
|---|---|---|---|---|
| **T-601** | schema Postgres + CRUD (`PostgresReportRepository`) | `persistence/postgres.py` | RF-28, D-02; #3 | `tests/persistence/test_repository.py` (gated) |
| **T-603** | repositório CRUD + Protocol + InMemory | `persistence/repository.py` | RF-28; CB-06 | idem (InMemory sempre) |
| **T-604** | `findings_index` por identidade estável | `persistence/repository.py` | RF-29, RNF-01 | idem |
| **T-605** | N6 `compare_history` (deltas, diff de achados) | `compare.py`, `graph/nodes.py` | RF-28/29; CA-15 | `tests/persistence/test_compare.py`, `tests/graph/test_m4_history.py` |

Estado: + `comparison`. Grafo: `aggregate → compare_history → build_report`. N7 fatorizado em
`make_build_report_node(repository)` que **persiste** o registro. `build_report`/`render` ganham a
seção de comparação. Reusa `finding_identity`/`Finding.identity` (M0) para o diff estável (RF-29).

**Aceite coberto:** CA-15 (regressões/melhorias/achados resolvidos entre v1 e v2), CB-06 (1ª
versão → sem comparação + nota no laudo).

**Decisões do M4:** persistência atrás do Protocol `ReportRepository` (espelha o split dev/prod do
checkpointer). `InMemoryReportRepository` dirige o CI; `PostgresReportRepository` (schema idempotente
`IF NOT EXISTS`, psycopg import preguiçoso) é exercitado por um **teste-contrato parametrizado** que
roda os dois — Postgres só com `AVALIA_PG_DSN` (CI sem banco → skip). Comparação determinística (não
exige juiz): a diferença de achados usa identidade estável; o run sem repositório passa por N6 no-op.

---

## 2f. M5 — Robustez de escala + streaming + ganchos Fase 2 (T-104/105/106, T-802/803/804)

Torna o avaliador robusto a artefatos grandes e a falhas, expõe progresso por streaming e declara
os ganchos (vazios) da Fase 2. Tudo intrínseco a RNF-05 (nada executa o alvo).

| Tarefa | Entrega | Arquivos | Requisitos | Testes |
|---|---|---|---|---|
| **T-104** | legibilidade determinística (compilado/binário/ofuscado) + `impacted_dims` | `extract/readability.py`, `extract/tsm_builder.py`, `report/build.py` | RF-03; CB-02 | `tests/extract/test_readability.py` (5) |
| **T-105** | priorização por sinal + amostragem acima de `max_analyzed_files` + cobertura | `extract/prioritize.py`, `extract/tsm_builder.py`, `config/evaluator_config.py` | RF-12; CB-05, CA-13 | `tests/extract/test_prioritize.py` (3) |
| **T-106** | contradições config↔código como Finding na dimensão dona | `extract/contradictions.py`, `domain/taxonomy.py` (+2 tipos), `evaluators/{custo,trajetoria}.py` | CB-08; RNF-08 | `tests/extract/test_contradictions.py` (4) |
| **T-802** | `BudgetState`+reducer; `over_budget`; curto-circuito → caminho degradado; laudo parcial; CB-10 | `graph/state.py`, `graph/budget.py`, `graph/nodes.py`, `graph/build_graph.py`, `report/build.py`, `report/render.py` | RF-12, RNF-12; CA-13, CB-10 | `tests/graph/test_m5_budget.py` (3) |
| **T-803** | `stream_progress` + `ProgressEvent` (projeção pura de `astream_events`) | `graph/streaming.py` | plan §3.12 | `tests/graph/test_m5_streaming.py` (1) |
| **T-804** | ganchos Fase 2 vazios (`TargetRunner`, `execution_gate`, `TestCaseGenerator`) | `phase2/{__init__,runner,execution_gate,testgen}.py` | S-05, D-01, O7–O9, RF-23 | `tests/phase2/test_phase2_hooks.py` (3) |

Taxonomia estendida (T-106): `CONTRADICAO_MODELO_CONFIG`→Custo, `CONTRADICAO_FLUXO_PROMPT`→Trajetória.
Config nova: `EvaluatorConfig.max_analyzed_files` (teto determinístico de cobertura, RNF-06).
Estado novo: `BudgetState` (tempo/custo/partial) com reducer `merge_budget`; campo `budget` no
`AvaliaState`. Grafo: `select_weights` ganha aresta condicional `route_after_weights` →
**fan-out das 7 dimensões** OU **`budget_degraded`** (determinístico, pula divergência/HITL) → N5.

**Aceite coberto no M5:** CA-13 (laudo parcial honesto por tamanho/teto), CB-02 (código ilegível →
confiança baixa + dims impactadas), CB-08 (contradições config↔código como Findings), CB-10 (fallback
de modelo esgotado → dimensão degradada + parcial, substituição declarada).

**Decisões do M5 (confirmadas com o usuário antes de codar):**
- **tree-sitter deferido** — mantém Python-first (#1); a interface plugável (T-101) absorve TS/JS depois.
- **CB-10 = degradar p/ determinístico + parcial:** sem juiz, a dimensão mantém o score
  determinístico-âncora, confiança forçada a baixo, substituição/limitação declarada e `status=partial`
  — sem novo campo de contrato (compatível com o validador `applicable→score`).
- **T-106 = novos `FindingType` por dimensão afetada** (estende a taxonomia, respeita a regra 4),
  cada contradição com evidência dos dois lados (RNF-07).
- **Budget short-circuit como aresta condicional após `select_weights`:** quando o teto de
  custo/tempo já estourou, o grafo desvia para `budget_degraded` (avalia as 7 dimensões só com os
  checks determinísticos, baratos) em vez de skippar dimensões — o laudo exige ≥1 dimensão (contrato
  M0). A parcialidade do laudo vem de `budget.partial` OU `coverage.sampled`.
- **Confiança parcial/ilegível:** `_apply_readability_confidence` (→ baixo nas dims impactadas) e
  `_apply_partial_confidence` (reduz um nível nas dims aplicáveis), espelhando `_apply_divergence_confidence`.

**Atrito registrado (M5):** o hook `format.py` roda `ruff --fix` no arquivo logo após cada edição;
adicionar um `import` *antes* da linha que o usa fez o autofix removê-lo como F401 (resolvido
reaplicando o import junto do uso). Colisão de basename no pytest (`test_hooks.py` em `guards/` e
`phase2/`, sem `__init__.py`) → renomeado para `test_phase2_hooks.py`.

---

## 2g. M6 — Observabilidade + meta-avaliação (E9: T-901, T-902; smoke T-1007)

Entrega a infraestrutura de medição: tracing não-bloqueante (MS-10) e o harness offline que valida
se o AVALIA julga bem (MS-04/08/09). NÃO fixa limiar de "confiável" (D-04) nem cura dataset (D-03).

| Tarefa | Entrega | Arquivos | Requisitos | Testes |
|---|---|---|---|---|
| **T-901** | tracing dual: `SpanCollector` (callback in-process, latência/tokens) + LangSmith opcional env-gated, no-op se ausente | `obs/{__init__,spans,tracing}.py` | MS-10; plan §3.11 | `tests/obs/test_tracing_spans.py` (4) |
| **T-902** | esquema do dataset (`BenchmarkCase/Dataset`, `band_of_score`, loader YAML) + harness offline (concordância de veredito/dimensão, classificação, calibração) | `metaeval/{__init__,dataset,harness}.py` | MS-04/07/08/09; D-03/D-04 | (via smoke) |
| **T-1007** | smoke do pipeline de medição sobre seed sintético | `tests/metaeval/fixtures/seed.yaml`, `tests/metaeval/test_metaeval_smoke.py` (2) | MS-04/08/09 (smoke) | — |

**Decisões do M6 (confirmadas com o usuário):**
- **Tracing dual:** o `SpanCollector` (subclasse de `BaseCallbackHandler`) registra spans por nó
  (latência sempre; tokens/custo quando há chamada real de modelo) e é aplicado no `invoke` via
  `instrument_config`, **sem alterar `build_avalia_graph`**. A exportação LangSmith é env-gated
  (`AVALIA_TRACING`/`LANGCHAIN_TRACING_V2`) com import guardado → `[]` se ausente. O laudo gera
  mesmo sem observabilidade (não-bloqueante, plan §3.11).
- **Meta-avaliação = job offline** sobre `EvaluationReport`s + dataset; reusa `band_of_score`
  (faixas de produto, spec §4.2.6) para mapear o score de cada dimensão à faixa comparável ao
  rótulo humano. A métrica primária é **concordância de veredito por dimensão** (EC-10/MS-04).
- **Calibração significativa BLOQUEADA por D-03/D-04** — declarada em
  `MetaEvalReport.calibration_blocked_reason`; o código entrega o pipeline, não o número.
- **Smoke fora do gate `-m fast`:** `test_metaeval_smoke.py` não recebe a marca `fast`, então o
  Stop hook (`pytest -m fast`) o ignora; roda em `pytest -q` completo.

**Aceite coberto no M6:** MS-10 (spans aparecem; laudo gera sem LangSmith), MS-04/08/09 (índices
calculados pelo harness sobre o seed — validação mecânica, não calibração).

**CI (resposta à revisão da PR #7):** adicionado `.github/workflows/ci.yml` (GitHub Actions) que
**enforça** nos PRs e em push para `master` os mesmos gates locais (CLAUDE.md §Comandos canônicos):
`ruff check` + `ruff format --check` + `mypy src` + `pytest -q` + guarda RNF-05. Um **serviço
Postgres** define `AVALIA_PG_DSN`, então os testes-contrato do repositório (T-601) deixam de ser
*skipped* e rodam de verdade no CI. Para o gate de formatação ficar verde repo-wide: `tests/fixtures`
foi excluído do ruff (são DADOS de teste intencionalmente não-idiomáticos) e os hooks da Fase A
(`.claude/hooks/*`) foram formatados. Antes só havia enforcement local (Stop hook) — agora há
enforcement mecânico no PR.

---

## 2h. M7 — Suíte de aceite fechada (E10 completo)

Fecha o Épico E10: um teste de aceite **explícito e black-box** por CA-01..15 e CB-01..10,
mais reprodutibilidade (T-1005) em dois regimes. Encerra a implementação da Fase 1.

| Tarefa | Entrega | Arquivos | Requisitos |
|---|---|---|---|
| **T-1004** | matriz de aceite caso→teste (26 testes) sobre o grafo | `tests/acceptance/test_acceptance_matrix.py` | CA-01..15, CB-01..10 |
| **T-1005** | reprodutibilidade: regime A (determinístico bit-idêntico) + regime B (juiz estável por faixa, fato-âncora) | `tests/acceptance/test_reproducibility.py` | RNF-01, RF-26; CA-14 |
| **(RF-01/CB-01)** | inventário completo dos 6 componentes (só código-fonte bloqueia; opcionais ausentes registrados) | `ingest.py` | RF-01, CB-01 |

**Única mudança de comportamento do M7:** `ingest_validate` passou a inventariar os seis
componentes do pacote (código-fonte, prompts, configuração, harness, instrumentação, metadados) por
heurística declarada sobre o TEXTO dos artefatos — mantendo **só o código-fonte como bloqueante**
(decisão de M1). Assim o laudo registra os opcionais ausentes (CB-01), honrando RF-01 por inteiro.
O resto do M7 é teste: a maioria dos CA/CB já passava com o comportamento de M1–M6; a suíte os torna
explícitos e auditáveis num só lugar.

**Aceite coberto no M7:** CA-12 (prova comportamental de não-execução: alvo com `raise` no topo do
módulo → o run conclui, logo o alvo nunca foi executado — RNF-05); CA-14 (dois regimes); CB-04
(divergência reconciliada registrada); e os demais CA/CB consolidados.

**Decisão do M7:** os testes de aceite são **black-box** (constroem o grafo, invocam, asseguram
sobre o `EvaluationReport`/status), distintos dos testes de unidade — uma camada de garantia a mais,
não substituição. Juízes mockados (`ScriptedGateway`/`ExhaustedGateway`) cobrem divergência e
fallback sem modelo real.

---

## 3. Cobertura requisito → artefato no M0 (espelha tasks §14, sem editar o original)

| Requisito | Artefato que satisfaz (M0) |
|---|---|
| RF-14, RNF-07 | `EvidenceRef` (símbolo obrigatório) |
| RF-29, RNF-01 (identidade) | `taxonomy.finding_identity` (SHA-256 de (dim, FindingType, loc normalizada)) |
| RF-09/10/11, RNF-02/03 | `DimensionResult` (reasoning+confidence obrigatórios), `Finding`, `JudgeOpinion` |
| RF-13, RNF-04 | `DimensionResult.static_limitations` exigido nas comportamentais |
| RF-25, RNF-08/10 | `EvaluationReport` (blocos 4.2.1–4.2.8) + `ReportMetadata` |
| RF-18 | `EvaluatorConfig.verdict_for` + `BandThresholds` (50/75) |
| RF-22 | `EvaluatorConfig.confidence_floor`; `AggregateScore.excluded_low_conf` |
| RF-16, RF-21 | `WeightProfile` + `weight_profiles.yaml` (neutro = pesos iguais) |
| RNF-06 | pesos/limiares/modelo só de config; slugs só no gateway (env-overridable) |
| RNF-12 | `NodeModelConfig.primary/fallback/retry`; `ModelGateway` default Opus→Sonnet; `model_substitutions` no laudo |
| S-05 | `dynamic_metrics` opaco (None na Fase 1); demais ganchos Fase 2 não tocados |

**Validados cedo por teste:** CA-03 (RAG pesa alucinação > neutro), CA-04 (fallback neutro),
CA-05 (reasoning não-vazio), CA-07/RF-13 (static_limitations), CB-07 (pesos inválidos → erro).

---

## 4. Taxonomia `FindingType` concreta (T-003) — instanciação da lista aberta da spec

`tasks.md` T-003 dá exemplos com "…". A enumeração fechada implementada (cada tipo com
dimensão dona, validado em tempo de import) é:

- **Custo:** `MIX_MODELO_INADEQUADO`, `SEM_LIMITE_TOKENS`, `SEM_TETO_CUSTO`, `CHAMADAS_REDUNDANTES`, `SEM_CACHE`
- **Performance:** `SERIALIZACAO_DESNECESSARIA`, `SEM_TIMEOUT`, `SEM_STREAMING`
- **Qualidade:** `SEM_HARNESS_VERIFICACAO`, `RUBRICA_AUSENTE_OU_VAGA`, `PROMPT_AMBIGUO`
- **Assertividade:** `SEM_EXPRESSAO_CONFIANCA`, `SEM_ESCALONAMENTO_BAIXA_CONFIANCA`
- **Alucinação:** `PROMPT_SEM_CITACAO`, `SEM_GROUNDING`, `SEM_ABSTENCAO`, `SEM_VERIFICACAO_FATUAL`
- **Trajetória:** `LOOP_SEM_TETO`, `CAMINHO_MORTO`, `PASSOS_REDUNDANTES`, `FERRAMENTA_SEM_DESCRICAO`, `ROTEAMENTO_INCOERENTE`
- **Robustez:** `SEM_RETRY`, `SEM_FALLBACK_MODELO`, `SEM_TRATAMENTO_ERRO`, `SEM_VALIDACAO_ENTRADA`, `GUARDRAIL_INJECAO_AUSENTE`

A taxonomia é extensível em marcos futuros sem quebrar identidade (a chave inclui o código do tipo).

---

## 5. Novos artefatos / decisões de implementação (não alteram as fontes da verdade)

Itens introduzidos nesta iteração que não estavam *literalmente* na spec/plan/tasks, mas as
**implementam** (não mudam decisão de escopo):

- **Layout de pacotes:** `src/avalia/{domain,config,model_gateway}` (src-layout). Razão: separar
  domínio (contratos) de config e do gateway, evitando ciclos de import (config → domínio;
  gateway → config; contratos → config).
- **Idioma de enum:** `enum.StrEnum` (py312) em vez de `(str, Enum)` — exigência do `ruff` UP042.
- **Variáveis de ambiente do gateway (RNF-06):** `AVALIA_DEFAULT_PRIMARY_MODEL`,
  `AVALIA_DEFAULT_FALLBACK_MODEL`, `AVALIA_DEFAULT_BACKEND`, `AVALIA_OPENROUTER_BASE_URL`.
  Defaults Opus→Sonnet vivem só em `model_gateway/gateway.py` (diretório isento do guard).
- **Valores dos perfis de peso** (`weight_profiles.yaml`): instanciação concreta dos perfis;
  cada um soma 1 (tolerância 1e-3), `neutro` = 1/7 por dimensão.
- **Hooks Fase A** CC-H02/H05/H06: ver Seção 1.

Nada acima conflita com EC-01..EC-10 nem com as resoluções #1..#5. Caso uma implementação
futura precise contrariar uma decisão, o protocolo é **PARAR e confirmar** (não foi necessário).

---

## 6. Invariantes ativos e como são garantidos (desde M0)

| # | Invariável | Garantia |
|---|---|---|
| 1 | Não executa o alvo (RNF-05) | hook CC-H01 + teste CC-T01 (ativo) + nenhum import/exec em `src/` |
| 2 | Anti-injeção (alvo = dado não confiável) | entra em M1 (T-302) — gateway já isola o acesso a modelo |
| 3 | RNF-01 (temp=0, rubrica versionada) | `ModelRef.temperature=0.0`; `JudgeOpinion.rubric_id` obrigatório; `CheckOutcome.deterministic_hash` |
| 4 | Modelo/pesos/limiares de config | `EvaluatorConfig` + `weight_profiles.yaml` + gateway; guard CC-H07 |
| 5 | Evidência exige símbolo; Finding usa FindingType | `EvidenceRef.symbol` obrigatório; `Finding.dimension/identity` derivados da taxonomia |
| 6 | Sem score sem reasoning+confidence | validador de `DimensionResult` |
| 7 | Fallback de modelo nunca silencioso | `model_substitutions` no laudo; política escalonada entra no wrapper T-302 (M1) |
| 8 | Ganchos Fase 2 vazios | `dynamic_metrics` opaco (rejeita ≠ None na Fase 1); `TargetRunner`/`execution_gate` declarados mas NÃO cabeados ao grafo (T-804) |

---

## 2i. Melhorias pós-dogfooding (Frentes 1–4 de PLANO-MELHORIAS.md)

Rodar o MVP contra o próprio avaliador expôs ruídos de comunicação e de motor. As 4 frentes do
plano de melhorias foram implementadas **sem tocar o cálculo nem a suíte de aceite** (CA/CB
intactos) — nenhum item foi "⚠ PARE-E-CONFIRME". Novos T-IDs propostos no plano (T1.*/T2.*/T3.*/T4.*).

| Frente | Entrega | Arquivos | Requisitos | Testes |
|---|---|---|---|---|
| **F1 — Parser multi-formato** | `ConfigExtractor` (YAML/JSON/TOML/INI/`.env`) → `ConfigItem`s achatados em `coverage.fully_analyzed`; malformado → `unreadable`. Documentação/dados não-analisáveis (`.md`, lock files…) deixam de contar como amostragem → **fim do laudo PARCIAL espúrio** | `extract/config_extractor.py` (novo), `extract/registry.py`, `extract/tsm_builder.py` | RF-01/12/14, RNF-07 | `tests/extract/test_config_extractor.py` (5) |
| **F2 — Prontidão estática (teto ≈90)** | `static_ceiling` (config, default 90, RNF-06) exposto no `ReportHeader`/JSON; render MD + resumo CLI anotam que a faixa 90–100 é da Fase 2. **Não muda score/veredito/faixas** | `config/evaluator_config.py`, `domain/contracts.py`, `report/{build,render}.py`, `cli.py` | RNF-04/08, §4.2.6 | `tests/report/test_static_ceiling.py` (5) |
| **F3 — Gateway (custo/perf)** | `ModelRef.max_tokens`/`timeout_s` (config, env-overridable); `ModelGateway` os repassa em `params` (chaves de dict → visíveis à análise) — fecha o acoplamento T3↔T4. **T3.2 cache de juízo:** `JudgeCache` (memoização por `(nó, conteúdo)`, RNF-01-safe), compartilhado por execução do grafo; extrator reconhece classe `*Cache` (achado `SEM_CACHE` honesto) | `config/evaluator_config.py`, `model_gateway/gateway.py`, `judge/{framework,contributors}.py`, `divergence.py`, `graph/{nodes,build_graph}.py`, `extract/python_extractor.py` | RF-DIM-C2/P2, RNF-06/12 | `tests/model_gateway/test_gateway.py` (+4), `tests/judge/test_judge_framework.py` (+3) |
| **F4 — Motor (falsos positivos/tipo)** | T4.1 retry/fallback **imperativos** (laço de tentativas, `try/except…continue`, iteração por papéis); T4.2 `max_tokens`/`timeout` via dict/subscrito/campo de config; T4.3 classificador robusto a meta-vocabulário (RAG só por estrutura de recuperação OU ≥2 grupos de vocabulário → corrige `tipo=rag`); T4.4 confiança do parcial **calibrada** (fração configurável); T4.5 harness por config de teste/CI | `extract/python_extractor.py`, `classify.py`, `report/build.py`, `extract/tsm_builder.py`, `config/evaluator_config.py` | RF-DIM-R2, RF-06/16, RF-DIM-Q1, RF-12 | `tests/extract/test_imperative_robustness.py` (8), `test_harness_detection.py` (6), `tests/report/test_partial_calibration.py` (4) |

**Decisões desta iteração (precisão > recall; sem mexer no cálculo):**
- **Documentação/dados não disparam parcial:** `tsm_builder` separa `ignored_docs` (`.md`, LICENSE,
  lock files…) de `best_effort` (fonte sem extrator, ex.: TS/JS adiado). Só `sampled` (budget +
  fonte não suportada) dispara PARCIAL — "sem amostragem espúria" (§3). README.md deixa de cair em
  `coverage.sampled` (teste de unidade ajustado).
- **Classificador RAG:** `index` (que casava `index_artifact`) foi **excluído** dos sinais
  estruturais; RAG exige `retriev*/vector*/embedding*…` OU ≥2 grupos de vocabulário. Inferência
  fraca → `None` → `select_weights` cai no perfil **neutro** (RF-16) em vez de pesos de RAG indevidos.
- **Contradição modelo↔config escopada ao MESMO arquivo:** comparar slug declarado num módulo vs.
  slug usado em OUTRO (ex.: default de gateway vs. exemplo de teste) gerava falso positivo no
  dogfood. A heurística já se declarava "conservadora, baixo falso-positivo" — same-file a torna mais
  precisa; o fixture de CB-08 (config+código no mesmo arquivo) é preservado.
- **Loader pula `tests/fixtures/`:** alvos sintéticos adversariais (loop sem teto, prompts RAG,
  contradições) são DADOS de teste, não a lógica do sistema (já isentos do ruff). `tests/` permanece
  no escopo (harness — T4.5); só `fixtures` SOB diretório de teste é pulado (top-level `fixtures/`
  preservado).

**Re-run do dogfood (critério §8 do plano) — `avalia .` na raiz:** veredito **aprovado**,
**Score 89/100** (exibido como *Prontidão estática (Fase 1), teto ~90*), **não-parcial**, tipo
**indeterminado** / perfil **fallback_neutro**, confiança **médio** (harness encontrado), **0
crítico / 0 importante / 0 recomendação** (com T3.2, o `cache` deixa de ser sugestão — o
`JudgeCache` é detectado). Antes: parcial, 83/100, `tipo=rag`, 0 críticos/5 importantes.

**Validação:** `ruff check` + `ruff format --check` + `mypy src` limpos · **240 testes verdes**
(+36 nesta iteração; +4 Postgres gated). Suíte de aceite (CA-01..15/CB-01..10) **intacta** — nenhum
número de cálculo ou faixa mudou.

---

## 7. Estado atual + Roadmap das próximas etapas (M8+)

**Onde estamos.** Fase 1 (avaliação estática) implementada de ponta a ponta (M0–M7), suíte de
aceite fechada (CA-01..15/CB-01..10), porta de entrada MVP (`avalia <alvo>`) e melhorias
pós-dogfooding (Frentes 1–4, §2i), **M8** (histórico/comparação no CLI), **M10** (extrator TS/JS
via tree-sitter) e **M11** (serde durável + docs de produção). 262 testes verdes; CI mecânico no
PR. O **núcleo do produto está pronto**; resta (a) ~~lacunas de uso~~ (M8 ✅), ~~cobertura de
linguagem~~ (M10 ✅), ~~endurecimento de produção~~ (M11 ✅), (b) **validar empiricamente que
o AVALIA julga bem** (meta-avaliação real — a pergunta central da spec §9.3), (c) ampliar
cobertura, (d) endurecer para produção e, por fim, (e) a **Fase 2 dinâmica** (roadmap, gated).

> Convenção: cada etapa cita os requisitos/decisões da fonte da verdade. **⚠ PARE-E-CONFIRME**
> marca trabalho que toca a Fase 2 (S-05) ou contraria EC-01..EC-10 — não iniciar sem aprovação
> humana explícita (CLAUDE.md).

### M8 — Fechar lacunas de uso da Fase 1 ✅ *(M8-1/M8-2 concluídos; M8-3 já estava pronto; M8-4 → M11)*
Itens que já tinham a infraestrutura pronta nos testes mas **não estavam cabeados na porta de uso**.

| Tarefa | Estado | Entrega | Requisitos |
|---|---|---|---|
| **M8-1 — Histórico/comparação no CLI** | ✅ | `cli.py`: flag `--history-dir` + `_make_repository` (precedência `--history-dir` → `AVALIA_PG_DSN` → nenhum); `build_avalia_graph(gateway=..., repository=...)`; linha de comparação no resumo. Antes `compare_history` era no-op pela CLI. | RF-28, RF-29; US-05, US-08; RNF-11 |
| **M8-2 — Persistência local sem Postgres** | ✅ | `persistence/json_file.py` — `JsonFileReportRepository` (stdlib, sem driver): grava `<dir>/<report_id>.json`, `latest_for` por `created_at`; `target_id` só no JSON (sem sanitizar path). Implementa o `Protocol ReportRepository`; coberto pelo teste-contrato parametrizado. | RF-28; D-02; RNF-11 |
| **M8-3 — Guard `guard_no_target_exec` AST-aware** | ✅ já pronto | O hook **já** usa `scan_ast` (regex só como fallback quando `ast.parse` falha) — sem falso positivo em docstrings. Nada a fazer. | RNF-05 (tooling) |
| **M8-4 — Serde do checkpointer p/ Postgres** | → **M11** | É concern de produção (HITL durável com `PostgresSaver`); a CLI usa `MemorySaver` e o repositório de laudos é independente do checkpointer. Movido para M11. | RF-24; plan §3.8a |

**Decisões/notas do M8:** repositório de histórico é **opt-in** (sem flag → comportamento atual,
zero config — RNF-11); nome do arquivo = `report_id` (uuid) evita sanitizar o `target_id` livre;
`latest_for` ignora arquivos corrompidos/alheios (postura defensiva). Testes: `+jsonfile` no
teste-contrato (`tests/persistence/test_repository.py`) e 2 testes de CLI (compara v1→v2 com
`--history-dir`; sem flag não persiste). **249 testes verdes**; gates limpos; nada executa o alvo.

### M9 — Meta-avaliação REAL (validar se o AVALIA julga bem) *(operacional; bloqueado por D-03/D-04)*
O **pipeline** já existe (M6: `metaeval/`, smoke T-1007). O que falta **não é código**, é dado e
execução:

| Tarefa | O que falta | Requisitos | Bloqueio |
|---|---|---|---|
| **M9-1 — Curar o dataset de benchmark** | Conjunto de sistemas-alvo com **veredito humano de referência por dimensão** + classificação (topologia/tipo). Trabalho humano de curadoria. | MS-07, MS-09; **D-03** | Dependência externa (curadoria). |
| **M9-2 — Primeiro lote + calibração do limiar** | Rodar o AVALIA no dataset, comparar com o rótulo humano (`metaeval/harness.py`), **calibrar o limiar de "confiável"** (não fixado na Spec — EC-10). | MS-04, MS-08; **D-04** | Depende de M9-1. |
| **M9-3 — Relatório de meta-avaliação periódico** | Job que mede MS-04/07/08/09 ao longo do tempo (deriva/melhoria). | MS-10 | Depende de M9-1/M9-2. |

> Sem M9 o AVALIA **funciona**, mas a confiança nos seus julgamentos permanece *autodeclarada*.
> Esta é a etapa de maior valor de credibilidade do produto.

### M10 — Cobertura de linguagem: 2º extrator (TS/JS) ✅ *(concluído)*
- **M10-1** ✅ — `extract/treesitter_extractor.py`: extração **estrutural** JS/TS via tree-sitter,
  plugando na interface `LanguageExtractor` (T-101) e no registry, **sem tocar o TSM nem os
  avaliadores** (resolução #1). Cobre agentes (func/arrow/classe), prompts (const + props de
  objeto), arestas (`addEdge`/`addConditionalEdges`), loops com teto best-effort (`while(true)`),
  atribuição de modelo, estado compartilhado (interface `*State`, param `state`) e robustez
  (try/catch, retry, timeout, streaming, fallback, cache, validação). Gramáticas via import
  preguiçoso; se ausentes, os arquivos caem em best-effort (registry não registra).
- **M10-2** ✅ — fixture `tests/fixtures/js_multiagente/graph.ts` + `tests/extract/test_treesitter_extractor.py`
  (8 testes); `build_report` declara a **confiança reduzida** da análise estrutural-sem-tipos
  (RNF-08, `is_structural_only`). **Ingest:** `ingest_validate` passou a reconhecer JS/TS como
  "código-fonte" (via `language_for_path`) — antes um alvo TS/JS era rejeitado no portão (RF-02).
- Endereça o **Risco R1** (cobertura de linguagem) do plan §9. Python (`ast`) segue first-class.
- **Deps:** `tree-sitter-javascript`/`tree-sitter-typescript` adicionadas ao `pyproject.toml`.
- **Dogfood:** `avalia` sobre um alvo `.ts` → multiagente/rag, score 77, **crítico** "loop sem
  teto no nó `retrieverAgent`" (`while(true)`), limitação estrutural declarada. 257 testes verdes.

### M11 — Endurecimento de produção / deployment ✅ *(parte de código concluída; ops documentado)*
O único **gap de código** real era o serde do checkpointer (atrito do M3 = M8-4); o resto já
existia (repo Postgres T-601, LangSmith env-gated T-901) e foi **documentado** para deployment.

| Tarefa | Estado | Entrega |
|---|---|---|
| **M8-4 / serde durável** | ✅ | `graph/serde.py` — `avalia_checkpoint_serde()`: `JsonPlusSerializer` com TODOS os tipos `avalia.*` (52, coletados por introspecção dos módulos de domínio/config/estado) na allowlist. Resolve o aviso do LangGraph ("tipos não-registrados serão bloqueados") → `interrupt`/`resume` (RF-24) à prova de `LANGGRAPH_STRICT_MSGPACK` e do `PostgresSaver`. `build_graph` passa a usá-lo no `MemorySaver` default. **Não usa allow-all** (segurança preservada). |
| **M11-1 / Postgres em prod** | ✅ código (M8) + docs | O `PostgresReportRepository` (T-601) já é cabeado no CLI via `AVALIA_PG_DSN` (M8). README §Produção documenta o setup. |
| **M11-2 / LangSmith** | ✅ docs | Já env-gated (T-901, não-bloqueante). README documenta `AVALIA_TRACING`/`LANGSMITH_API_KEY`. |
| **M11-3 / API HTTP** | ⏸ adiado (deliberado) | Documentado como adiado (EC-05 sem auth na Fase 1; evitar superdimensionar). O grafo é reusável por um serviço futuro. |

**Notas do M11:** o serde coleta tipos por introspecção (robusto a novos contratos — basta o
módulo estar na lista); `importlib` foi **evitado** (o guard RNF-05 o proíbe em `src/`) usando
imports diretos. Teste `tests/graph/test_m11_serde.py` (5) prova roundtrip por tipo **sob modo
estrito** (0 avisos). README ganhou a seção **Produção**. 262 testes verdes.

### M12+ — Fase 2: avaliação dinâmica *(roadmap — ⚠ PARE-E-CONFIRME, S-05)*
Os **ganchos já existem** (T-804: `execution_gate`, `TargetRunner`, `TestCaseGenerator`, slot
`dynamic_metrics`), mas **nada disso pode ser implementado sem confirmação humana explícita** —
Fase 2 está fora do escopo atual (S-05) e executar o alvo viola o invariante absoluto da Fase 1
até que o gate de aprovação (RF-23/CA-12) seja construído.

| Tarefa (roadmap) | Escopo | Requisitos |
|---|---|---|
| **M12-1 — Gate de execução** | `execution_gate` real entre N5 e N7 com `interrupt()` de aprovação **antes** de qualquer execução; nenhuma execução por omissão/timeout. | RF-23, CA-12, RNF-05 |
| **M12-2 — Runner isolado** | Implementar `TargetRunner` num **ambiente sandboxed** (isolamento de credenciais/estado — S-06). | O7; D-01 |
| **M12-3 — Geração de casos de teste** | `TestCaseGenerator` consumindo o TSM (já disponível) para gerar casos + critérios de sucesso. | O8 |
| **M12-4 — Captura de traces + métricas reais** | Popular `dynamic_metrics` (refina o slot opaco): custo/latência reais, taxa de alucinação, calibração de confiança, trajetória real de ferramentas. | O9; RF-13 (fecha o que a Fase 1 não pôde medir) |

**Ordem recomendada:** M8 (semanas) → M9 (depende de curadoria humana, pode correr em paralelo) →
M10 → M11 → M12 (só após decisão de negócio + confirmação humana).

### Decisões/atritos acumulados (M1–M7) — insumo do roadmap acima
- **Extrator `ast`-only** (escolha do usuário); tree-sitter deferido via a interface plugável.
- **Tracing aplicado no `invoke` (callbacks), não na construção do grafo** — `build_avalia_graph`
  permanece sem dependência de observabilidade; LangSmith é opcional e nunca bloqueia o laudo.
- **Meta-avaliação é job offline** sobre laudos + dataset; o limiar de "confiável" é diferido
  (D-04) e o dataset real é curadoria humana (D-03) — o código entrega só o pipeline de medição.
- **Juiz injetável por gateway**; default determinístico, gateway mockado nos testes.
- **Resolução de divergência registra + ajusta confiança**, sem sobrescrever o score (regra 6).
- **Serde do checkpointer LangGraph**: registrar `avalia.domain.*` (chip de tarefa) antes que
  versões futuras bloqueiem tipos não-registrados — relevante para o `PostgresSaver` do M4.
- **`StateGraph` tipado como `Any`** em `build_graph.py`: fronteira pragmática com o typing
  estrito do LangGraph (nós `Callable[[AvaliaState], dict]` não encaixam no `_Node[Never]`).
- **Atrito de guardas (a melhorar):** `guard_no_target_exec` e `block_sql_destructive` são
  baseados em regex e geram falso positivo quando docstrings/PR-body mencionam os literais
  proibidos (`importlib`, `TRUNCATE`). Tornar `guard_no_target_exec` AST-aware (como o de
  modelo, que ignora strings/comentários) é um aperfeiçoamento candidato.
