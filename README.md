# AVALIA

**Avaliador ESTÁTICO de sistemas multiagentes de IA (Fase 1).** O AVALIA recebe os artefatos de um
sistema-alvo (código, prompts, config, harness) e produz um **laudo técnico** com pontuação por
dimensão, veredito, nível de confiança e recomendações priorizadas, **sem nunca executar o alvo**
(RNF-05/S-04). O alvo é apenas entrada, lido como texto.

Fontes da verdade: [spec.md](spec.md) · [plan.md](plan.md) · [tasks.md](tasks.md) ·
log de execução em [PROGRESS.md](PROGRESS.md).

## Instalação

Requer Python 3.12.

```bash
pip install -e .            # núcleo
pip install -e ".[dev]"     # + lint/tipos/testes
```

## Uso (MVP)

Aponte o AVALIA para o diretório do sistema-alvo:

```bash
avalia caminho/para/o/alvo --target-id meu-sistema --version v1
# ou, sem instalar o script:
python -m avalia caminho/para/o/alvo
```

Gera `avalia-out/laudo.md` (humano) e `avalia-out/laudo.json` (máquina) e imprime um resumo
(veredito, score, classificação, achados, recomendações).

> **Dica (laudo representativo):** aponte para a **raiz do repositório** do alvo, não só para
> `src/`. A raiz inclui `tests/`, `pyproject.toml`, `tox.ini`, workflows de CI, etc. — sem isso o
> AVALIA não encontra o harness de verificação e rebaixa a confiança da dimensão *Qualidade*
> (RF-DIM-Q1). Ex.: `avalia .` em vez de `avalia src/`.

> **Prontidão estática (Fase 1):** o score é exibido em `/100`, mas o teto da análise estática é
> **≈ 90** — a faixa 90–100 só é atingível com avaliação **dinâmica** (Fase 2). Um `83/100` não é
> "reprovado em 17 pontos": ~7 pontos são *headroom* reservado à Fase 2 (RNF-04).

### Opções

| Opção | Efeito |
|---|---|
| `--target-id ID` | Identificador do alvo (default: nome do diretório); vincula versões no histórico. |
| `--version V` | Versão/tag avaliada (default: `0`). |
| `-o, --out DIR` | Diretório de saída (default: `avalia-out`). |
| `--format {both,md,json}` | Formato(s) do laudo gravado(s) (default: `both`). |
| `--llm` | Liga os juízes-LLM via `ModelGateway` (default: **determinístico**, sem custo/credencial). |
| `--max-files N` | Teto de arquivos analisados a fundo; acima dele o resto é amostrado (laudo parcial honesto). |
| `--token-ceiling N` | Teto de tokens (entrada+saída) das chamadas de juízo; atingido → dimensões restantes no determinístico e laudo parcial. |
| `--cost-ceiling X` | Teto de custo em moeda. Só é calculável com `model_prices` na configuração (ver *Produção*); sem preço, o laudo declara o custo como não calculável e o teto de tokens segue valendo. |
| `--time-ceiling S` | Teto de tempo da avaliação, em segundos. |
| `--history-dir DIR` | Persiste o laudo e compara com a versão anterior do mesmo `--target-id` (ver *Produção*). |
| `--debug` | Em caso de erro, mostra o rastreamento completo. |

**Modo determinístico (padrão):** roda só as checagens estáticas (estrutura, controles de custo,
loops, retry/fallback, etc.) — reproduzível e sem chamadas de modelo. **`--llm`** acrescenta os
julgamentos semânticos (clareza de prompt, anti-injeção, grounding…) via `ModelGateway`
(default Opus→Sonnet, configurável por env — `AVALIA_DEFAULT_PRIMARY_MODEL`, `AVALIA_DEFAULT_BACKEND`,
etc.); requer `ANTHROPIC_API_KEY` (ou `OPENROUTER_API_KEY`). Substituições de modelo são sempre
declaradas no laudo (RNF-12).

O laudo registra o **consumo de orçamento** (tokens, custo quando há preço, tempo, tetos e
dimensões degradadas) no JSON (`metadata.budget_usage`), no Markdown e no resumo do CLI.

### Códigos de saída

| Código | Significado |
|---|---|
| `0` | Laudo gerado (inclusive laudo parcial). |
| `1` | Erro interno inesperado do AVALIA — rode de novo com `--debug`. |
| `2` | Entrada inválida: caminho inexistente ou sem permissão, configuração inválida, alvo sem código-fonte, saída não gravável. |
| `3` | Infraestrutura: repositório de histórico Postgres (`AVALIA_PG_DSN`) inacessível. |

