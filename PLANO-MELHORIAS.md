# Plano de Implementação — Melhorias do AVALIA (pós-dogfooding)

> Documento de trabalho, **autocontido**, para implementar em outra sessão. **Não é fonte da
> verdade** (spec/plan/tasks permanecem imutáveis). Substitui o antigo `PLANO-100.md` (a ideia de
> "subir para 100" foi descartada pelo dono: o teto 100 fica reservado para a Fase 2 dinâmica).

## 1. Contexto (resumo do que motivou o plano)

Rodamos o MVP contra o próprio código do avaliador:

```bash
PYTHONPATH=src py -m avalia src/avalia --target-id avalia-self --version <sha> --out .avalia-self
```

Resultado: *aprovado*, **83/100**, classificação *multiagente / tipo rag*, **LAUDO PARCIAL**,
confiança geral *baixo*; 0 críticos, 5 importantes (`sem_limite_tokens`, `sem_timeout`,
`sem_harness_verificacao`, `sem_retry`, `sem_fallback_modelo`).

Duas perguntas do dono fecharam o diagnóstico:
- **Por que parcial/baixo?** Porque `config/weight_profiles.yaml` **não tem parser** (só há extrator
  Python) → vira "best-effort/amostrado" → **um único arquivo** dispara o laudo PARCIAL, e o parcial
  **rebaixa a confiança de todas as 7 dimensões**. Some-se a isso `qualidade=baixo` por não achar
  harness — artefato de eu ter apontado só para `src/` (os testes estão em `tests/`).
- **`83/100` é incoerente com o teto de 90/85?** Sim, é um defeito de **comunicação**: a régua mostra
  `/100`, mas o cálculo determinístico **trava em ~90** (base) / 85 (trajetória) — 100 é inalcançável
  na Fase 1. A escala anuncia um máximo que o motor não produz.

## 2. Decisões fixas (do dono) — guiam todo o plano

1. **Parser multi-formato:** contemplar YAML, JSON, TOML, INI, `.env` (formatos de **config/dados**),
   para que deixem de ser "não analisados" e parem de disparar laudo parcial.
2. **Manter o cálculo estático como está** (base 90 / trajetória 85). **Não** subir o teto para 100
   agora. Em vez disso, **exibir honestamente** como *"prontidão estática"* com **teto 90**; a faixa
   90–100 fica reservada para quando a **Fase 2 (dinâmica)** for implementada.
3. Implementar também as correções reais e os pontos-cegos apontados no laudo.

> Consequência boa: como **não** mexemos no cálculo nem nas faixas, **não há efeito-cascata na suíte
> de aceite** (CA-01..15/CB-01..10). Nenhum item deste plano é "⚠ PARE-E-CONFIRME".

---

## 3. Frente 1 — Parser multi-formato (config/dados) — *decisão 1*

**Objetivo:** YAML/JSON/TOML/INI/`.env` passam a ser **analisados** (entram em `coverage.fully_analyzed`),
não "amostrados" — eliminando o laudo parcial espúrio e alimentando o TSM com fatos de config.

> Escopo: isto cobre **formatos de config/dados** (o que o dono pediu: "YAML, JSON, etc."). Outras
> **linguagens de programação** (TS/JS via tree-sitter) são um esforço maior e **continuam adiadas**,
> entrando pela mesma interface `LanguageExtractor` no futuro.

### T1.1 — `ConfigExtractor` (novo)
- **Arquivo:** `src/avalia/extract/config_extractor.py`, implementando o protocolo `LanguageExtractor`
  (`extract/base.py`).
- **Fazer:** ler por extensão e produzir `ConfigItem(key, value_expr, evidence)` para as chaves
  (achatadas, ex.: `rag.alucinacao`), marcando os arquivos em `ExtractionResult.files`:
  - `.yaml`/`.yml` → `yaml.safe_load` (PyYAML já é dependência).
  - `.json` → `json.loads` (stdlib).
  - `.toml` → `tomllib.loads` (stdlib 3.11+).
  - `.ini`/`.cfg` → `configparser` (stdlib).
  - `.env` → parse simples `CHAVE=valor` linha a linha.
  - Falha de parse (arquivo malformado) → adiciona a `unreadable_files` (cai na legibilidade T-104),
    **não** quebra.
- **`EvidenceRef`:** `symbol` = caminho da chave (ex.: `rag.alucinacao`); `component_kind="config"`;
  linha best-effort (pode ser `None` — a identidade usa símbolo, não linha — RF-29).
- **Achatamento:** dicts aninhados viram `a.b.c`; listas → `a[0]` ou só a chave-pai (decisão de
  implementação; manter raso para não explodir). Limitar profundidade/qtde para evitar ruído.
