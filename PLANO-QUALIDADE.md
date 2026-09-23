# Plano de Implementação — Auditoria de Qualidade do AVALIA (marco MQ)

> Documento de trabalho, **autocontido**, para implementar PR a PR. **Não é fonte da verdade**: as
> fontes são [spec.md](spec.md) v0.5 · [plan.md](plan.md) v1.4 · [tasks.md](tasks.md) v1.4, já
> emendadas com as decisões abaixo (PR-D). Sucede o [PLANO-MELHORIAS.md](PLANO-MELHORIAS.md) (concluído).

## 1. Contexto

Auditoria de 2026-09-22 no `master` (`f8a3b92`). Os gates estavam verdes: 262 testes (4 Postgres
pulados localmente), `ruff`, `ruff format`, `mypy --strict` (76 arquivos). O dogfood (`avalia .`)
dá **aprovado 89/100 e 0 achados**. Mesmo assim, lendo o código e com testes pontuais, a auditoria
achou defeitos que a análise estática não enxerga:

| # | Defeito (confirmado) | Requisito violado |
|---|---|---|
| 1 | O juiz só captura `TransientModelError`/`ModelUnavailableError`, que ninguém lança. Um `RateLimitError` (429) real **propaga e aborta a avaliação** (reproduzido). O passo "saída malformada" nunca dispara, porque o parser lança exceção em vez de devolver outro tipo. | RNF-12, CB-10 |
| 2 | `RetryPolicy.backoff_seconds` nunca é lido: as tentativas saem em sequência imediata. | RNF-12 |
| 3 | `BudgetState.accumulated_cost` nunca é incrementado (`cost_ceiling` sem efeito); o tempo só é checado antes do fan-out; a CLI não expõe tetos. O teste de CA-13 passa porque **injeta** o custo. | RF-12, CA-13 |
| 4 | Duas heurísticas de harness divergentes (`ingest.py` e `tsm_builder.py`): `latest_version.py` é tomado como harness; `tests/helpers.py` e `src/foo.test.ts` não são. | RF-DIM-Q1 |
| 5 | Nota base e penalidades são constantes em `evaluators/` (90; 22/9/3; Trajetória 85/25); `static_ceiling=90` é declarado à parte da nota base. | RNF-06 |
| 6 | Achados do juiz: urgência sempre IMPORTANTE, evidência = 5 primeiros prompts, `statement` = `reasoning[:80]`. | RF-29, RNF-07 |
| 7 | A CLI só trata `FileNotFoundError` (DSN inválido, permissão ou `--max-files 0` → traceback). | RNF-11 |
| 8 | Sem medição de cobertura de testes. | DoD global |

Pontos fortes preservados: TSM imutável e plugável, regras invioláveis com enforcement (hooks e
testes-guarda), CI completo com Postgres real, rastreabilidade em todo módulo, nenhum segredo no laudo.

## 2. Decisões do dono (fixas; registradas na spec §11)

| ID | Decisão |
|---|---|
| **DQ-01** | Teto de custo em **duas unidades**: `token_ceiling` (principal, sempre aplicável) e `cost_ceiling` em moeda, que só vale com `model_prices` na config; sem preço, o laudo declara que o custo não é calculável. |
| **DQ-02** | O juiz-LLM **não emite achado crítico** (só sugestão/importante); crítico é exclusivo de fato determinístico. |
| **DQ-03** | Parâmetros de pontuação são configuração (`ScoringConfig`). |
| **DQ-04** | A Robustez declara em `static_limitations` que presença de retry/fallback ≠ eficácia. |

## 3. Regras para todos os PRs

- Um PR por frente, cada um a partir do `master`; cada PR marca seu item na §5 e atualiza o `PROGRESS.md` (§7/MQ e, ao fim, a seção §2j).
- **Nada executa o alvo** (RNF-05) e nada implementa a Fase 2 (S-05). `py -m pytest tests/guards -q` em todo PR.
- **Invariante:** com a config padrão, notas, vereditos e faixas dos laudos determinísticos **não mudam**
  (`tests/acceptance/test_reproducibility.py` bit-idêntico). As únicas mudanças esperadas no laudo são a
  limitação nova da Robustez (PR-5) e a evidência dos achados do juiz (PR-5), ambas declaradas.
