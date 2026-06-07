# AVALIA — Plano Técnico (Fase PLAN)

**Versão:** 1.3  
**Data:** 2026-05-31  
**Fonte da verdade:** [spec.md](spec.md) v0.2 (Registro de Decisões EC-01 a EC-10 — imutável nesta fase)  
**Escopo de implementação:** Fase 1 (avaliação estática) completa; Fase 2 apenas como pontos de extensão.  
**Decisões técnicas em aberto:** RESOLVIDAS (#1 Python-first plugável · #2 juízes Opus + LangChain structured output, sem PydanticAI · #3 Postgres+JSONB reusando PostgresSaver, identidade de achado por chave composta com taxonomia controlada · #4 divergência por faixas qualitativas, configurável · #5 HITL via CLI atrás de ApprovalProvider). Registro completo em [tasks.md](tasks.md) §0. Sem conflito com a Spec.

> Convenção de rastreabilidade: cada decisão referencia entre parênteses os requisitos que a justificam. A Seção 10 fecha a matriz requisito → componente. Itens não decidíveis sem o usuário estão marcados `[DECISÃO TÉCNICA EM ABERTO]` e consolidados na Seção 11.

---

## 1. Visão Geral da Arquitetura

O AVALIA é um **grafo de avaliação** (LangGraph `StateGraph`) que recebe um pacote de artefatos do sistema-alvo, constrói uma representação estática indexada desse artefato, classifica o alvo, avalia sete dimensões em paralelo combinando checagens determinísticas e juízes-LLM, agrega com pesos configuráveis, resolve divergências (com escalonamento humano só quando necessário) e emite um laudo estruturado e auditável.

Princípio arquitetural central (espelha o princípio norteador da Spec, Seção 1): **a análise nunca executa o alvo (RNF-05, S-04)** — toda inferência vem de leitura estática de artefatos. O grafo decide automaticamente e só interrompe para humano em divergência irresolúvel (RF-24).

### 1.1 Diagrama textual do grafo

```
                         ┌─────────────────────────┐
            entrada ───► │ N0. ingest_validate     │  RF-01, RF-02, RF-03
                         └───────────┬─────────────┘
                          falha obrigatório │ (RF-02)
                          ┌────────────────┘└───────────────┐
                          ▼                                  ▼
                  ┌──────────────┐                 ┌───────────────────────┐
                  │ ERRO sem     │                 │ N1. index_artifact    │  RF-12, RF-14, RNF-07
                  │ laudo (CA-01)│                 │ (parse + priorização) │
                  └──────────────┘                 └───────────┬───────────┘
                                                               ▼
                                                  ┌───────────────────────┐
                                                  │ N2. classify_target   │  RF-04..08 (1ª classe)
                                                  │ topologia+tipo+conf.   │
                                                  └───────────┬───────────┘
                                                              ▼
                                                  ┌───────────────────────┐
                                                  │ N3. select_weights     │  RF-16, RF-17, RF-21
                                                  │ perfil + aplicabilidade│
                                                  └───────────┬───────────┘
                                                              ▼
                          ╔═══════════════ FAN-OUT paralelo (RF-DIM-P1 espelhado) ═══════════════╗
                          ▼          ▼          ▼          ▼          ▼          ▼          ▼
                       D-Custo   D-Perf    D-Qualid.  D-Assert.  D-Alucin.  D-Trajet.  D-Robustez
                       RF-DIM-C* RF-DIM-P* RF-DIM-Q*  RF-DIM-A*  RF-DIM-H*  RF-DIM-T*  RF-DIM-R*
                       (cada dimensão = checks determinísticos + juiz-LLM)  RF-09..14
                          ╚════════════════════════════ FAN-IN (reducer) ═══════════════════════╝
                                                              ▼
                                                  ┌───────────────────────┐
                                                  │ N4. detect_divergence │  RF-20, 4.2.7
                                                  └───────┬───────────────┘
                                       resolvida auto │   │ irresolúvel (RF-24)
                                  ┌───────────────────┘   └──────────────┐
                                  ▼                                       ▼
                       ┌───────────────────┐                  ┌──────────────────────┐
                       │ N5. aggregate     │ ◄── resume ───── │ N4h. human_gate       │ interrupt()
                       │ pesos/veredito    │                  │ (HITL divergência)    │ RF-24, RNF-05
                       │ RF-15..19, RF-22  │                  └──────────────────────┘
                       └─────────┬─────────┘
                                 ▼
                       ┌───────────────────┐
                       │ N6. compare_hist  │  RF-28, RF-29 (condicional: há versão anterior?)
                       └─────────┬─────────┘
                                 ▼
                       ┌───────────────────┐
                       │ N7. build_report  │  RF-25, RF-27, RNF-08, RNF-10
                       └─────────┬─────────┘
                                 ▼
                              laudo (Pydantic + render markdown/JSON)

  Atravessando todos os nós:
   • teto de custo/tempo (RF-12) → curto-circuito p/ N7 com laudo parcial (CA-13)
   • astream_events → progresso por nó (Seção 3.12)
   • checkpointer → suporta interrupt/resume do N4h (Seção 3.8a)
   • [ponto de extensão Fase 2] gate de execução do alvo entre N5 e N7 (Seção 7)
```

---

## 2. Stack e Justificativa (validada contra requisitos)

| Item da stack | Veredito | Justificativa rastreada | Ressalva / alternativa |
|---|---|---|---|
| **LangGraph `StateGraph`** | **Adotado** | Fan-out/fan-in nativo das 7 dimensões (RF-09); `interrupt()`/resume para HITL de divergência (RF-24); state tipado com reducers (Seção 3.3); roteamento condicional para erro/parcial/HITL (RF-02, RF-12, RF-20). | Nenhuma; é o melhor encaixe para um pipeline com paralelismo + HITL + checkpoint. |
| **Pydantic v2** | **Adotado** | Contratos de dados de todo o State e do laudo (Seção 4); structured output dos juízes-LLM garante laudo sempre completo (RF-09, RF-25); validação de config de pesos rejeita entrada inválida (CB-07). | Nenhuma. |
| **Checkpointer: MemorySaver (dev) / PostgresSaver (prod)** | **Adotado** | Necessário para `interrupt`/`resume` do `human_gate` (RF-24); sem ele o HITL perderia o estado da avaliação. | É **checkpoint de execução do grafo**, não armazenamento de laudos — não confundir (Seção 3.8). |
| **Persistência de laudos históricos** | **Adotado, separado** | RF-28/RF-29 e D-02 exigem recuperar laudos de versões anteriores do mesmo alvo. Recomendação: PostgreSQL com colunas relacionais para indexação (target_id, version, created_at) + JSONB para o laudo serializado. | `[DECISÃO TÉCNICA EM ABERTO #3]` Postgres+JSONB vs. document store vs. arquivos versionados. |
| **LangSmith (tracing + datasets)** | **Adotado p/ observabilidade e meta-avaliação** | Tracing de custo/latência por nó (suporte a MS-10, Seção 3.11); datasets de benchmark para concordância com vereditos humanos (MS-04, MS-07, MS-09, D-03). | Não pode ser dependência dura do caminho crítico do laudo (o laudo deve gerar sem LangSmith disponível). Observabilidade é lateral, não bloqueante. |
| **Streaming via `astream_events`** | **Adotado** | Expõe progresso por nó (início/fim, score parcial, custo parcial) — sustenta acompanhamento das US (Seção 3.12). | Nenhuma. |
| **PydanticAI / LangChain para "sub-tarefas determinísticas simples"** | **Reenquadrado** | **Correção conceitual:** sub-tarefas verdadeiramente determinísticas (detectar teto de loop, timeout, mix de modelos) **não usam LLM** — são parsing AST puro (Seção 3.1/3.2), pré-requisito de RNF-01. PydanticAI/LangChain entram apenas como camada de *structured output* dos **juízes-LLM** (checks semânticos), garantindo saída Pydantic validada. | Escolha entre PydanticAI vs. LangChain `with_structured_output` é secundária; ambos servem. `[DECISÃO TÉCNICA EM ABERTO #2]` provedor/modelo do juiz. |
| **Parser estático (novo item necessário)** | **Adicionado** | Nenhum item da stack proposta lê o código do alvo. É preciso um motor de parsing (Seção 3.1). Recomendação: `tree-sitter` (multilíngue, posições precisas para evidência — RF-14/RNF-07) + módulo `ast` nativo para Python first-class. | `[DECISÃO TÉCNICA EM ABERTO #1]` escopo de linguagens first-class. |

**Conclusão de validação da stack:** a stack proposta serve bem orquestração, HITL, contratos e observabilidade, mas **estava incompleta** — faltava o motor de análise estática (o coração da Fase 1) e havia uma imprecisão sobre "sub-tarefas determinísticas com LLM". Ambos corrigidos acima sem inflar escopo.

---

## 3. As 12 Decisões de Arquitetura

### 3.1 Motor de análise estática (decisão central) — RF-03, RF-12, RF-14, RNF-07, CB-02, CB-05

**Abordagem: híbrida em duas camadas, com escopo de linguagem em níveis.**

- **Camada estrutural (determinística):** parsing em árvore sintática para extrair fatos verificáveis com posição exata (arquivo + intervalo de linhas/colunas). Sustenta evidência rastreável (RF-14/RNF-07) e os checks determinísticos (Seção 3.2).
  - **Python — first-class:** `ast` nativo + `tree-sitter-python`. Cobre o grosso do ecossistema multiagente (LangGraph, LangChain, CrewAI, AutoGen).
  - **TypeScript/JavaScript — second-class:** `tree-sitter` (estrutural; sem inferência de tipos). 
  - **Demais linguagens — best-effort:** `tree-sitter` genérico onde houver gramática; senão, fallback textual + juiz-LLM, com confiança reduzida declarada (RNF-08).
- **Camada semântica (juiz-LLM):** lê trechos priorizados (prompts, descrições de ferramentas, lógica de roteamento) e julga o que é qualitativo (clareza de prompt, coerência de roteamento, adequação de guard-rails).
- **Construção de um "modelo do alvo" (Target Static Model — TSM):** produto do nó `index_artifact`. Estrutura normalizada e **agnóstica de linguagem** contendo: inventário de arquivos, nós/agentes detectados, arestas/roteamento, ferramentas, loops, atribuições de modelo, prompts localizados, configs. Cada elemento carrega `EvidenceRef` (arquivo + intervalo). O TSM é a fonte única de fatos para todos os avaliadores → garante consistência e rastreabilidade.
- **Legibilidade (RF-03, CB-02):** se um arquivo não parseia (ofuscado/compilado/encriptado), o TSM o marca `unreadable=true`; dimensões que dependem dele recebem confiança "baixa" automaticamente.
- **Priorização e amostragem (RF-12, CB-05):** o `index_artifact` ranqueia arquivos por **sinal** (heurística: define grafo/orquestração > prompts > ferramentas > config > harness > resto). Acima do teto de custo/tempo, sumariza/amostra o restante e registra `AnalysisCoverage` (integral vs. amostrado) → laudo parcial honesto (CA-13).

`[DECISÃO TÉCNICA EM ABERTO #1]` Escopo de linguagens first-class da Fase 1: (a) só Python first-class + resto best-effort (menor custo, cobre maioria); (b) Python + TS/JS first-class (mais cobertura, ~2x esforço de parsing). Trade-off: cobertura de mercado vs. esforço.

### 3.2 Separação determinístico vs. LLM-judge (sustenta a reprodutibilidade) — RNF-01, RF-26, RF-DIM-*, CA-14

Cada check de dimensão é classificado. **Determinístico** = derivado do TSM por regra pura (idêntico entre execuções). **LLM-judge** = julgamento semântico (reprodutibilidade estatística). **Híbrido** = fato determinístico + apreciação semântica.

| Check (RF-DIM) | Natureza | O que é determinístico | O que é LLM-judge |
|---|---|---|---|
| C1 mix de modelos | Híbrido | mapa nó→modelo (TSM) | adequação "barato no simples, caro só onde precisa" |
| C2 controles de custo | **Determinístico** | presença de teto de loop, limites de tokens, cache, truncamento | — |
| C3 chamadas redundantes | LLM-judge | candidatos por topologia | se há redundância real de propósito |
| P1 paralelização | Híbrido | topologia sequencial vs. fan-out (TSM) | se a serialização é desnecessária |
| P2 streaming/timeouts | **Determinístico** | presença de timeout/streaming nas chamadas | — |
| Q1 maquinaria de verificação | Híbrido | existência de harness/testes | clareza dos prompts, qualidade das rubricas |
| A1 expressão de confiança | LLM-judge | — | prompts pedem confiança? |
| A2 tratamento de baixa confiança | Híbrido | existência de ramo de escalonamento | se trata baixa confiança adequadamente |
| H1 anti-alucinação | LLM-judge | presença de etapa de verificação (parcial) | exigência de citação, grounding, abstenção |
| T1 definições de ferramentas | Híbrido | ferramentas têm descrição/params (TSM) | clareza e sobreposição de domínios |
| T2 roteamento | Híbrido | grafo, caminhos mortos (TSM) | coerência, contradições semânticas |
| T3 loops/passos redundantes | **Determinístico** | todo loop tem teto? nós redundantes? | — |
| R1 tratamento de erro | Híbrido | try/except, propagação (TSM) | se o tratamento é significativo |
| R2 retry/fallback | **Determinístico** | presença de retry/backoff/fallback | — |
| R3 validação/anti-injeção | Híbrido | presença de validação de entrada | adequação dos guard-rails anti-injeção |

**Como o split honra RNF-01/RF-26:** os checks determinísticos rodam sobre o TSM com regra pura → **bit-idênticos** entre execuções (parte determinística de RF-26/CA-14). Os juízes-LLM rodam com `temperature=0` e prompts/rubricas fixas e versionadas → **reprodutibilidade estatística** (veredito e achados críticos estáveis; formulação pode variar). O **veredito por dimensão** é derivado preferencialmente dos sinais determinísticos quando estes são decisivos (ex.: "loop sem teto" é fato, não opinião), reduzindo a variância do juízo final.

**Resiliência operacional do juiz (RNF-12).** O wrapper de juiz (Seção 3.2 / T-302) implementa a política escalonada de fallback de modelo, porque o fan-out de 7 dimensões × painel multiplica as chamadas a modelo e torna falhas transitórias prováveis por run: (1) **retry no mesmo modelo** com backoff para erro transitório — preserva RNF-01; (2) **re-solicitação** para saída estruturada malformada; (3) **fallback para modelo configurado** (T-005) se o primário ficar indisponível, **declarado** nos metadados do laudo com **confiança reduzida** na dimensão (RNF-08/RNF-09) — nunca silencioso, porque trocar o modelo ameaça a reprodutibilidade e isso não pode ser fingido; (4) **laudo parcial** (reusa o curto-circuito de budget, Seção 3.5 / T-802) se o fallback se esgotar. Modelo primário e de fallback são configuráveis por tipo de nó (RNF-06), nunca constantes. **Padrão: Opus → Sonnet.**

  - **3.2b — Abstração `ModelGateway` (acesso a modelo configurável/cross-provider).** Todo acesso a LLM passa por um `ModelGateway` que resolve `(tipo_de_nó, papel: primário|fallback)` → modelo concreto, isolando o resto do código do provedor. Back-ends: **direto Anthropic** (padrão Opus/Sonnet) e **OpenRouter** (base_url compatível com OpenAI, alcance cross-provider — Kimi etc.). O gateway centraliza: seleção primário/fallback, política de retry/backoff, e a **negociação de structured output** (preferir `with_structured_output`; degradar para tool-calling/JSON mode conforme a capacidade do modelo; se incompatível, tratar como saída malformada → passo 2 da RNF-12). Isso mantém a decisão #2 (LangChain structured output) intacta e torna o provedor um detalhe de configuração, não de código. **Ressalva:** a paridade de structured output por modelo de fallback (especialmente cross-provider via OpenRouter) deve ser verificada — daí o `ModelGateway` negociar o modo compatível.

### 3.3 State do grafo (contratos Pydantic) — Seção 4.2, RF-01, RF-04..08, RF-09..14, RF-15..22

`AvaliaState` (campos conceituais; tipos Pydantic v2, reducers indicados):

| Campo | Tipo conceitual | Reducer | Requisito |
|---|---|---|---|
| `submission` | `Submission` (artefato + metadados + config avaliador) | replace | RF-01, 4.1 |
| `component_inventory` | `ComponentInventory` (presentes/ausentes) | replace | RF-01, RF-02 |
| `tsm` | `TargetStaticModel` (fatos + EvidenceRefs + coverage) | replace | RF-12, RF-14 |
| `readability` | `ReadabilityReport` | replace | RF-03, CB-02 |
| `classification` | `TargetClassification` (topologia, tipo, confiança) | replace | RF-04..08 |
| `applicable_dims` | `set[Dimension]` + razões de "não aplicável" | replace | RF-21 |
| `effective_weights` | `WeightProfile` (origem: inferido/sobrescrito) | replace | RF-15..17 |
| `dimension_results` | `list[DimensionResult]` | **`operator.add`** (merge do fan-out) | RF-09..14, fan-in |
| `divergences` | `list[DivergenceRecord]` | `operator.add` | RF-20, 4.2.7 |
| `human_decisions` | `list[HumanDecision]` | `operator.add` | RF-24 |
| `aggregate` | `AggregateScore` (score, veredito, condições) | replace | RF-15..19 |
| `budget` | `BudgetState` (custo/tempo gasto vs. teto) | custom max/add | RF-12 |
| `comparison` | `VersionComparison \| None` | replace | RF-28, RF-29 |
| `report` | `EvaluationReport` | replace | RF-25, Seção 4.2 |
| `status` | enum (`ok`/`partial`/`error`/`awaiting_human`) | replace | RF-02, RF-12, RF-24 |

O reducer `operator.add` nas dimensões é o que permite o fan-out paralelo escrever no mesmo State sem corrida (cada avaliador emite um `DimensionResult`; o framework concatena no fan-in).

### 3.4 Nós e suas funções — RF-01..29

| Nó | Função | Paralelo? | Requisitos |
|---|---|---|---|
| **N0 `ingest_validate`** | Recebe submissão, monta inventário, valida obrigatórios, valida config de pesos | não | RF-01, RF-02, RF-03, CB-07 |
| **N1 `index_artifact`** | Constrói o TSM (parse estrutural + priorização + coverage + legibilidade) | interno pode paralelizar por arquivo | RF-12, RF-14, CB-02, CB-05 |
| **N2 `classify_target`** | Topologia (≥2 sinais), tipo funcional, confiança da classificação | não | RF-04..08, MS-09 |
| **N3 `select_weights`** | Resolve dimensões aplicáveis + perfil de pesos (inferido/fallback/sobrescrito) | não | RF-16, RF-17, RF-21 |
| **N4-Dx (×7) avaliadores de dimensão** | Cada um roda seus checks determinísticos + juiz-LLM; emite `DimensionResult` | **SIM — fan-out** | RF-09..14, RF-DIM-* |
| **N4 `detect_divergence`** (fan-in) | Detecta divergências; dispara re-julgamento automático | não | RF-20 |
| **N4h `human_gate`** | `interrupt()` para decisão humana em divergência irresolúvel | não | RF-24, RNF-05 |
| **N5 `aggregate`** | Pesos→score→veredito→condições de aprovação; exclui baixa confiança | não | RF-15..19, RF-22 |
| **N6 `compare_history`** | Carrega laudo anterior, calcula deltas/regressões | não (condicional) | RF-28, RF-29, CB-06 |
| **N7 `build_report`** | Monta `EvaluationReport` + render; persiste no repositório de laudos | não | RF-25, RF-27, RNF-08, RNF-10 |

Ponto de **fan-out** = saída de N3. Ponto de **fan-in** = entrada de N4 (`detect_divergence` só roda quando todos os 7 `DimensionResult` chegaram).

### 3.5 Roteamento (edges e pontos condicionais) — RF-02, RF-12, RF-20, RF-24, CA-01, CA-13

- `N0 → N1` se obrigatórios presentes e config válida; **`N0 → END(erro)` sem laudo** se faltar obrigatório (RF-02/CA-01) ou config de pesos inválida (CB-07).
- `N1 → N2 → N3 → fan-out(N4-Dx)`.
- `fan-in → N4 detect_divergence`.
- Condicional de divergência: `N4 → N5` se resolvida automaticamente (CA-10); `N4 → N4h → (resume) → N5` se irresolúvel (RF-24/CA-11).
- `N5 → N6` se existe versão anterior; senão `N5 → N7` (CB-06).
- **Curto-circuito de budget (RF-12/CA-13):** uma checagem transversal de `BudgetState` em cada transição; ao estourar o teto, roteia direto para `N7` com `status=partial` e `AnalysisCoverage` declarando o que ficou de fora.
- `N6 → N7 → END`.

### 3.6 Mecanismo de detecção de divergência — RF-20, RF-24, CA-10, CA-11, 4.2.7

- **Geração de múltiplos julgamentos:** cada dimensão comportamental produz julgamento por um **painel de 2–3 juízes com ângulos distintos** (ex.: um "advogado da qualidade", um "cético/red-team", e o fato determinístico como árbitro), em vez de só multi-amostragem do mesmo prompt. Ângulos distintos expõem divergência real, não ruído de amostragem.
- **Limiar de divergência:** divergência sinalizada quando (a) os juízes discordam além de um delta de score configurável **ou** (b) a confiança agregada da dimensão cai abaixo de um piso. `[DECISÃO TÉCNICA EM ABERTO #4]` valores iniciais do delta e do piso (a calibrar — conecta D-04/MS-08).
- **Resolução automática primeiro (RF-20):** re-julgamento com rubrica mais estrita + pedido de reconciliação explícita ("explique a discordância e concilie à luz do fato X do TSM"). Registra `DivergenceRecord{resolvido_por: auto}`.
- **Escalonamento (RF-24):** só se persistir após o re-julgamento → `human_gate` com `interrupt()`, apresentando as posições em conflito. Registra `DivergenceRecord{resolvido_por: humano, decisão}`.
- **Auditabilidade (4.2.7):** todo `DivergenceRecord` entra no laudo, resolvido automaticamente ou não.

### 3.7 Motor de agregação — RF-15..22, CA-03, CA-04, CA-08, CA-09

- **Perfis de peso como DADOS, não código (RNF-06):** arquivo de configuração versionado (ex.: `weight_profiles.yaml`) mapeando `tipo_de_sistema → {dimensão: peso}`. Inclui um perfil `neutro` (pesos iguais). Editar prioridades = editar dados, sem tocar código.
- **Seleção (RF-16):** `select_weights` escolhe o perfil pelo tipo inferido (N2) se a confiança ≥ piso; senão **fallback para `neutro`** (CA-04/CB-09), declarando a razão.
- **Sobrescrita (RF-17):** config explícita do usuário substitui o perfil; o laudo marca `origem=sobrescrito`.
- **Renormalização (RF-21):** dimensões "não aplicáveis" (de N3) são removidas e os pesos restantes renormalizados para somar 1 → sem nota artificialmente baixa (CA-08).
- **Exclusão por confiança (RF-22):** se o usuário configurou piso de confiança, julgamentos abaixo dele saem da agregação, com sinalização no laudo.
- **Faixas e veredito (RF-18, 4.2.6):** 0–49 reprovado / 50–74 aprovação condicional / 75–100 aprovado (limiares configuráveis).
- **Condições de aprovação automáticas (RF-19/CA-09):** na faixa intermediária, deriva condições dos próprios `Finding`s (cada `Finding` crítico/importante vira uma condição acionável, com `traces_to=finding_id`), priorizadas. Geradas pelo AVALIA; usuário não configura.

### 3.8 Persistência — duas preocupações distintas — RF-28, RF-29, D-02, CB-06

**(a) Checkpointer do grafo (execução):** MemorySaver (dev) / PostgresSaver (prod). Existe para **interrupt/resume do HITL** (RF-24) e resiliência da execução. Chave por `thread_id` da avaliação. **Não** é o armazém de laudos.

**(b) Repositório de laudos históricos (produto):** armazena cada `EvaluationReport` finalizado para comparação entre versões (RF-28/RF-29). Modelo de dados:

```
EvaluationReportRecord
  ├─ report_id        (PK, único da avaliação)
  ├─ target_id        (metadado de identidade do alvo — vincula versões; RF-28)
  ├─ target_version   (versão/tag avaliada)
  ├─ created_at
  ├─ aggregate_verdict / aggregate_score
  ├─ report_json      (EvaluationReport serializado — JSONB)
  └─ findings_index   (achados normalizados p/ diff de regressão; RF-29)
```

Versões do mesmo alvo são vinculadas por `target_id` (fornecido pelos metadados — S-02). `compare_history` busca o laudo anterior mais recente por `target_id` e calcula deltas; se não houver, CB-06 (segue sem comparação). `findings_index` permite classificar achados em resolvido/persistente/novo por identidade estável do achado (ex.: hash de `tipo+localização`).

`[DECISÃO TÉCNICA EM ABERTO #3]` tecnologia do repositório (Postgres+JSONB recomendado vs. document store vs. arquivos versionados) e esquema de identidade estável de achado para o diff.

### 3.9 Aprovação humana na Fase 1 — RF-23, RF-24, RNF-05, RNF-11

- **Único gatilho de HITL na Fase 1 = divergência irresolúvel (RF-24)**, implementado com `interrupt()` no `human_gate`, retomado via checkpointer (Seção 3.8a). Baixa fricção (RNF-11): no caminho feliz, **zero** intervenção humana — classificação, perfil e condições são automáticos.
- **RF-23 (nenhuma execução do alvo sem aprovação) na Fase 1:** trivialmente satisfeito porque a Fase 1 **nunca executa o alvo** (S-04). O gate de execução é modelado como **ponto de extensão** (Seção 7), não construído agora. Não superdimensionar (instrução de escopo).
- O laudo registra toda `HumanDecision` com o desfecho (auditabilidade — RNF-10). `[DECISÃO TÉCNICA EM ABERTO #5]` canal de aprovação humana (CLI interativa, API com callback, UI) — afeta como o `interrupt` é exposto.

### 3.10 Saída e auditabilidade — Seção 4.2 inteira, RNF-07, RNF-08, RNF-10

- **Laudo como objeto Pydantic `EvaluationReport`** (Seção 4) — fonte canônica; **renderizações derivadas** em Markdown (humano) e JSON (máquina). A estrutura Pydantic garante que todos os blocos 4.2.1–4.2.8 estejam presentes (RF-25).
- **Evidência rastreável (RNF-07):** cada `Finding` carrega `EvidenceRef[]` (arquivo + intervalo + trecho), herdado do TSM.
- **Declaração ativa de limitações (RNF-08):** o laudo inclui `AnalysisCoverage`, componentes ausentes, legibilidade comprometida e incerteza de classificação como seções de primeira ordem.
- **Autocontido para auditor externo (RNF-10):** o laudo embute evidências, raciocínio, registro de divergências e config efetiva — um auditor reproduz o raciocínio só com o laudo + artefato, sem estado interno do AVALIA.

### 3.11 Observabilidade e meta-avaliação — MS-04..10, D-03, D-04

- **Tracing (LangSmith):** cada nó emite span com custo/tokens/latência → alimenta MS-10 (evolução) e dá visibilidade de gargalos. **Não bloqueante:** o laudo gera mesmo sem LangSmith.
- **Subsistema de meta-avaliação (arquitetado agora, construído depois):** um **dataset de benchmark** (D-03) de sistemas-alvo com **veredito humano de referência por dimensão**. A métrica primária é **concordância de veredito por dimensão** (aprovado/ressalva/reprovado) — EC-10/MS-04 — calculada comparando o laudo do AVALIA ao rótulo humano. MS-09 mede a concordância da **classificação** (topologia/tipo). MS-08 valida que confiança "alta" concorda mais que "baixa".
- **Limiar de "confiável":** não fixado (EC-10); calibrado após o primeiro lote (D-04). O plano prevê a *infraestrutura de medição*, não um número.
- **Arquitetura:** o `EvaluationReport` já expõe veredito por dimensão e confiança em formato comparável ao rótulo humano → meta-avaliação é um job offline sobre o repositório de laudos + dataset, sem alterar o grafo.

### 3.12 Streaming — suporte às US de acompanhamento

- `astream_events` emite eventos por nó: `on_node_start/end`, score parcial de dimensão ao concluir cada avaliador do fan-out, custo parcial acumulado do `BudgetState`. Consumidores reativos (CLI/UI) mostram progresso dimensão a dimensão (sustenta US-02, US-06, US-09 quanto a visibilidade do andamento). Não altera contratos; é projeção do State.

---

## 4. Modelo de Dados (contratos Pydantic principais)

Contratos conceituais (campos + tipos; sem implementação). Todos Pydantic v2.

```
Enums:
  Dimension      = {custo, performance, qualidade, assertividade, alucinacao, trajetoria, robustez}
  Confidence     = {alto, medio, baixo}
  Topology       = {multiagente, agente_unico_borderline}
  Verdict        = {aprovado, aprovacao_condicional, reprovado}
  Urgency        = {critico, importante, sugestao}
  CheckNature    = {deterministico, llm_judge, hibrido}

EvidenceRef          { file_path; line_start; line_end; snippet; component_kind }   # RNF-07, RF-14
ComponentInventory   { present: list[str]; missing: list[str] }                     # RF-01, RF-02
ReadabilityReport    { unreadable_files: list[EvidenceRef]; impacted_dims }         # RF-03, CB-02
AnalysisCoverage     { fully_analyzed: list[str]; sampled: list[str]; reason }      # RF-12, CB-05

TargetStaticModel    { files; agents; edges; tools; loops; model_assignments;       # núcleo factual
                       prompts; configs; coverage: AnalysisCoverage;
                       readability: ReadabilityReport }                             # RF-12, RF-14

TargetClassification { topology: Topology; topology_signals: list[str];             # RF-04, RF-05
                       system_type: str|None; classification_conf: Confidence;
                       caveats: list[str] }                                         # RF-06, RF-07, RF-08

WeightProfile        { source: {inferido|fallback_neutro|sobrescrito};              # RF-16, RF-17
                       weights: dict[Dimension,float]; normalized: bool }           # RF-21

CheckOutcome         { check_id; nature: CheckNature; passed|score_signal;          # Seção 3.2
                       evidence: list[EvidenceRef]; deterministic_hash? }           # RNF-01

JudgeOpinion         { angle; score; reasoning; confidence; evidence }              # RF-10, RF-20

Finding              { id; dimension; urgency: Urgency; positive: bool;             # RF-09, RF-14
                       statement; reasoning; evidence: list[EvidenceRef] }          # RNF-02, RNF-07

DimensionResult      { dimension; applicable: bool; score: int|None;                # RF-09, RF-21
                       confidence: Confidence; confidence_reason?;                  # RF-11
                       reasoning: str; findings: list[Finding];                     # RF-10, RNF-02
                       recommendations: list[Recommendation];
                       static_limitations: str?;        # RF-13 p/ comportamentais
                       check_outcomes; judge_opinions }                            # 3.2, 3.6

DivergenceRecord     { dimension; conflicting_positions; threshold_hit;             # RF-20, 4.2.7
                       resolved_by: {auto|humano}; resolution_note }                # RF-24

AggregateScore       { score: int; verdict: Verdict;                                # RF-15, RF-18
                       excluded_low_conf: list[Dimension];                          # RF-22
                       approval_conditions: list[ApprovalCondition] }               # RF-19

ApprovalCondition    { statement; urgency; traces_to: finding_id }                  # RF-19, CA-09

VersionComparison    { prev_report_id; deltas: dict[Dimension,int];                 # RF-29
                       regressions; improvements;
                       resolved/persistent/new findings }                          # RF-29, CB-06

EvaluationReport     { header: ReportHeader;          # 4.2.1 (classificação, perfil, veredito, conf.)
                       dimensions: list[DimensionResult];                           # 4.2.2
                       consolidated_recommendations;                                # 4.2.3, RF-27
                       approval_conditions;                                         # 4.2.4
                       comparison: VersionComparison?;                              # 4.2.5
                       divergences: list[DivergenceRecord];                         # 4.2.7
                       metadata: { effective_config; inventory; coverage;           # 4.2.8
                                   known_limitations } }                            # RNF-08, RNF-10
```

`Submission` (entrada) e `EvaluatorConfig` (pesos opcionais, limiares, teto de custo/tempo) completam o contrato de entrada (4.1). `EvaluatorConfig` valida pesos na ingestão (CB-07).

---

## 5. Desenho do Grafo (nós, edges, paralelismo, HITL)

- **Topologia:** linear até N3, **fan-out de 7 ramos** (um por dimensão) a partir de N3, **fan-in** em N4. Os 7 avaliadores são independentes e leem o **mesmo TSM imutável** → paralelizáveis sem corrida; escrevem via reducer `operator.add` em `dimension_results`.
- **Pontos condicionais:** (i) N0 erro vs. seguir; (ii) N4 auto-resolvido vs. `human_gate`; (iii) N5→N6 vs. N5→N7 (há histórico?); (iv) curto-circuito de budget para N7.
- **HITL:** `human_gate` usa `interrupt()`; a execução suspende e o checkpointer preserva o State; ao receber a decisão humana, retoma em N5. É o **único** ponto de pausa humana na Fase 1.
- **Determinismo de ordem:** o fan-in agrega resultados de forma **ordenada por `Dimension`** antes da agregação, para que a saída não dependa da ordem de chegada dos ramos (apoia RNF-01).

---

## 6. Estratégia de Reprodutibilidade (split determinístico vs. LLM) — RNF-01, RF-26, CA-14

1. **Camada determinística idêntica:** todo `CheckOutcome` determinístico carrega um `deterministic_hash` derivado do TSM; duas execuções sobre o mesmo artefato produzem hashes iguais → checks estáticos **bit-idênticos** (parte determinística de CA-14).
2. **Camada LLM estatística:** juízes com `temperature=0`, **prompts e rubricas versionados** (id de versão da rubrica no laudo), e ordenação estável das opiniões. Garante veredito por dimensão e achados críticos estáveis; tolera variação de formulação (RF-26/RNF-01).
3. **Ancoragem do veredito em fato:** quando um sinal determinístico é decisivo (ex.: loop sem teto), o veredito da dimensão é governado pelo fato, não pelo juízo — minimizando variância onde mais importa.
4. **Teste de reprodutibilidade (CA-14):** executar o mesmo artefato N vezes e asserir: hashes determinísticos idênticos; vereditos por dimensão idênticos; conjunto de achados críticos idêntico (Seção 8).

---

## 7. Pontos de Extensão para a Fase 2 (sem implementação) — S-05, D-01, RF-23, O7..O9

Projetados como **interfaces vazias/ganchos**, não construídos (evita superdimensionar):

1. **Gate de execução do alvo (RF-23):** posição reservada no grafo entre N5 e N7 (`execution_gate`), que na Fase 2 fará `interrupt()` de aprovação **antes** de qualquer execução. Na Fase 1 é um no-op ausente do grafo, mas o roteamento e o State (`status=awaiting_human`) já comportam o padrão de interrupt (reuso do mecanismo de Seção 3.9).
2. **Runner isolado do alvo (D-01):** contrato `TargetRunner` (porta) declarado, sem implementação — a Fase 2 pluga um runner sandboxed. A Fase 1 não o referencia.
3. **Gerador autônomo de casos de teste (O8):** gancho `TestCaseGenerator` que consumirá o TSM (já disponível) para gerar casos — o TSM da Fase 1 é reaproveitado, evitando retrabalho.
4. **Captura de traces (O9):** o State já tem `dimension_results` e o laudo já separa "presença de mecanismo" (Fase 1) de "comportamento medido" (Fase 2) — campos dinâmicos entram como extensão de `DimensionResult` (ex.: `dynamic_metrics?`), sem quebrar contratos.

Nenhum desses executa o alvo na Fase 1 (RNF-05/S-04). O design garante **não-bloqueio** sem custo de construção agora.

---

## 8. Estratégia de Testes (como cada CA-xx e CB-xx é verificável)

Todos os testes operam sobre **fixtures de artefatos estáticos** (mini sistemas-alvo sintéticos). **Nenhum teste executa o alvo** (RNF-05/S-04).

| Caso | Estratégia de verificação |
|---|---|
| CA-01 / CB-07 | Fixture sem código-fonte / com pesos inválidos → assert `status=error`, sem `EvaluationReport`, mensagem cita componente/erro. |
| CA-02 / CB-03 | Fixture de agente único → assert `topology=agente_unico_borderline`, confiança presente, laudo gerado, dims inaplicáveis marcadas. |
| CA-03 | Fixture tipo RAG (alta confiança) → assert perfil `RAG` e peso de `alucinacao` > neutro. |
| CA-04 / CB-09 | Fixture ambíguo → assert `source=fallback_neutro` + razão declarada. |
| CA-05 / RNF-02 | Qualquer laudo → assert cada `DimensionResult.reasoning` não vazio. |
| CA-06 | Fixture sem harness → assert dimensão Qualidade `confidence=baixo` + razão sobre harness. |
| CA-07 / RF-13 | Qualquer laudo → assert `static_limitations` presente em alucinação/qualidade/assertividade. |
| CA-08 / RF-21 | Fixture agente único → assert dimensão inaplicável excluída e pesos renormalizados (soma=1). |
| CA-09 / RF-19 | Fixture na faixa 50–74 com loop sem teto → assert condição "adicionar teto..." com `traces_to`. |
| CA-10 | Fixture que induz divergência reconciliável → assert `DivergenceRecord.resolved_by=auto`, sem HITL. |
| CA-11 | Fixture de divergência persistente → assert dispara `human_gate`/`interrupt`; após decisão mock, `resolved_by=humano`. |
| CA-12 (Fase 2) | Verificável só quando o `execution_gate` existir; na Fase 1, **teste negativo**: assert que nenhum caminho do grafo invoca execução do alvo (RNF-05). |
| CA-13 / RF-12 | Fixture grande + teto baixo → assert `status=partial`, `AnalysisCoverage` preenchido, confiança reduzida. |
| CA-14 / RNF-01 | Mesmo fixture ×N → assert hashes determinísticos idênticos, vereditos por dimensão idênticos, achados críticos idênticos. |
| CA-15 / RF-29 | Dois laudos (v1,v2) no repositório → assert listas de regressão/melhoria/achados resolvidos. |
| CB-01 | Fixture sem harness/instrumentação → assert prossegue + confiança reduzida + componentes ausentes no laudo. |
| CB-02 | Fixture com arquivo ofuscado → assert `unreadable`, dims impactadas `baixo`. |
| CB-04 | Coberto por CA-10/CA-11. |
| CB-05 | Coberto por CA-13. |
| CB-06 | Comparação sem histórico → assert laudo normal + nota "sem histórico", sem `VersionComparison`. |
| CB-08 | Fixture com config↔código contraditórios → assert `Finding` de contradição + confiança reduzida. |

**Camadas de teste:** (a) unidade nos checks determinísticos (TSM→CheckOutcome); (b) contrato Pydantic (laudo sempre completo); (c) integração de grafo por fixture (acima); (d) reprodutibilidade (CA-14); (e) meta-avaliação offline contra dataset de benchmark (MS-04/MS-09), fora do CI crítico.

---

## 9. Riscos Técnicos e Mitigações

| # | Risco | Impacto | Mitigação |
|---|---|---|---|
| R1 | **Cobertura de linguagem** do parser estático insuficiente para alvos reais | Evidência fraca, confiança baixa generalizada | Python first-class + tree-sitter multilíngue + fallback LLM com confiança declarada (3.1); decidir escopo (Aberto #1) |
| R2 | **Variância dos juízes-LLM** ameaça RNF-01 | Vereditos instáveis | Ancorar veredito em fato determinístico; temp=0; rubricas versionadas; painel com árbitro factual (3.2/3.6) |
| R3 | **Custo/latência** do fan-out de 7 dimensões × painel de juízes | Estouro de budget frequente | Checks determinísticos primeiro (baratos); juiz-LLM só no semântico; teto de custo/tempo com laudo parcial (RF-12); cache de prompts |
| R4 | **Identidade estável de achado** para diff de regressão | Comparação de versões ruidosa (RF-29) | Hash de `tipo+localização normalizada`; Aberto #3 |
| R5 | **Heurística de classificação** erra topologia/tipo | Perfil de pesos e aplicabilidade errados a jusante | Confiança reportada (RF-05); fallback neutro; meta-avaliação MS-09; sobrescrita do usuário (RF-17) |
| R6 | **Falsa sensação de avaliação comportamental** na Fase 1 | Usuário superinterpreta o laudo | `static_limitations` obrigatório (RF-13/RNF-04) em toda dimensão comportamental |
| R7 | **LangSmith como dependência dura** | Laudo não gera se observabilidade cai | Observabilidade desacoplada do caminho crítico (3.11) |
| R8 | **Injeção de prompt via artefato do alvo** (prompts maliciosos lidos pelo juiz) | Juiz manipulado | Tratar conteúdo do alvo como *dado não confiável*; sandbox de prompt (delimitação/escape) nos juízes; `[risco a endereçar no TASK]` |
| R9 | **Indisponibilidade/falha do modelo de julgamento** (outage, rate limit, output malformado) no fan-out de N chamadas | Avaliação aborta por falha pontual | Política escalonada RNF-12 (retry mesmo modelo → re-prompt → fallback declarado c/ confiança reduzida → laudo parcial); modelo primário+fallback configuráveis por nó (3.2, T-005/T-302/T-802) |

---

## 10. Matriz de Rastreabilidade (requisito → componente)

| Requisito | Componente/Decisão que satisfaz |
|---|---|
| RF-01 | N0 `ingest_validate` + `ComponentInventory` (3.4, 4) |
| RF-02 | N0 validação obrigatórios + edge erro sem laudo (3.5) |
| RF-03 | N1 legibilidade + `ReadabilityReport` (3.1) |
| RF-04 | N2 `classify_target` topologia ≥2 sinais (3.4) |
| RF-05 | `TargetClassification.classification_conf` (3.3, 4) |
| RF-06 | N2 inferência de tipo + fallback (3.7) |
| RF-07 | `caveats` no laudo (3.7, 4) |
| RF-08 | Classificação a partir do TSM, não de metadados (3.1, RNF-09) |
| RF-09 | N4-Dx avaliadores + `DimensionResult` completo (3.4) |
| RF-10 | `reasoning` obrigatório; structured output (3.10, 4) |
| RF-11 | `confidence`/`confidence_reason` em `DimensionResult` (4) |
| RF-12 | N1 priorização + `AnalysisCoverage` + curto-circuito budget (3.1, 3.5) |
| RF-13 | `static_limitations` nas dims comportamentais (3.2, 4) |
| RF-14 | `EvidenceRef` herdado do TSM (3.1) |
| RF-15 | N5 `aggregate` ponderado (3.7) |
| RF-16 | `select_weights` perfil+fallback (3.7) |
| RF-17 | `WeightProfile.source=sobrescrito` (3.7) |
| RF-18 | Mapeamento de faixas/veredito (3.7) |
| RF-19 | `ApprovalCondition` derivada de findings (3.7) |
| RF-20 | `detect_divergence` + re-julgamento (3.6) |
| RF-21 | `applicable_dims` + renormalização (3.7) |
| RF-22 | Exclusão por piso de confiança (3.7) |
| RF-23 | Fase 1 não executa (S-04) + `execution_gate` como extensão (7) |
| RF-24 | `human_gate` com `interrupt()` (3.9) |
| RF-25 | N7 `build_report` + `EvaluationReport` (3.10) |
| RF-26 | Estratégia de reprodutibilidade (6) |
| RF-27 | Recomendações consolidadas/priorizadas (3.10, 4) |
| RF-28 | Repositório de laudos por `target_id` (3.8b) |
| RF-29 | `compare_history` + `findings_index` (3.8b) |
| RF-DIM-C1/C2/C3 | Avaliador Custo (tabela 3.2) |
| RF-DIM-P1/P2 | Avaliador Performance (3.2) |
| RF-DIM-Q1/Q2 | Avaliador Qualidade (3.2) + RF-13 |
| RF-DIM-A1/A2 | Avaliador Assertividade (3.2) |
| RF-DIM-H1/H2 | Avaliador Alucinação (3.2) + RF-13 |
| RF-DIM-T1/T2/T3 | Avaliador Trajetória (3.2) |
| RF-DIM-R1/R2/R3 | Avaliador Robustez (3.2) |
| RNF-01 | Split determinístico/LLM + reprodutibilidade (6) |
| RNF-02 | `reasoning` obrigatório (4) |
| RNF-03 | `confidence` em todo julgamento, incl. classificação (3.3) |
| RNF-04 | `static_limitations` (3.2) |
| RNF-05 | Fase 1 não executa; teste negativo (8, R8) |
| RNF-06 | Perfis/limiares como dados (`weight_profiles.yaml`) (3.7) |
| RNF-07 | `EvidenceRef` em todo `Finding` (3.10) |
| RNF-08 | Seções de limitação/cobertura no laudo (3.10) |
| RNF-09 | Classificação independente de autodeclaração (3.1) |
| RNF-10 | Laudo autocontido + divergências (3.10) |
| RNF-11 | Zero HITL no caminho feliz; sem auth (3.9) |
| RNF-12 | Política escalonada de fallback de modelo no wrapper de juiz (3.2); config por nó (T-005); laudo parcial (3.5); declaração em metadados (R9) |
| MS-04/07/09 | Subsistema de meta-avaliação + dataset (3.11) |
| MS-08 | Calibração de confiança via dataset (3.11) |
| MS-10 | Tracing LangSmith + medição periódica (3.11) |
| CA-01..15 / CB-01..09 | Estratégia de testes (8) |
| D-01 | Ponto de extensão `TargetRunner` (7) |
| D-02 | Repositório de laudos (3.8b) |
| D-03/D-04 | Dataset de benchmark + calibração diferida (3.11) |

**Verificação de órfãos:** todos os RF-01..29, RF-DIM-*, RNF-01..11, MS-*, D-* têm componente. **Sem requisitos órfãos.**

**Verificação de excesso de engenharia:** todo componente do plano rastreia a ≥1 requisito. Os pontos de extensão da Fase 2 (Seção 7) são **ganchos vazios** (não construídos) — justificados por S-05 (não bloquear a Fase 2), sem custo de implementação. **Sem excesso de engenharia identificado.**

---

## 11. Decisões Técnicas — RESOLVIDAS (2026-05-30)

### Resoluções (entram na fase TASK)

- **#1 — Linguagens: Python-first (3.1).** Fase 1 entrega **apenas o extrator Python**. O TSM e a interface `LanguageExtractor` são **plugáveis por linguagem desde já**; TS/JS é um segundo extrator futuro, sem tocar no TSM nem nos avaliadores. Justificativa: profundidade > amplitude para proteger MS-04/MS-05.
- **#2 — Juízes-LLM: tier Opus em todos os nós de julgamento (2, 3.2).** Modelo é **parâmetro de config por tipo de nó** (permite baixar para Sonnet depois, guiado por MS-08). Structured output via **LangChain `with_structured_output`** dentro dos nós (sem segundo framework de agente); Pydantic v2 permanece a camada de contratos. **PydanticAI não é usado na Fase 1** (nenhum nó precisa de loop de agente autônomo).
- **#2b — Cadeia de fallback de modelo padrão = Opus → Sonnet (RNF-12), configurável; acesso via `ModelGateway` (3.2b).** O padrão por tipo de nó é **primário Opus → fallback Sonnet** (degradação na mesma família, menor risco de variância de veredito). É **inteiramente configurável** (RNF-06): pode-se trocar primário/fallback e até apontar para outro provedor. O acesso a modelo passa por uma **abstração `ModelGateway`** que aceita dois back-ends: (a) **direto Anthropic**; (b) **OpenRouter** (API única compatível com OpenAI, dando alcance cross-provider — Kimi etc. — sem múltiplas integrações). **Ressalva técnica:** a paridade de `with_structured_output` precisa ser verificada por modelo/provedor de fallback — nem todo modelo via OpenRouter suporta o mesmo mecanismo de saída estruturada; o `ModelGateway` deve degradar para um modo de structured output compatível (ex.: tool-calling ou JSON mode) e, se nem isso, tratar como saída malformada (passo 2 da política RNF-12). Cross-provider amplia a degradação (≠ família) → a regra "fallback nunca silencioso + confiança reduzida + declaração" vale com ainda mais força.
- **#3 — Repositório: Postgres + JSONB, reusando a instância do PostgresSaver de prod (3.8b).** **Identidade de achado (RF-29)** = chave composta **(dimensão, código_de_tipo_de_achado, localização_normalizada)**, onde o código de tipo vem de uma **taxonomia controlada enumerada** e a localização é **símbolo/nó (função/classe/nó do grafo), NUNCA número de linha** (linha é evidência, não identidade). **Consequência:** as rubricas dos juízes-LLM devem emitir um `finding_type_code` da lista enumerada. Robusto à reformulação (RNF-01) e a código que muda de lugar.
- **#4 — Divergência: sem delta hardcoded (3.6).** Gatilho ancorado nas faixas da Seção 4.2.6: divergência quando dois julgamentos da mesma dimensão caem em **faixas qualitativas diferentes** (Insuficiente / Adequado com ressalvas / Pronto) **OU** quando a confiança da dimensão fica **abaixo de "médio"**. Valores **configuráveis**; calibrar via MS-08. Documentado como configuração, não constante.
- **#5 — HITL: CLI primeiro, atrás de uma interface `ApprovalProvider` (3.9).** A interface abstrai o interrupt/resume. API-callback e UI ficam como pontos de extensão da Fase 2. Justificativa: HITL na Fase 1 é raro (só RF-24) e RNF-11 exige baixa fricção.

### `[CONFLITO COM A SPEC]`

- **Nenhum conflito identificado** (confirmado pelo usuário). Ponto de atenção (não conflito): a stack proposta omitia o motor de análise estática e tratava sub-tarefas determinísticas como "LLM simples"; o plano corrigiu para **parsing puro nos checks determinísticos** (Seção 2, 3.1), pré-requisito de RNF-01 — alinhado à Spec.

---

*Fim do Plano Técnico — versão 1.3. Decisões técnicas resolvidas (inclui RNF-12: fallback Opus→Sonnet configurável via `ModelGateway`, back-ends Anthropic/OpenRouter). Pronto para a fase TASK (ver [tasks.md](tasks.md)).*