- **DoD:** sobre um YAML/JSON de fixture, devolve `ConfigItem`s com símbolo de chave; arquivo malformado
  → `unreadable`, sem exceção.
- **Requisito:** RF-01, RF-12, RF-14, RNF-07.

### T1.2 — Registro por extensão
- **Arquivo:** `extract/registry.py` (`language_for_path`, `get_extractor`).
- **Fazer:** mapear as extensões acima → o `ConfigExtractor`. Manter `.py` → `PythonExtractor`.
- **DoD:** `language_for_path("x.yaml")` resolve para o extrator de config; `.py` inalterado.

### T1.3 — `tsm_builder` roteia config para o extrator (não best-effort)
- **Arquivo:** `extract/tsm_builder.py`.
- **Fazer:** com o registro de T1.2, os arquivos de config caem em `by_lang` (extrator dedicado),
  não em `best_effort`. Conferir que `coverage.sampled` deixa de recebê-los.
- **DoD:** TSM de um projeto com `*.yaml` → `coverage.sampled` vazio por causa de config; os
  `ConfigItem`s aparecem no TSM.

### T1.4 — Cobertura/parcial deixa de disparar por config
- **Efeito:** `make_build_report_node` calcula `partial` de `coverage.sampled` — que agora não
  contém os configs → **laudo deixa de ser PARCIAL** por um YAML.
- **DoD (dogfood):** `avalia src/avalia` não vem mais PARCIAL por `weight_profiles.yaml`.

### T1.5 — Testes
- `tests/extract/test_config_extractor.py`: YAML/JSON/TOML/INI/.env → `ConfigItem`s; malformado →
  `unreadable`. Fixture com config → `coverage` não amostra config.
- **Não esquecer:** `pyproject.toml` `extend-exclude=["tests/fixtures"]` já isenta fixtures do ruff.

---

## 4. Frente 2 — Exibir *prontidão estática* (teto 90) — *decisão 2*

**Objetivo:** comunicar honestamente que a Fase 1 mede **prontidão estática**, cujo teto é ~90;
100 só com a Fase 2. **Não muda o cálculo nem as faixas/veredito** (zero ripple no aceite).

### T2.1 — Constante do teto estático (config, RNF-06)
- **Onde:** definir `STATIC_READINESS_CEILING = 90` (nominal). Tê-la como **dado** (config), não
  constante espalhada — ex.: campo em `EvaluatorConfig` (`static_ceiling: int = 90`) ou módulo de
  constantes do domínio. (90 = `evaluators/base._BASE_SCORE`; a trajetória usa 85, então o teto do
  **agregado** é ~90 conforme os pesos — exibir como "≈ 90".)

### T2.2 — Expor no contrato do laudo (projeção máquina)
- **Arquivo:** `domain/contracts.py` (`ReportMetadata` ou `ReportHeader`).
- **Fazer:** adicionar `static_ceiling: int = 90` (aditivo, default — **não** quebra contratos
  existentes). Preenchido em `report/build.py`.
- **DoD:** `laudo.json` traz `static_ceiling`.

### T2.3 — Render honesto (Markdown + CLI)
- **Arquivos:** `report/render.py`, `cli.py` (`_summary`).
- **Fazer (recomendado):** manter o número interno 0–100 e o **veredito/faixas inalterados**, mas
  rotular e anotar o teto. Ex. no Markdown:
  > **Prontidão estática (Fase 1):** 83/100 — teto da análise estática ≈ **90**; a faixa 90–100 só é
  > atingível com avaliação dinâmica (Fase 2). *Não é "reprovado em 17 pontos": ~7 pontos são headroom
  > reservado à Fase 2.*
- No resumo da CLI, idem (linha curta: `Prontidão estática: 83/100 (teto Fase 1 ~90; 90-100 = Fase 2)`).
- **Alternativa** (se o dono preferir denominador literal): exibir `83/90`. **Risco:** vira ~92% e
  pode recriar a ilusão de "quase perfeito"; por isso a recomendação é manter `/100` + anotar o teto.
  Deixar a escolha explícita ao implementar.
- **DoD:** o laudo deixa claro que 90 é o teto da Fase 1; nenhum número de cálculo muda; suíte de
  aceite intacta.
- **Requisito:** RNF-04 (separar Fase 1 vs. Fase 2), RNF-08 (transparência), §4.2.6.

### T2.4 — Testes
- `tests/report/`: o render contém a nota de teto estático; `static_ceiling` presente no JSON;
  vereditos/scores inalterados (snapshot dos números atuais).