- Testes nunca chamam modelo real: exceções de provedor são **classes locais** com o mesmo nome e `status_code` dos SDKs.

## 4. Frentes

### PR-1 — Resiliência real do juiz (itens 1 e 2) · T-302/T-1008 reforçados · plan §3.2c
- **Q1.1** `src/avalia/model_gateway/errors.py`: `TransientModelError`, `ModelUnavailableError`, `MalformedOutputError`; `judge/framework.py` reexporta os dois primeiros (compatibilidade).
- **Q1.2** `classify_provider_error(exc)`, sem importar SDK no topo:
  - transitório: status 408/409/429/500–504/529; `RateLimitError`, `APITimeoutError`, `APIConnectionError`, `InternalServerError`, `OverloadedError`; `TimeoutError`, `ConnectionError`, `httpx.TimeoutException`;
  - indisponível: status 400/401/403/404; `NotFoundError`, `AuthenticationError`, `PermissionDeniedError`;
  - malformado: `OutputParserException`, `pydantic.ValidationError`, `json.JSONDecodeError`;
  - outra exceção **dentro da chamada ao modelo** → indisponível, com o nome da classe na substituição.
- **Q1.3** `ModelGateway.invoke_structured(node_type, role, schema, messages) -> StructuredCallResult(parsed, input_tokens, output_tokens)` usando `with_structured_output(schema, include_raw=True)`; `try/except` só em volta da chamada. `GatewayLike` passa a exigir `invoke_structured` e `retry_for`.
- **Q1.4** `Judge._run_angle` sobre `invoke_structured`, com razão de substituição específica (ex.: `fallback de modelo aplicado (primário: indisponível — NotFoundError)` ou `… transitório após 3 tentativa(s) — RateLimitError`).
- **Q1.5** Backoff: `RetryPolicy.max_backoff_seconds` (default 30); espera `min(backoff_seconds·2ⁿ, max_backoff_seconds)` entre tentativas no mesmo modelo, sem jitter, sem espera após a última; `sleep` injetável.
- **Q1.6** Testes: `tests/model_gateway/test_provider_errors.py` (classificação + `invoke_structured`) e `tests/judge/test_judge_resilience.py` (429 → retry com delays 1s/2s; 404 no primário → fallback declarado e confiança reduzida; 401 nos dois → `partial`; parse inválido → re-solicitação; exceção desconhecida → fallback com o nome); teste de grafo com gateway que sempre lança 429 → laudo parcial. Em vez de um helper em `tests/conftest.py` (`tests/` não é pacote), a lógica de invocação fica na base `StructuredInvoker` (`model_gateway/structured.py`), usada pelo `ModelGateway` real; os mocks só passam a herdar dela, em `tests/judge/test_judge_framework.py`, `tests/acceptance/test_acceptance_matrix.py`, `tests/acceptance/test_reproducibility.py`, `tests/divergence/test_divergence.py`, `tests/graph/test_e2e.py`, `tests/graph/test_m3_hitl.py`, `tests/graph/test_m5_budget.py`.
- **DoD:** a simulação de 429 da auditoria degrada em vez de propagar; gates verdes; aceite intacto.

