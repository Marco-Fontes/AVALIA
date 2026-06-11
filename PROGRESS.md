# AVALIA — Registro de Execução (Fase 4 / Implementação)

**Atualizado:** 2026-06-10 · **Iteração 1:** M0 → M1.
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
| **M3** — divergência + HITL | ⏳ próximo |

Validação atual: `ruff check .` limpo · `mypy src` limpo (46 arquivos) · **122 testes verdes** (`py -m pytest -q`).
Smoke 7-dim: o grafo gera um `EvaluationReport` com as 7 dimensões em fan-out (veredito
condicional, condições priorizadas e rastreáveis, recomendações consolidadas), renderizável em MD/JSON.

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
| 8 | Ganchos Fase 2 vazios | `dynamic_metrics` opaco (rejeita ≠ None na Fase 1); `TargetRunner`/`execution_gate` não criados |

---

## 7. Próximo passo — M3 (divergência + HITL)

Épico E4: N4 `detect_divergence` (gatilho por faixas qualitativas divergentes ou confiança <
piso, T-401), re-julgamento automático/reconciliação (T-402), `ApprovalProvider`+CLI (T-403),
N4h `human_gate` com interrupt/resume (T-404, usa o checkpointer já cabeado), registro de
divergências no laudo (T-405). Valida CA-10 (reconciliação automática) e CA-11 (escalonamento).

### Decisões/atritos acumulados (M1–M2)
- **Extrator `ast`-only** (escolha do usuário); tree-sitter fica para M5 via a interface plugável.
- **Juiz injetável por gateway**; default determinístico, gateway mockado nos testes (M1–M2).
- **`StateGraph` tipado como `Any`** em `build_graph.py`: fronteira pragmática com o typing
  estrito do LangGraph (nós `Callable[[AvaliaState], dict]` não encaixam no `_Node[Never]`).
- **Atrito de guardas (a melhorar):** `guard_no_target_exec` e `block_sql_destructive` são
  baseados em regex e geram falso positivo quando docstrings/PR-body mencionam os literais
  proibidos (`importlib`, `TRUNCATE`). Tornar `guard_no_target_exec` AST-aware (como o de
  modelo, que ignora strings/comentários) é um aperfeiçoamento candidato.