---

## 5. Frente 3 — Correções de produto (gateway do AVALIA) — *achados do laudo*

Parâmetros são **config** (RNF-06); acesso a modelo só via `ModelGateway` (RNF-12).

### T3.1 — `max_tokens` (Custo) e `timeout` (Performance)
- **Arquivos:** `config/evaluator_config.py` (`ModelRef`: `max_tokens: int|None=1024`,
  `timeout_s: float|None=60.0`, ambos `gt=0`), `model_gateway/gateway.py` (`_default_ref` lê de env
  `AVALIA_DEFAULT_MAX_TOKENS`/`AVALIA_DEFAULT_TIMEOUT`; `_default_client_factory` inclui em `params`).
- **DoD:** chamadas de juiz passam `max_tokens`/`timeout`; teste do gateway cobre. Achado some
  **só após T4.2** (ver acoplamento).
- **Requisito:** RF-DIM-C2, RF-DIM-P2, RNF-06.

### T3.2 — Cache de chamadas de juiz (Custo, sugestão — opcional)
- Prompt caching (cache_control) ou memoização por `(rubric_id, conteúdo)`. Baixa prioridade.

> **⚠ Acoplamento T3↔T4:** o gateway usa `ChatAnthropic(**params)` (dict desempacotado — estabiliza o
> mypy entre versões). Como os kwargs vêm de dict, o extrator atual (que procura `kw.arg=="max_tokens"`
> em chamadas) **não enxerga** esses parâmetros mesmo após T3.1. Por isso o achado só zera quando o
> **detector aprende a ler chave de dict / campo de config** (T4.2).

---

## 6. Frente 4 — Correções de motor (analisador) — *pontos-cegos do laudo*

Melhorias **gerais** (qualquer alvo), cada heurística com **evidência (símbolo)** e **fixtures
positiva + negativa** (evitar falso negativo).

### T4.1 — Detectar retry/fallback **imperativos** (Robustez) — *maior valor*
- **Arquivo:** `extract/python_extractor.py` (+ `domain/tsm.py` se preciso).
- **retry:** além de `@retry`, detectar laço de tentativas (`for _ in range(... 'attempt'/'retry'/
  'max_attempts' ...)`, `while` com contador, `try/except` com `continue` em loop) → `ErrorHandling(kind="retry")`.
- **fallback de modelo:** detectar iteração por papéis/modelos (`for role in (... PRIMARY ..., ...
  FALLBACK ...)`, `ModelRole.FALLBACK`, nomes com `fallback`) além de `with_fallbacks`/`fallback=`
  → `ErrorHandling(kind="fallback_modelo")`.
- **DoD:** fixture com retry/fallback imperativos → Robustez **sem** `SEM_RETRY`/`SEM_FALLBACK_MODELO`;
  fixture sem eles **continua** acusando. No dogfood, esses 2 achados somem.
- **Requisito:** RF-DIM-R2, RNF-12; melhora MS-05.

### T4.2 — Detectar `max_tokens`/`timeout` via dict/config (fecha o acoplamento com T3.1)
- **Fazer:** reconhecer `max_tokens`/`timeout` como **chave de dict** (`{"max_tokens": ...}`) e como
  campo de config conhecido, não só kwarg literal de chamada.
- **DoD:** após T3.1+T4.2, o dogfood não acusa `sem_limite_tokens`/`sem_timeout`.

### T4.3 — Classificador robusto a meta-vocabulário (tipo) — corrige `tipo=rag`
- **Arquivo:** `classify.py` (`_infer_type`).
- **Fazer:** exigir **≥2 sinais** de RAG **ou** estrutura de recuperação (nó/ferramenta/aresta
  `retriev*`/`vector*`/`index*`), em vez de **1 keyword** em prompt; priorizar sinais **estruturais**;
  expor confiança da inferência (vocabulário-só → baixa → `select_weights` cai para **neutro**).
- **DoD:** AVALIA-self → tipo `None`/neutro (não `rag`); fixtures RAG **estruturais** continuam `rag`.
  Ajustar a fixture de CA-03 se ela dependia só de vocabulário.
- **Requisito:** RF-06, RF-08/RNF-09, MS-09.

### T4.4 — Calibrar confiança do parcial (menos brusca)
- **Arquivo:** `report/build.py` (`_apply_partial_confidence`).
- **Fazer:** hoje rebaixa **todas** as dimensões um nível. Rebaixar só as dimensões cujas evidências
  caem em arquivos **amostrados**, ou só quando a fração amostrada é significativa (limiar
  configurável — RNF-06). (Com a Frente 1, o parcial fica raro; isto cobre amostragem **real** de
  repositórios grandes — CA-13/CB-05 continuam válidos.)