### PR-2 — Detector de harness único (item 4) · T-107 · plan §3.2g
- `src/avalia/extract/harness.py`: `is_harness_path` por partes do caminho (diretórios `tests`/`test`/`__tests__`; `test_*.py`, `*_test.py`, `*.test.{js,jsx,ts,tsx,mjs,cjs}`, `*.spec.*`; `conftest.py`); mover `_file_signals_harness`/`_detect_harness` de `tsm_builder.py`.
- `ingest.py` apaga `_HARNESS_PATH_HINTS` e usa a nova função.
- Testes em `tests/extract/test_harness_detection.py`: os 4 casos da auditoria + caminho com `\` + teste de consistência ingest↔TSM.
- **Risco:** algum fixture de aceite pode mudar de confiança (CA-06); rodar o aceite e justificar no PR qualquer mudança, sem ajustar fixture em silêncio.

### PR-4 — Pontuação como config (item 5) · T-008 · plan §3.2f
- `ScoringConfig` em `config/evaluator_config.py`: `base_score=90`, `critical_penalty=22`, `important_penalty=9`, `suggestion_penalty=3`, `trajectory_base_score=85`, `trajectory_no_cap_penalty=25` (validados 0–100).
- Remover as constantes de `evaluators/base.py` e `evaluators/trajetoria.py`; avaliadores recebem `scoring: ScoringConfig = ScoringConfig()`; os nós de dimensão e `budget_degraded` passam `config.scoring`.
- `static_ceiling: int | None = None` + propriedade `effective_static_ceiling` (explícito ou `scoring.base_score`); explícito menor que a nota base → erro de validação. `report/build.py` usa a propriedade.
- Guarda nova `tests/guards/test_no_scoring_constants.py` (AST: nenhuma constante de módulo `*_PENALTY`/`*_SCORE` em `evaluators/`).
- **DoD:** reprodutibilidade bit-idêntica com a config padrão; `tests/report/test_static_ceiling.py` verde.

### PR-3 — Orçamento com consumo real (item 3) · T-805, T-802 reforçado · plan §3.3/§3.5
- `BudgetMeter` em `graph/budget.py` (lock; tokens de entrada/saída, custo, tempo), criado por `run_evaluation` e passado em `config["configurable"]`, fora do checkpoint. O `JudgeCache` também passa a ser por execução.
- O `Judge` chama `meter.charge(...)` após cada chamada e checa `meter.exceeded(config)` antes de cada ângulo; estourado → `JudgeContribution.partial_reason="teto de orçamento"` (o nó de dimensão para de escrever "fallback esgotado" quando a causa é o teto).
- `EvaluatorConfig`: `token_ceiling: int | None`, `model_prices: dict[str, ModelPrice]` (preço por Mtok de entrada e de saída); `cost_ceiling` passa a ser explicitamente moeda.
- `BudgetState`: âncora `started_at` em horário real (o relógio monotônico não serve entre processos).
- Laudo: `metadata.budget_usage` (`input_tokens`, `output_tokens`, `cost`, `cost_unavailable_reason`, `elapsed_s`, tetos, `degraded_dims`), renderizado no Markdown e no JSON.
- CLI: `--token-ceiling`, `--cost-ceiling`, `--time-ceiling`.
- Testes: gateway falso que reporta tokens + teto baixo → dimensões seguintes degradam com razão "teto" e o laudo sai parcial com `budget_usage`, sem injetar custo; sem preço → custo declarado como não calculável; teto de tempo com relógio falso; retomada de HITL sem erro de tempo.
- **Risco declarado (plan R10):** com teto atingido e ramos paralelos, quais dimensões degradam pode variar; o laudo sempre as declara.

### PR-5 — Achados do juiz + limitação da Robustez (item 6, DQ-02, DQ-04) · T-312, T-313 · plan §3.2d/§3.2e
- `JudgeVerdict`: `urgency` ∈ {sugestão, importante} (crítico rejeitado pelo schema), `evidence_symbol: str | None`; validador: `finding_type` exige `finding_statement` (sai o `reasoning[:80]`).
- `contributors._target_content` envia a lista de símbolos do TSM **dentro** dos delimitadores de dado não confiável; `Judge.assess(..., known_symbols=...)` valida o símbolo (inexistente → âncora do projeto + nota "símbolo não localizado no TSM").
- Robustez: `static_limitations` = "presença de retry/fallback no código não prova eficácia sob falha real; eficácia só verificável na Fase 2".
- Testes: identidade estável com o mesmo símbolo; símbolo inexistente → âncora; crítico rejeitado; caso novo no teste adversarial T-310 (símbolo injetado pelo alvo); limitação presente em todo laudo.
- **Migração (plan R11):** a identidade dos achados do juiz muda uma vez; declarar no README e no PROGRESS.

### PR-6 — CLI robusta + gate de cobertura (itens 7 e 8) · T-1009
- Códigos de saída: 0 sucesso; 2 erro de entrada (caminho, permissão, `ValidationError` da config); 3 infraestrutura (Postgres via `AVALIA_PG_DSN`); 1 erro interno (com dica de `--debug`). `--debug` mostra o traceback. Testes em `tests/cli/`.
- `pytest-cov` em `[project.optional-dependencies].dev`; `[tool.coverage.run] source=["avalia"], branch=true`; `[tool.coverage.report] show_missing=true, fail_under=<piso medido no PR, arredondado para baixo>`; CI: `python -m pytest -q --cov --cov-report=term-missing`.

### PR-7 — Melhorias finas
- `loader.py`: `os.walk` cortando diretórios ignorados na descida (sem entrar em `node_modules`/`.venv`), mantendo a ordem determinística.
- `config_extractor.py`: mascarar como `<redacted>` os valores de chaves `*KEY*`, `*SECRET*`, `*PASSWORD*`, `*TOKEN*`, `*DSN*` (a chave continua visível; a detecção de contradição de slug de modelo não é afetada).
- `cli.py`: tipar `_summary(report: EvaluationReport)` e `_make_repository(...) -> ReportRepository | None`.
- `aggregate.py`: calcular `_below_floor` uma vez; `registry.language_for_path` via `Path.suffix` (cuidando de `.env` e sufixos compostos).
- Versão do pacote `0.0.0` → `0.11.0` (`pyproject.toml` e `__init__.py`).
- **Achado no PR-3 (pré-existente):** reinvocar o MESMO grafo compilado com o MESMO `thread_id` continua o estado do checkpoint, e `dimension_results` (reducer `operator.add`) acumula as duas execuções — nota agregada > 100 (`ValidationError`). A CLI não é afetada (grafo e `MemorySaver` novos por execução), mas um serviço que reuse o grafo seria. Correção proposta: a ingestão zera as listas acumuladas quando começa uma nova submissão (ou o runner gera um `thread_id` por execução), com teste de reuso.

## 5. Checklist

- [x] **PR-D** — spec v0.5, plan v1.4, tasks v1.4, CLAUDE.md (versões), PROGRESS (cabeçalho, números, §7/MQ, nota do guard), este plano.
- [x] **PR-1** — resiliência real do juiz (`model_gateway/{errors,structured,roles}.py`; +33 testes; 295 verdes)
- [x] **PR-2** — harness único (`extract/harness.py`; também unificou a 3ª cópia, em `extract/prioritize.py`; +20 testes)
- [x] **PR-4** — pontuação como config (`ScoringConfig`, inclusive o piso 50 e a penalidade de contradição da Trajetória; teto derivado; guarda de AST; +10 testes)
- [x] **PR-3** — orçamento com consumo real (`BudgetMeter`/`RunRegistry`; `budget_usage` no laudo; flags de teto na CLI; +12 testes)
- [x] **PR-5** — achados do juiz + limitação da Robustez (`JudgeVerdict.urgency`/`evidence_symbol`; `symbol_index`; nó de aresta com símbolo próprio; +12 testes)
- [ ] **PR-6** — CLI + cobertura
- [ ] **PR-7** — melhorias finas
- [ ] **Fechamento** — PROGRESS §2j (tabela de entregas, como a §2i), dogfood re-rodado e registrado, README (flags de teto, `--debug`, códigos de saída, garantias de resiliência, `model_prices`, mascaramento de segredos, cobertura, nota de migração), CLAUDE.md (comando de cobertura), proposta de caso "retry declarado mas ineficaz" em `benchmark/dataset.yaml` (curadoria humana, D-03).

Ordem: **PR-1 → PR-2 → PR-4 → PR-3 → PR-5 → PR-6 → PR-7**. PR-3 e PR-5 dependem do PR-1.

## 6. Critério de pronto do marco MQ

1. Gates verdes: `ruff check`, `ruff format --check`, `mypy src`, `pytest` (com Postgres no CI), `tests/guards`, cobertura ≥ piso.
2. Um 429 simulado produz **laudo parcial**, sem exceção.
3. Com `--token-ceiling` baixo e gateway simulado, o laudo sai parcial com razão "teto" e `budget_usage` preenchido.
4. Os 4 casos de harness da auditoria corretos; ingest e TSM concordam.
5. Nenhuma constante de pontuação em `evaluators/` (guarda ativa).
6. Suíte de aceite CA-01..15 / CB-01..10 intacta; reprodutibilidade bit-idêntica com a config padrão.