## Garantias

- **Nunca executa o alvo** (RNF-05/S-04): só leitura estática (`ast` para Python; **tree-sitter**
  para TS/JS — estrutural, sem inferência de tipos, confiança reduzida declarada no laudo). Há hook
  + teste-guarda contínuos que falham o build se algum caminho introduzir execução/import do alvo.
- **Acesso a modelo só via `ModelGateway`** (RNF-06/RNF-12), nunca slugs hardcoded.
- **Resiliência real a falhas do provedor** (RNF-12/CB-10): limite de taxa, timeout e 5xx →
  nova tentativa no mesmo modelo com espera exponencial; modelo indisponível ou sem credencial →
  modelo de fallback, declarado no laudo com confiança reduzida; ambos esgotados → laudo parcial.
  A avaliação não aborta por falha pontual.
- **Sem segredos do alvo no modelo interno** (TSM): valores de chaves como `api_key`,
  `*_PASSWORD`, `token` e `dsn` são mascarados na extração — portanto não chegam ao checkpoint
  nem ao laudo (a chave continua visível).
- **Pontuação configurável** (RNF-06): nota base e penalidades vivem em `ScoringConfig`
  (`EvaluatorConfig.scoring`); os defaults reproduzem exatamente as notas anteriores.
- **Reproduzibilidade:** checagens determinísticas são bit-idênticas entre execuções; o juízo-LLM é
  estável por faixa (RNF-01).

## Produção (deployment)

A Fase 1 não exige autenticação nem banco para o uso local (RNF-11/EC-05). Para uma operação
durável, configure por ambiente — o código já suporta, só falta a infraestrutura:

- **Histórico de laudos (RF-28/29).** Local sem banco: `avalia <alvo> --history-dir ./histórico`.
  Em produção: defina `AVALIA_PG_DSN` (Postgres) e o CLI usa o `PostgresReportRepository`
  (schema idempotente `CREATE TABLE IF NOT EXISTS`; reusa a instância do checkpointer — resolução #3).
- **HITL durável (RF-24).** O `interrupt`/`resume` da divergência usa `MemorySaver` por padrão
  (suficiente para o CLI single-shot). Como **serviço**, injete um `PostgresSaver` construído com
  `avalia_checkpoint_serde()` (`avalia.graph.serde`) — o serde registra os tipos `avalia.*`, à prova
  do modo estrito (`LANGGRAPH_STRICT_MSGPACK`) e de versões futuras do LangGraph.
- **Tetos de custo em moeda (DQ-01).** Informe o preço por modelo na configuração —
  `EvaluatorConfig(cost_ceiling=0.50, model_prices={"<slug>": ModelPrice(input_per_mtok=3.0,
  output_per_mtok=15.0)})` — ao chamar o grafo por código. Sem preço para algum modelo usado, o
  custo é declarado como não calculável (nunca estimado em silêncio).
- **Um `thread_id` por avaliação.** `run_evaluation` gera um por omissão; informe o mesmo só para
  **retomar** a mesma avaliação (HITL). Reusar o de uma avaliação concluída é recusado.
- **Observabilidade (MS-10).** Tracing é **opcional e não-bloqueante**: ligue com
  `AVALIA_TRACING=1` (+ `LANGSMITH_API_KEY`); ausente, o laudo é gerado igual.
- **API/serviço HTTP:** deliberadamente **adiado** (avaliar antes de construir — sem auth na Fase 1,
  EC-05). O avaliador roda hoje via CLI ou `build_avalia_graph().invoke`.

## Desenvolvimento

```bash
python -m pytest -q             # suíte completa
python -m pytest -m fast -q     # gate rápido
python -m ruff check . && python -m ruff format --check .
python -m mypy src
python -m pytest -q --cov        # cobertura (o CI falha abaixo do piso em pyproject.toml)
```

CI (GitHub Actions) enforça esses gates em todos os PRs, com Postgres em serviço para os testes de
persistência.

> **Nota de migração (v0.11.0):** a evidência dos achados emitidos pelo juiz-LLM passou a ser o
> símbolo do alvo citado e validado (antes: os primeiros prompts). Na primeira comparação histórica
> depois da atualização, esses achados aparecem uma vez como resolvidos/novos. Achados
> determinísticos não mudam.