- **DoD:** amostragem de 1 arquivo secundário não derruba a confiança de dimensões não afetadas.

### T4.5 — Detectar harness por config de teste + orientação de uso (Qualidade)
- **Fazer:** além de `test_*`, reconhecer harness por `pyproject.toml [tool.pytest]`, `tox.ini`,
  `conftest.py`, `.github/workflows` com `pytest`. (Sinergia com a Frente 1: os configs já estarão
  parseados.)
- **Uso:** documentar no README que, para um laudo representativo, aponte para a **raiz do repo**
  (inclui `tests/`), não só `src/`. No dogfood: `avalia .` em vez de `avalia src/avalia`.
- **Requisito:** RF-DIM-Q1.

---

## 7. Ordem sugerida (marcos)

1. **M1 — Parser multi-formato (Frente 1):** T1.1→T1.5. Sozinho já tira o laudo parcial espúrio e
   restaura a confiança das dimensões não-comportamentais.
2. **M2 — Prontidão estática (Frente 2):** T2.1→T2.4. Render honesto, sem mexer no cálculo.
3. **M3 — Motor (Frente 4):** T4.1, T4.2, T4.3, T4.4, T4.5. Zera falsos positivos e corrige tipo.
4. **M4 — Produto (Frente 3):** T3.1 (T3.2 opcional). Depende de T4.2 para o achado zerar.

Após M1–M4, re-rodar o dogfood **na raiz do repo**.

## 8. Critério de aceite (re-run do dogfood)

```bash
PYTHONPATH=src py -m avalia . --target-id avalia-self --out .avalia-self
```
**Esperado:**
- **Não-parcial** (configs analisados; sem amostragem espúria).
- **Tipo** neutro/None (não `rag`); perfil de pesos `fallback_neutro`.
- **Robustez** sem `sem_retry`/`sem_fallback_modelo`; **Custo/Performance** sem
  `sem_limite_tokens`/`sem_timeout`; **Qualidade** com harness presente (escopo inclui `tests/`).
- **Confiança** das dimensões determinísticas → *alto*; comportamentais → *médio* com `--llm`
  (sem `--llm`, permanecem reduzidas por design — RF-13; **não forçar**).
- **Score** ~88–90, exibido como **Prontidão estática (Fase 1), teto ≈ 90** — sem alegar 100.
- Gates de sempre verdes (`ruff`/`format`/`mypy`/`pytest`/guarda RNF-05) + **CI verde**; **suíte de
  aceite inteira intacta** (nenhuma mudança de cálculo/faixa).

## 9. Rastreabilidade e flags

- **Novas tarefas** (estendem `tasks.md` — propor T-IDs ao abrir): T1.* (RF-01/12/14, RNF-07);
  T2.* (RNF-04/08, §4.2.6); T3.* (RF-DIM-C2/P2, RNF-06); T4.* (RF-DIM-R2/RNF-12, RF-06/08, MS-09,
  RF-DIM-Q1).
- **Sem itens "⚠ PARE-E-CONFIRME":** nenhuma mudança de semântica de pontuação (o teto continua 90; só
  passa a ser **exibido**). A escala §4.2.6 (0–100, faixas 49/74) permanece intacta.
- **Invariantes preservados:** nada executa o alvo (RNF-05); modelo só via `ModelGateway`
  (RNF-06/12); achados com `FindingType` da taxonomia + evidência por símbolo (regra 4/5).

## 10. Riscos

| Risco | Mitigação |
|---|---|
| `ConfigExtractor` adiciona **ruído** (lock files, package.json gigante) | limitar extensões/profundidade; pular arquivos grandes (loader já corta >512KB); não achatar listas profundas |
| T4.1 gera **falsos positivos** de retry/fallback (alvo que só importa os nomes) | exigir padrão estrutural (laço/role) + evidência; fixtures positiva e negativa |
| T4.3 **deixa de classificar RAG real** | exigir ≥2 sinais OU estrutura de recuperação; manter fixture RAG estrutural |
| Exibição `/90` recria ilusão de "quase perfeito" | recomendação: manter `/100` + anotar teto 90 (não rescalonar o denominador) |
| Config malformado quebra a ingestão | parse em try/except → `unreadable` (T-104), nunca exceção |

---

*Fim do plano. M1 (parser) sozinho já corrige o "parcial/baixo"; M2 torna o teto honesto; M3/M4
zeram os achados de motor/produto. Nada toca o cálculo nem a suíte de aceite — pronto para
implementar incrementalmente, um marco por PR.*
