# AVALIA — Especificação do Sistema (Fase SPEC)

**Versão:** 0.4  
**Data:** 2026-05-31  
**Status:** Ambiguidades resolvidas (ver Seção 11 — Registro de Decisões). v0.4 acrescenta RNF-12 (resiliência operacional do avaliador / fallback de modelos, padrão Opus→Sonnet configurável e cross-provider) e CB-10, e afina RF-DIM-R2/C1 para nomear fallback de modelo na análise do alvo.

---

## 1. Visão Geral e Problema

### Contexto

Sistemas multiagentes de IA são compostos por múltiplos agentes LLM interconectados, ferramentas, orquestradores, harnesses de teste e configurações que interagem de forma complexa. À medida que esses sistemas são adotados em produção, a pergunta "este sistema está pronto?" tornou-se difícil de responder com rigor: não existe hoje uma metodologia padronizada para avaliar a qualidade de *construção* de um sistema multiagente — independentemente de se executá-lo.

### Problema

Equipes de engenharia, tech leads e revisores de arquitetura que precisam decidir se um sistema multiagente de IA está apto para produção enfrentam:

- Ausência de critérios objetivos e padronizados para julgar a qualidade de construção de sistemas multiagentes.
- Risco de subir para produção sistemas com controles de custo inadequados, sem tratamento de erro, sem observabilidade ou com vulnerabilidades de injeção de prompt.
- Falta de visibilidade sobre regressões entre versões do mesmo sistema.
- Dependência de avaliações manuais ad hoc, inconsistentes e não reproduzíveis.

### Solução

O **AVALIA** é um sistema avaliador que recebe como entrada os artefatos de um sistema multiagente de IA (código-fonte, harness, prompts, configurações e instrumentação) e produz um laudo técnico estruturado com pontuações por dimensão de qualidade, pontuação agregada, nível de confiança e recomendações priorizadas — sem executar o sistema-alvo (Fase 1).

O AVALIA é o **avaliador**. O sistema multiagente sendo avaliado é o **sistema-alvo** — ele é apenas a entrada do AVALIA.

### Princípio de Design Norteador

O AVALIA opera sob o princípio **"decide sozinho, declara o que assumiu, e só chama o humano quando há risco"**. Sempre que possível, o AVALIA classifica, infere e decide automaticamente, declarando explicitamente no laudo cada premissa assumida e a confiança correspondente; ele só interrompe para aprovação humana quando a ação é arriscada (executar o alvo) ou quando uma divergência interna não pôde ser resolvida automaticamente.

---

## 2. Objetivos e Não-Objetivos

### Objetivos

**Fase 1 (escopo atual — Avaliação Estática):**

- O1. Analisar o código-fonte e o harness do sistema-alvo sem executá-lo.
- O2. Classificar automaticamente o tipo e a topologia do sistema-alvo na triagem (ver Seção 5.2), usando essa classificação como insumo das decisões downstream.
- O3. Avaliar sete dimensões de qualidade de construção (custo, performance, qualidade, assertividade, alucinação, trajetória, robustez), produzindo pontuação e raciocínio por dimensão.
- O4. Produzir um laudo técnico reproduzível, com pontuação agregada configurável, recomendações priorizadas e nível de confiança explícito em cada julgamento.
- O5. Permitir comparação entre versões do mesmo sistema-alvo para detectar regressões ou melhorias.
- O6. Garantir que nenhuma execução do sistema-alvo ocorra sem aprovação humana explícita.

**Fase 2 (roadmap — Avaliação Dinâmica, fora do escopo de implementação agora):**

- O7. Executar o sistema-alvo de forma controlada e capturar traces de execução.
- O8. Gerar autonomamente casos de teste e critérios de sucesso para o sistema-alvo.
- O9. Medir comportamento real: custo por execução, latência, qualidade das saídas, taxa de alucinação, calibração de confiança, trajetória real de ferramentas.

### Não-Objetivos (Fase 1)

- NOO1. O AVALIA não julga se as *saídas* do sistema-alvo estão corretas — isso é Fase 2.
- NOO2. O AVALIA não corrige o sistema-alvo nem gera código de correção.
- NOO3. O AVALIA não executa qualquer parte do sistema-alvo em Fase 1.
- NOO4. O AVALIA **não recusa** a avaliação de um sistema por ele não ser claramente multiagente. Em vez disso, classifica o sistema (multiagente / agente único-borderline) e avalia mesmo assim, com ressalvas declaradas no laudo (ver Seção 5.2 e RF-08).
- NOO5. O AVALIA não substitui revisão humana — ele auxilia e estrutura, mas a decisão final de aprovação para produção permanece com o humano.
- NOO6. O AVALIA não avalia aspectos puramente de negócio (valor de negócio da funcionalidade implementada, ROI, aderência a requisitos de produto).
- NOO7. O AVALIA não implementa autenticação ou controle de acesso de usuários na Fase 1 (ver S-03 e Registro de Decisões EC-05).

---

## 3. Personas e Histórias de Usuário

### Personas

**P1 — Engenheiro de Plataforma de IA**  
Responsável por manter padrões e boas práticas para sistemas de IA na organização. Avalia múltiplos sistemas de times diferentes para garantir conformidade com padrões de engenharia.

**P2 — Tech Lead / Arquiteto de Sistema**  
Responsável pelo sistema-alvo. Quer entender onde seu sistema tem pontos fracos antes de subir para produção e priorizar o que melhorar.

**P3 — Revisor de Arquitetura / Comitê de Aprovação**  
Avalia o sistema-alvo como parte de um processo de governança antes de aprovação formal para produção. Precisa de evidências objetivas e rastreáveis para embasar a decisão.

**P4 — Engenheiro de QA / Avaliação de IA**  
Especializado em avaliação e testes de sistemas de IA. Usa o AVALIA como ferramenta base e quer poder configurar pesos e limiares conforme o contexto do sistema-alvo.

### Histórias de Usuário

**US-01 (P1):** Como engenheiro de plataforma de IA, quero submeter o repositório de um sistema-alvo ao AVALIA e receber um laudo com pontuação por dimensão de qualidade, para identificar rapidamente sistemas que não atendem aos padrões mínimos da organização.

**US-02 (P2):** Como tech lead, quero ver recomendações priorizadas por dimensão com raciocínio explícito, para saber o que corrigir primeiro antes do lançamento em produção.

**US-03 (P3):** Como revisor de arquitetura, quero acessar o laudo com nível de confiança em cada julgamento e os trechos do artefato que embasaram cada avaliação, para embasar minha decisão de aprovação com evidências rastreáveis.

**US-04 (P4):** Como engenheiro de QA, quero configurar os pesos de cada dimensão e os limiares de aprovação/reprovação de acordo com o perfil do sistema-alvo, para que a pontuação agregada reflita as prioridades do contexto, sobrescrevendo o perfil que o AVALIA inferiu automaticamente.

**US-05 (P1):** Como engenheiro de plataforma de IA, quero comparar o laudo da versão atual do sistema-alvo com laudos de versões anteriores, para detectar regressões introduzidas em novas releases.

**US-06 (P2):** Como tech lead, quero que o AVALIA me informe quando um julgamento tem baixa confiança, para que eu saiba onde a avaliação é inconclusiva e deva investir em evidências adicionais.

**US-07 (P3):** Como revisor de arquitetura, quero que qualquer análise que requeira execução do sistema-alvo exija minha aprovação explícita antes de prosseguir, para manter controle sobre ações potencialmente destrutivas ou custosas.

**US-08 (P4):** Como engenheiro de QA, quero submeter versões incrementais do sistema-alvo e ver um histórico de evolução das pontuações por dimensão, para acompanhar se as correções aplicadas estão surtindo efeito.

**US-09 (P2):** Como tech lead, quero ver qual tipo e topologia o AVALIA inferiu para o meu sistema e qual perfil de pesos aplicou, para entender o porquê das prioridades do laudo e poder ajustá-las se a inferência estiver errada.

**US-10 (P1):** Como engenheiro de plataforma de IA, quando o agregado cair na faixa intermediária, quero receber a lista de condições que, se atendidas, elevariam o veredito, para transformar o laudo em um plano de ação claro.

---

## 4. Entradas e Saídas

### 4.1 Entradas

O usuário fornece ao AVALIA um **pacote de artefatos do sistema-alvo**, composto por:

| Componente | Descrição | Obrigatoriedade |
|---|---|---|
| Código-fonte | Implementação dos agentes, orquestradores, roteadores e ferramentas | Obrigatório |
| Prompts | Templates de sistema e de usuário usados pelos agentes | Obrigatório |
| Configuração | Parâmetros do sistema: modelos utilizados por nó, variáveis de ambiente, configuração de retry, limites de tokens, etc. | Obrigatório |
| Harness de testes | Suítes de teste, scripts de avaliação, fixtures, datasets de avaliação existentes | Opcional — ausência é computada negativamente |
| Instrumentação | Configuração de logging, tracing, métricas, alertas | Opcional — ausência é computada negativamente |
| Metadados | Identificador do sistema-alvo, versão/tag, descrição funcional, contexto de uso | Obrigatório |

O usuário também fornece, opcionalmente, **configurações do avaliador**:

- Pesos por dimensão de qualidade. Quando não fornecidos, o AVALIA aplica automaticamente um **perfil de pesos** inferido do tipo de sistema-alvo (ver Seção 5.2). Configuração explícita do usuário sempre sobrescreve o perfil inferido.
- Limiar de pontuação agregada para classificação de aprovação/reprovação.
- Limiar de confiança mínima para que um julgamento seja incluído na pontuação agregada.
- Teto de custo/tempo de avaliação (interrompe com laudo parcial honesto — ver RF-12 e CB-05).

### 4.2 Saídas — O Laudo

O AVALIA produz um **laudo técnico** com o seguinte conteúdo:

#### 4.2.1 Cabeçalho do Laudo
- Identificador do sistema-alvo e versão avaliada
- Data e identificador da avaliação
- **Classificação do sistema-alvo:** tipo inferido, topologia (multiagente / agente único-borderline) e confiança dessa classificação (ver Seção 5.2)
- **Perfil de pesos aplicado** e se foi inferido ou sobrescrito pelo usuário
- Sumário executivo em linguagem natural (máximo: um parágrafo)
- **Pontuação agregada** — escala 0–100 ponderada (ver Seção 4.2.6)
- Veredito: **aprovado**, **aprovação condicional** ou **reprovado** (baseado no limiar configurado)
- Nível de confiança geral da avaliação

#### 4.2.2 Avaliação por Dimensão
Para cada uma das sete dimensões aplicáveis, o laudo contém:

- **Pontuação da dimensão** na escala 0–100 (ou marcação "não aplicável" — ver RF-23)
- **Nível de confiança** do julgamento (alto / médio / baixo) com justificativa para confiança não-alta
- **Raciocínio** — argumento que explica a pontuação, nunca apenas um número
- **Evidências** — referências rastreáveis aos trechos do artefato que embasaram o julgamento (arquivo, localização no código, trecho de prompt)
- **Achados** — lista de pontos positivos e pontos de melhoria identificados na dimensão
- **Recomendações** para a dimensão, priorizadas (crítico / importante / sugestão)
- **Limitações da avaliação estática** — o que a Fase 1 não pode concluir sobre esta dimensão e por quê (especialmente relevante para dimensões comportamentais)

#### 4.2.3 Recomendações Consolidadas
- Lista unificada de todas as recomendações, priorizadas por impacto estimado
- Agrupadas por dimensão e marcadas com nível de urgência

#### 4.2.4 Condições de Aprovação (quando o veredito for "aprovação condicional")
- Lista de condições geradas automaticamente pelo AVALIA que, se atendidas, elevariam o veredito
- Cada condição é acionável, priorizada e rastreável a um achado/requisito específico (ver RF-19)

#### 4.2.5 Histórico e Comparação (quando aplicável)
- Δ de pontuação por dimensão em relação à versão anterior do mesmo sistema-alvo
- Identificação de regressões (dimensão piorou) e melhorias (dimensão melhorou)
- Achados resolvidos vs. achados persistentes vs. achados novos

#### 4.2.6 Escala de Pontuação (semântica de produto)
- Cada dimensão e o agregado usam escala **0–100**, com mapeamento para faixas qualitativas:
  - **0–49 — Insuficiente** (não pronto)
  - **50–74 — Adequado com ressalvas** (faixa intermediária; aciona condições de aprovação)
  - **75–100 — Pronto**
- Para as **dimensões comportamentais na Fase 1** (Qualidade e Correção, Assertividade, Alucinação/Fundamentação), a pontuação representa **prontidão de projeto** (presença e adequação de mecanismos), não medição de resultado real, e é sempre acompanhada de confiança reduzida e da limitação correspondente (ver RF-08).

#### 4.2.7 Registro de Divergências (auditabilidade)
- Toda divergência interna detectada entre julgamentos e a forma como foi resolvida (re-julgamento automático ou escalonamento humano) é registrada no laudo (ver RF-20).

#### 4.2.8 Metadados do Laudo
- Configurações usadas na avaliação (pesos efetivos, limiares)
- Indicação de quais componentes do artefato foram recebidos e quais estavam ausentes
- **Cobertura de análise:** o que foi analisado integralmente vs. amostrado/sumarizado (ver RF-12)
- **Substituições de modelo:** se algum nó de julgamento usou um modelo de fallback (em vez do modelo primário), o laudo declara qual nó, qual substituição e o impacto na confiança daquela dimensão (ver RNF-12)
- Lista de limitações conhecidas desta avaliação específica

---

## 5. Requisitos Funcionais

### 5.1 Ingestão e Validação do Artefato

**RF-01 — Recepção do artefato**  
O AVALIA deve receber o pacote de artefatos do sistema-alvo e registrar quais componentes foram fornecidos e quais estão ausentes.

*Critério:* A lista de componentes recebidos e ausentes aparece no laudo antes de qualquer pontuação.

**RF-02 — Validação de completude mínima**  
O AVALIA deve verificar se os componentes obrigatórios (código-fonte, prompts, configuração, metadados) estão presentes. Se algum componente obrigatório estiver ausente, o AVALIA deve notificar o usuário e não prosseguir com a avaliação.

*Critério:* Dado um artefato sem código-fonte, quando submetido ao AVALIA, então o sistema emite mensagem de erro descritiva identificando o componente ausente e não gera laudo parcial.

**RF-03 — Validação de legibilidade**  
O AVALIA deve identificar se o código-fonte está em formato legível (não compilado, não ofuscado, não encriptado). Se ilegível, deve reportar a limitação e proceder apenas com os componentes legíveis, marcando os julgamentos afetados como confiança "baixa".

*Critério:* Dado código-fonte ofuscado, quando submetido, então o laudo registra explicitamente que a análise de código ficou comprometida e os julgamentos afetados têm confiança "baixa".

### 5.2 Classificação e Triagem do Sistema-Alvo *(requisito de primeira classe)*

> A classificação do sistema-alvo é um nó crítico: seu resultado alimenta a escolha do perfil de pesos (RF-15/RF-16), a determinação de dimensões aplicáveis (RF-23) e as ressalvas do laudo. Por isso é tratada como etapa funcional própria, com confiança reportada, e não como detalhe da ingestão.

**RF-04 — Classificação de topologia (multiagente vs. agente único)**  
O AVALIA deve classificar o sistema-alvo quanto à sua topologia em três níveis, com base em heurísticas sobre os artefatos. O sistema é classificado como **multiagente** se detectar pelo menos **dois** dos seguintes sinais: (a) múltiplos papéis/agentes com prompts distintos; (b) orquestração explícita entre eles (grafo, roteamento, hand-off); (c) estado compartilhado entre passos. Se detectar apenas **um** sinal, classifica como **agente único / borderline**. O AVALIA **nunca recusa** a avaliação com base nessa classificação.

*Critério:* Dado um sistema com um único prompt e sem orquestração entre agentes, quando classificado, então o laudo o marca como "agente único / borderline" e prossegue com a avaliação.

**RF-05 — Confiança da classificação**  
A classificação de topologia e de tipo deve sempre reportar seu próprio nível de confiança, dado seu caráter heurístico.

*Critério:* O cabeçalho do laudo contém a classificação acompanhada de um nível de confiança explícito.

**RF-06 — Inferência do tipo de sistema-alvo**  
O AVALIA deve inferir o tipo funcional do sistema-alvo (ex.: RAG/pesquisa, agente de ação/ferramentas, atendimento, pipeline de dados) a partir dos artefatos, para fundamentar a seleção do perfil de pesos. Se não conseguir inferir o tipo com confiança suficiente, deve declarar isso e cair para pesos iguais (ver RF-16).

*Critério:* O laudo declara o tipo inferido e a confiança da inferência; quando a confiança é insuficiente, o laudo declara o uso de pesos iguais como fallback.

**RF-07 — Ressalva de classificação no laudo**  
Quando o sistema for classificado como "agente único / borderline", o laudo deve registrar a ressalva e suas consequências (dimensões não aplicáveis, renormalização de pesos — ver RF-23).

**RF-08 — Independência da classificação em relação a autodeclarações**  
A classificação deve derivar dos artefatos analisados, não de rótulos autodeclarados nos metadados do sistema-alvo (ver RNF-09).

### 5.3 Análise por Dimensão

Para cada uma das sete dimensões (Custo e Eficiência, Performance e Latência, Qualidade e Correção, Assertividade, Alucinação/Fundamentação, Trajetória, Robustez), os seguintes requisitos se aplicam:

**RF-09 — Avaliação estática de cada dimensão**  
Para cada dimensão aplicável, o AVALIA deve analisar os artefatos fornecidos e produzir: pontuação, nível de confiança, raciocínio, evidências rastreáveis, achados e recomendações.

*Critério:* O laudo de qualquer avaliação bem-sucedida contém todas as dimensões aplicáveis, cada uma com os seis elementos acima.

**RF-10 — Raciocínio sempre explícito**  
Nenhuma pontuação pode ser emitida sem raciocínio textual que a justifique. O AVALIA não deve emitir apenas números.

*Critério:* Dado qualquer laudo gerado, quando inspecionado, então cada pontuação de dimensão possui ao menos um parágrafo de raciocínio.

**RF-11 — Nível de confiança obrigatório**  
Cada julgamento deve incluir nível de confiança explícito (alto / médio / baixo). Quando a confiança for médio ou baixo, o AVALIA deve justificar o motivo da incerteza.

*Critério:* Dado um artefato com harness de testes ausente, quando avaliado na dimensão Qualidade e Correção, então o nível de confiança é "baixo" com justificativa "ausência de harness de testes impede avaliação de maquinaria de verificação".

**RF-12 — Degradação graciosa para artefatos grandes**  
Diante de artefatos muito grandes, o AVALIA não recusa por tamanho; ele prioriza automaticamente os arquivos de maior sinal (definição do grafo/orquestração, prompts, ferramentas, configuração, harness de teste) e amostra ou sumariza o restante, declarando no laudo o que foi analisado integralmente vs. amostrado e o impacto na confiança. Um teto configurável de custo/tempo pode interromper a análise, produzindo um laudo parcial honesto.

*Critério:* Dado um artefato que excede o teto de custo/tempo configurado, quando avaliado, então o laudo é emitido como parcial, declara a cobertura de análise e marca como reduzida a confiança das dimensões afetadas.

**RF-13 — Limitação comportamental declarada por dimensão**  
Para dimensões predominantemente comportamentais (Qualidade e Correção, Assertividade, Alucinação/Fundamentação), o laudo deve declarar explicitamente que a Fase 1 avalia apenas a presença e adequação de mecanismos (prontidão de projeto), não o resultado real — e que a avaliação do resultado real requer Fase 2.

*Critério:* O laudo de Fase 1 para a dimensão Alucinação/Fundamentação contém declaração de que "a taxa de alucinação real não pode ser medida sem execução do sistema-alvo (Fase 2)".

**RF-14 — Evidências rastreáveis**  
Cada achado deve citar a localização no artefato que o embasou (arquivo, trecho de prompt, parâmetro de configuração).

*Critério:* Dado um achado de "ausência de teto de iteração em loop", então o laudo indica o arquivo e o nó/função onde o loop foi identificado como sem teto.

#### 5.3.1 Dimensão: Custo e Eficiência de Modelos
- **RF-DIM-C1 — Adequação do mix de modelos:** o AVALIA deve identificar quais modelos são atribuídos a quais nós e avaliar se modelos de alto custo são usados apenas onde necessário, incluindo a presença e a adequação de fallback de modelo/provedor (que afeta tanto custo quanto disponibilidade — cruza com RF-DIM-R2).
- **RF-DIM-C2 — Controles de custo:** verificar presença de teto de iterações em loops, limites de tokens (entrada/saída), truncamento/sumarização de contexto e uso de cache.
- **RF-DIM-C3 — Chamadas redundantes:** identificar padrões de chamadas de modelo redundantes no fluxo principal.

#### 5.3.2 Dimensão: Performance e Latência
- **RF-DIM-P1 — Paralelização:** verificar uso de paralelização onde cabível (fan-out vs. sequência desnecessária) e nós que serializam processamento desnecessariamente.
- **RF-DIM-P2 — Streaming e timeouts:** verificar definição de timeouts para chamadas externas e uso de streaming onde aplicável.

#### 5.3.3 Dimensão: Qualidade e Correção *(comportamental)*
- **RF-DIM-Q1 — Maquinaria de verificação:** verificar existência de harness de testes/avaliação, clareza dos prompts, presença de rubricas/critérios de qualidade no código e etapas de verificação.
- **RF-DIM-Q2 — Limitação comportamental:** declarar que a correção real das saídas não é avaliável na Fase 1 (ver RF-13).

#### 5.3.4 Dimensão: Assertividade e Calibração de Confiança *(comportamental)*
- **RF-DIM-A1 — Expressão de confiança:** verificar se os prompts pedem que os agentes expressem confiança/certeza.
- **RF-DIM-A2 — Tratamento de baixa confiança:** verificar lógica que, diante de baixa confiança, ativa escalonamento, pedido de aprovação humana ou recusa em decidir — em vez de decidir no escuro.

#### 5.3.5 Dimensão: Alucinação / Fundamentação *(comportamental)*
- **RF-DIM-H1 — Mecanismos anti-alucinação:** verificar exigência de citação de fontes, recuperação com atribuição de origem, etapas de verificação factual e instruções de abstenção sem base factual.
- **RF-DIM-H2 — Limitação comportamental:** declarar que a taxa real de alucinação não é medível na Fase 1 (ver RF-13).

#### 5.3.6 Dimensão: Trajetória
- **RF-DIM-T1 — Definições de ferramentas:** verificar clareza das descrições, documentação de parâmetros e ausência de sobreposição ambígua de domínios.
- **RF-DIM-T2 — Lógica de roteamento:** verificar roteamento explícito, sem caminhos contraditórios ou mortos na topologia estática.
- **RF-DIM-T3 — Tetos de loop e passos redundantes:** identificar todos os loops e verificar teto de iteração; identificar caminhos/nós redundantes.

#### 5.3.7 Dimensão: Robustez
- **RF-DIM-R1 — Tratamento de erro estruturado:** verificar se falhas de chamadas externas/ferramentas são tratadas (erro capturado, não exceção solta).
- **RF-DIM-R2 — Retry e fallback:** verificar presença de lógica de retry (com/sem backoff) e fallback, incluindo explicitamente **fallback de modelo/provedor de LLM** (degradação para modelo alternativo quando o primário falha ou fica indisponível). A ausência de fallback de modelo é um achado de robustez de primeira classe (cruza com RF-DIM-C1).
- **RF-DIM-R3 — Validação e anti-injeção:** verificar validação de entradas externas e guard-rails anti-injeção de prompt nos prompts e ferramentas.

### 5.4 Agregação e Pontuação

**RF-15 — Pontuação agregada ponderada por perfil**  
O AVALIA deve calcular a pontuação agregada (0–100) como combinação ponderada das pontuações por dimensão, usando o perfil de pesos aplicável.

**RF-16 — Seleção automática de perfil de pesos com fallback**  
O AVALIA deve aplicar automaticamente um perfil de pesos correspondente ao tipo de sistema inferido (RF-06) — por exemplo, Alucinação/Fundamentação com peso maior em sistemas RAG; Robustez e aprovação humana com peso maior em agentes de ação. Quando o tipo não for inferível com confiança suficiente, deve cair para pesos iguais. O perfil aplicado é sempre declarado no laudo.

*Critério:* Dado um sistema-alvo classificado como RAG com confiança suficiente, quando avaliado sem configuração explícita de pesos, então o laudo declara o perfil "RAG" aplicado e a dimensão Alucinação/Fundamentação tem peso maior que o de um perfil neutro.

**RF-17 — Sobrescrita de pesos pelo usuário**  
Configuração explícita de pesos pelo usuário sempre prevalece sobre o perfil inferido, e o laudo registra que houve sobrescrita.

**RF-18 — Limiares configuráveis de aprovação**  
O AVALIA deve aplicar os limiares configurados para classificar o resultado como aprovado, aprovação condicional ou reprovado, com base no mapeamento de faixas da Seção 4.2.6.

**RF-19 — Geração automática de condições de aprovação**  
Quando o agregado cair na faixa intermediária (aprovação condicional), o AVALIA deve gerar automaticamente a lista de condições que, se atendidas, elevariam o veredito. Cada condição é derivada dos próprios achados, acionável, priorizada e rastreável a um achado/requisito específico. O usuário não precisa configurar essas condições; pode no máximo ignorá-las.

*Critério:* Dado um agregado na faixa 50–74 com um achado "loop sem teto no nó X", quando o laudo é gerado, então as condições de aprovação incluem "adicionar teto de iteração no nó X", rastreável ao achado de origem.

**RF-20 — Detecção e resolução de divergências internas**  
O AVALIA deve detectar divergências entre julgamentos da mesma dimensão (ou de dimensões correlatas) quando discordam além de um limiar, ou quando a confiança agregada fica baixa. A resolução é automática em primeiro lugar (re-julgamento com critério mais estrito ou reconciliação explícita pelo juiz); apenas se a divergência persistir, o AVALIA aciona aprovação/decisão humana. Toda divergência detectada e a forma de resolução são registradas no laudo.

*Critério:* Dado dois julgamentos contraditórios sobre o mesmo loop, quando a divergência não se resolve no re-julgamento automático, então o AVALIA escala para decisão humana e registra a divergência e seu desfecho no laudo.

**RF-21 — Dimensões não aplicáveis e renormalização de pesos**  
Quando uma dimensão não se aplica ao sistema-alvo (ex.: roteamento entre agentes em um sistema de agente único), o AVALIA deve marcá-la como "não aplicável", excluí-la da agregação e renormalizar automaticamente os pesos das demais dimensões — em vez de penalizar o sistema por não ter algo que não faz sentido para ele.

*Critério:* Dado um sistema de agente único sem roteamento entre agentes, quando avaliado, então a dimensão Trajetória (no aspecto de roteamento entre agentes) é marcada "não aplicável", excluída do agregado, e os pesos restantes são renormalizados — sem nota artificialmente baixa.

**RF-22 — Exclusão de julgamentos de baixa confiança da agregação**  
Quando o limiar de confiança mínima for configurado, o AVALIA deve excluir da pontuação agregada os julgamentos abaixo do limiar, sinalizando isso explicitamente no laudo.

### 5.5 Pontos de Aprovação Humana

**RF-23 — Nenhuma execução sem aprovação humana**  
O AVALIA não deve executar qualquer parte do sistema-alvo (Fase 2) sem aprovação humana explícita e registrada, obtida por confirmação ativa do usuário — nunca por omissão ou timeout. Este requisito é absoluto e não pode ser relaxado por configuração.

*Critério:* Dado que o usuário solicita uma avaliação dinâmica (Fase 2), quando o AVALIA está prestes a executar o sistema-alvo, então o sistema exibe descrição da ação planejada e aguarda confirmação explícita antes de prosseguir.

**RF-24 — Escalonamento humano em divergência irresolúvel**  
Quando uma divergência interna não puder ser resolvida automaticamente (RF-20), o AVALIA deve acionar o ponto de aprovação humana, apresentando a divergência e as posições em conflito.

### 5.6 Geração do Laudo

**RF-25 — Laudo completo e estruturado**  
O AVALIA deve gerar um laudo contendo todos os elementos da Seção 4.2 após a conclusão da análise.

**RF-26 — Reproduzibilidade estatística**  
Para o mesmo artefato e as mesmas configurações, o AVALIA deve produzir vereditos e dimensões reprovadas estáveis, com os mesmos achados materiais/críticos presentes, tolerando variação de formulação textual. Onde a verificação é puramente determinística (checagens estáticas de estrutura), o resultado deve ser idêntico entre execuções (ver RNF-01).

*Critério:* Dado o mesmo artefato submetido duas vezes, quando os laudos são comparados, então os vereditos por dimensão e os achados críticos são os mesmos, e os resultados das checagens estáticas determinísticas são idênticos.

**RF-27 — Recomendações priorizadas**  
O AVALIA deve consolidar e priorizar recomendações por nível de urgência (crítico, importante, sugestão) e fornecer uma lista unificada ordenada por impacto estimado.

### 5.7 Comparação Histórica

**RF-28 — Histórico por sistema-alvo**  
O AVALIA deve manter histórico de laudos para o mesmo sistema-alvo (identificado por seu metadado de identidade) e permitir comparação entre versões.

**RF-29 — Detecção de regressão e melhoria**  
Ao comparar versões, o AVALIA deve identificar e destacar: dimensões com piora de pontuação (regressão), dimensões com melhoria, achados resolvidos, achados persistentes e achados novos.

*Critério:* Dado dois laudos do mesmo sistema-alvo (v1 e v2), quando comparados, então o laudo de comparação lista explicitamente quais dimensões regrediram, quais melhoraram e quais achados foram resolvidos.

---

## 6. Requisitos Não-Funcionais

**RNF-01 — Reproduzibilidade estatística do laudo**  
Para o mesmo artefato e as mesmas configurações, o AVALIA deve produzir julgamentos consistentes: vereditos e dimensões reprovadas estáveis, achados críticos sempre presentes, tolerando variação de formulação. Checagens estáticas determinísticas devem ser idênticas entre execuções. Determinismo bit a bit não é exigido, dado o uso de julgamento por LLM.

**RNF-02 — Raciocínio obrigatório em julgamentos qualitativos**  
Nenhum julgamento qualitativo pode ser expresso apenas como número ou classificação. O raciocínio textual é parte inseparável da saída.

**RNF-03 — Nível de confiança sempre presente**  
Todo julgamento — inclusive a classificação do sistema-alvo — deve expor seu nível de confiança.

**RNF-04 — Separação explícita Fase 1 vs. Fase 2**  
O laudo deve deixar inequívoco, para cada dimensão comportamental, o que está sendo avaliado (presença de mecanismos / prontidão de projeto) e o que não pode ser avaliado sem execução (resultado real).

**RNF-05 — Nenhuma ação que execute o sistema-alvo sem aprovação humana**  
Requisito absoluto, não relaxável por configuração.

**RNF-06 — Configurabilidade de pesos e limiares**  
Pesos de agregação e limiares de aprovação são parâmetros da avaliação, não constantes internas. O perfil inferido é sempre sobrescrevível.

**RNF-07 — Rastreabilidade de evidências**  
Todo achado deve ser rastreável ao trecho do artefato que o originou.

**RNF-08 — Transparência sobre limitações**  
O laudo deve declarar ativamente o que não foi possível avaliar (componente ausente, código ilegível, conteúdo amostrado, classificação incerta) e o impacto na confiança.

**RNF-09 — Independência em relação a autodeclarações do sistema-alvo**  
O AVALIA não deve confiar em metadados autodeclarados como substituto da análise. Declarar ter "controles de custo" não conta — o AVALIA verifica no código.

**RNF-10 — Auditabilidade**  
O laudo deve ser autocontido o suficiente para que um auditor externo reproduza o raciocínio e verifique os achados a partir do artefato original — incluindo o registro de divergências (Seção 4.2.7) — sem acesso ao estado interno do AVALIA.

**RNF-11 — Baixa fricção na Fase 1**  
A Fase 1 não deve exigir autenticação, login ou configuração obrigatória além do artefato e metadados. Decisões automáticas (classificação, perfil de pesos, condições) ocorrem sem intervenção, sempre declaradas.

**RNF-12 — Resiliência operacional do avaliador (fallback de modelos)**  
O AVALIA não deve abortar uma avaliação inteira por causa de uma falha transitória ou indisponibilidade de um modelo de julgamento. A política de resiliência é **escalonada e transparente**, nesta ordem:
1. **Erro transitório** (timeout, limite de taxa): nova tentativa no **mesmo modelo** (com backoff). Preserva a reprodutibilidade (RNF-01).
2. **Saída estruturada malformada:** re-solicitação ao mesmo modelo.
3. **Modelo genuinamente indisponível:** degradação para um **modelo de fallback configurado** (padrão **Opus → Sonnet**, configurável; o acesso a modelo é abstraído para permitir back-ends diferentes, inclusive cross-provider), **sempre declarada** no laudo, com **confiança reduzida** na dimensão afetada — nunca silenciosa (preserva RNF-08/RNF-09; respeita a tensão com RNF-01, que não pode ser fingida sob troca de modelo). Quanto mais distante o modelo de fallback do primário (outra família/provedor), maior a redução de confiança esperada.
4. **Falha persistente após esgotar o fallback:** a dimensão afetada é marcada como não avaliável e a avaliação prossegue, podendo resultar em **laudo parcial** (reusa o mecanismo de RF-12).

O modelo primário e o de fallback por tipo de nó são **configuráveis** (RNF-06). Nenhuma substituição de modelo pode ocorrer sem ser registrada nos metadados do laudo (Seção 4.2.8).

---

## 7. Critérios de Aceite

### CA-01 — Validação de artefato incompleto (RF-02)
**Dado** que um usuário submete um pacote sem o código-fonte obrigatório, **Quando** o AVALIA processa a submissão, **Então** o sistema emite notificação descritiva identificando o componente ausente e não gera laudo.

### CA-02 — Classificação de topologia com ressalva (RF-04, RF-07)
**Dado** um sistema com um único prompt e sem orquestração entre agentes, **Quando** classificado, **Então** o laudo o marca como "agente único / borderline" com confiança explícita e prossegue com a avaliação, sem recusa.

### CA-03 — Perfil de pesos inferido e declarado (RF-16)
**Dado** um sistema-alvo classificado como RAG com confiança suficiente e sem pesos configurados, **Quando** avaliado, **Então** o laudo declara o perfil "RAG" aplicado e a dimensão Alucinação/Fundamentação recebe peso maior que num perfil neutro.

### CA-04 — Fallback para pesos iguais (RF-06, RF-16)
**Dado** um sistema cujo tipo não é inferível com confiança suficiente, **Quando** avaliado sem pesos configurados, **Então** o laudo declara o fallback para pesos iguais e a razão.

### CA-05 — Raciocínio sempre presente (RF-10)
**Dado** uma avaliação concluída, **Quando** o laudo é inspecionado, **Então** cada pontuação de dimensão está acompanhada de ao menos um parágrafo de raciocínio.

### CA-06 — Confiança baixa por ausência de harness (RF-11, RF-DIM-Q1)
**Dado** um artefato sem harness de testes, **Quando** o AVALIA avalia Qualidade e Correção, **Então** o laudo registra confiança "baixa" com justificativa referenciando a ausência do harness.

### CA-07 — Limitação comportamental declarada (RF-13)
**Dado** qualquer avaliação de Fase 1, **Quando** o laudo é gerado para Alucinação/Fundamentação, **Então** ele declara explicitamente que a taxa real de alucinação não pode ser medida sem execução.

### CA-08 — Dimensão não aplicável e renormalização (RF-21)
**Dado** um sistema de agente único sem roteamento entre agentes, **Quando** avaliado, **Então** o aspecto inaplicável de Trajetória é marcado "não aplicável", excluído do agregado, e os pesos restantes são renormalizados — sem nota artificialmente baixa.

### CA-09 — Condições de aprovação geradas automaticamente (RF-19)
**Dado** um agregado na faixa 50–74 com achado "loop sem teto no nó X", **Quando** o laudo é gerado, **Então** as condições de aprovação incluem "adicionar teto de iteração no nó X", rastreável ao achado de origem.

### CA-10 — Divergência resolvida automaticamente e registrada (RF-20)
**Dado** dois julgamentos contraditórios sobre o mesmo trecho, **Quando** o re-julgamento automático os reconcilia, **Então** o laudo registra a divergência e como foi resolvida, sem acionar o humano.

### CA-11 — Divergência irresolúvel escala para humano (RF-20, RF-24)
**Dado** uma divergência que persiste após re-julgamento automático, **Quando** o AVALIA não consegue reconciliar, **Então** ele aciona o ponto de aprovação humana e registra a divergência no laudo.

### CA-12 — Aprovação humana obrigatória para execução (RF-23)
**Dado** que o usuário solicita avaliação dinâmica (Fase 2), **Quando** o AVALIA está prestes a executar qualquer componente do sistema-alvo, **Então** o sistema exibe a ação planejada, aguarda confirmação ativa e só prossegue após confirmação explícita — nunca por omissão ou timeout.

### CA-13 — Laudo parcial honesto para artefato grande (RF-12)
**Dado** um artefato que excede o teto de custo/tempo configurado, **Quando** avaliado, **Então** o laudo é emitido como parcial, declara a cobertura (integral vs. amostrado) e reduz a confiança das dimensões afetadas.

### CA-14 — Reproduzibilidade estatística (RNF-01)
**Dado** o mesmo artefato submetido duas vezes com as mesmas configurações, **Quando** os laudos são comparados, **Então** os vereditos por dimensão e os achados críticos coincidem, e as checagens estáticas determinísticas são idênticas.

### CA-15 — Comparação de versões (RF-29)
**Dado** dois laudos de versões diferentes do mesmo sistema-alvo, **Quando** comparados, **Então** o laudo de comparação lista dimensões com regressão, com melhoria, achados resolvidos, persistentes e novos.

---

## 8. Casos de Borda e Tratamento de Falha

### CB-01 — Artefato incompleto (componentes opcionais)
Um ou mais componentes opcionais ausentes (harness, instrumentação). **Comportamento:** prossegue com os componentes presentes; dimensões afetadas recebem confiança reduzida; o laudo registra os componentes ausentes e seu impacto por dimensão.

### CB-02 — Código ilegível ou parcialmente ilegível
Código ofuscado, compilado, encriptado ou não interpretável. **Comportamento:** registra a limitação, avalia apenas o legível, marca julgamentos impactados como confiança "baixa", não emite pontuações dependentes do ilegível sem aviso.

### CB-03 — Sistema-alvo que não é multiagente
O artefato não apresenta sinais suficientes de sistema multiagente. **Comportamento (RF-04, RF-21):** o AVALIA **não recusa**; classifica como "agente único / borderline", marca as dimensões inaplicáveis como "não aplicável", renormaliza os pesos e prossegue com avaliação válida e ressalva no laudo.

### CB-04 — Divergência entre julgamentos
Dois julgamentos contraditórios sobre o mesmo trecho. **Comportamento (RF-20, RF-24):** o AVALIA detecta a divergência, tenta resolução automática (re-julgamento/reconciliação) e, se persistir, escala para decisão humana — sempre registrando a divergência e seu desfecho no laudo.

### CB-05 — Artefato muito grande
Volume de código/artefatos excede a capacidade de análise integral. **Comportamento (RF-12):** sem limite rígido; o AVALIA prioriza arquivos de maior sinal, amostra/sumariza o resto, declara a cobertura e o impacto na confiança; teto configurável de custo/tempo pode interromper com laudo parcial honesto.

### CB-06 — Ausência de histórico para comparação
O usuário pede comparação, mas não há laudo anterior. **Comportamento:** gera o laudo atual normalmente, informa a ausência de histórico e não emite comparação.

### CB-07 — Configuração de pesos inválida
Pesos com soma incorreta ou valores negativos. **Comportamento:** rejeita a configuração antes da análise, informa o problema específico e não prossegue até receber configuração válida.

### CB-08 — Componentes contraditórios no artefato
A configuração declara um modelo, mas o código referencia outro; prompts assumem fluxo que o código não implementa. **Comportamento:** identifica e reporta as contradições como achados, com referência aos trechos, e reduz a confiança das dimensões afetadas.

### CB-09 — Tipo de sistema não inferível
O AVALIA não consegue inferir o tipo com confiança suficiente. **Comportamento (RF-06, RF-16):** declara a incerteza e aplica pesos iguais como fallback, registrando a decisão.

### CB-10 — Modelo de julgamento indisponível durante a avaliação
Um nó de julgamento do AVALIA sofre falha transitória ou indisponibilidade do modelo primário. **Comportamento (RNF-12):** o AVALIA aplica a política escalonada — retry no mesmo modelo → re-solicitação → fallback declarado com confiança reduzida → laudo parcial se persistir. A avaliação **não** é abortada por uma falha pontual; toda substituição de modelo é registrada nos metadados do laudo.

---

## 9. Métricas de Sucesso do AVALIA

### 9.1 Utilidade para os Usuários
- **MS-01 — Adoção:** percentual de avaliações para produção em que o AVALIA é consultado.
- **MS-02 — Actionability:** percentual de recomendações consideradas acionáveis e relevantes (feedback pós-laudo).
- **MS-03 — Tempo de avaliação:** redução no tempo médio de avaliação pré-produção vs. processo manual.

### 9.2 Confiabilidade dos Julgamentos
- **MS-04 — Concordância com revisores humanos (meta-avaliação):** mede-se a concordância do AVALIA com um conjunto de sistemas-alvo de veredito humano de referência. A **métrica primária é a concordância em nível de veredito por dimensão** (aprovado / ressalva / reprovado), por ser mais estável que concordar na nota exata. O **limiar de "confiável" não é fixado nesta Spec** — deve ser calibrado empiricamente após o primeiro lote de avaliações (ver Registro de Decisões EC-10).
- **MS-05 — Falsos negativos críticos:** percentual de sistemas aprovados pelo AVALIA que apresentaram problemas sérios em produção nas dimensões avaliadas. Meta: próximo de zero para problemas críticos.
- **MS-06 — Reproduzibilidade observada:** percentual de avaliações do mesmo artefato com vereditos e achados críticos coincidentes em execuções independentes (consistente com a reproduzibilidade estatística — RNF-01).

### 9.3 Meta-Avaliação (Validar se o AVALIA Julga Bem)
- **MS-07 — Benchmark de calibração:** aplica-se o AVALIA a sistemas-alvo de qualidade conhecida (falhas documentadas e exemplares) e mede-se se ele identifica os problemas esperados sem inventar inexistentes.
- **MS-08 — Calibração de confiança:** julgamentos com confiança "alta" devem ser confirmados por humanos em taxa maior do que os de confiança "baixa" — validando que o nível de confiança é informativo.
- **MS-09 — Calibração da classificação:** a classificação de topologia/tipo (Seção 5.2) é medida contra rótulos humanos de referência, validando o nó de triagem que alimenta as decisões downstream.
- **MS-10 — Evolução da meta-avaliação:** o desempenho em MS-04 a MS-09 é medido periodicamente para detectar deriva ou melhoria.

---

## 10. Suposições e Dependências

### Suposições
- **S-01:** Os artefatos são fornecidos em formato textual legível (código-fonte, não binários).
- **S-02:** Os metadados do sistema-alvo (identificador, versão, descrição) são fornecidos pelo usuário; o AVALIA não infere a identidade do alvo a partir do código (mas infere tipo/topologia — Seção 5.2).
- **S-03:** O usuário tem autorização para avaliar o sistema-alvo; a Fase 1 **não** implementa autenticação nem controle de acesso (ver RNF-11, NOO7, EC-05).
- **S-04:** "Não executar o sistema-alvo" na Fase 1 significa não instanciar, invocar APIs ou executar código do alvo em ambiente algum — a análise é puramente sobre artefatos estáticos.
- **S-05:** A Fase 2 está fora do escopo de implementação atual, mas seus requisitos são registrados para não criar impedimentos arquiteturais na Fase 1.
- **S-06:** O AVALIA é independente do sistema-alvo — não compartilha infraestrutura, credenciais ou estado com o sistema que avalia.

### Dependências
- **D-01 (Fase 2):** a avaliação dinâmica depende de um ambiente de execução isolado para o sistema-alvo.
- **D-02:** a comparação histórica depende de armazenamento persistente de laudos anteriores (mecanismo é decisão da fase Plan).
- **D-03:** a meta-avaliação (MS-07–MS-09) depende de um conjunto de sistemas-alvo benchmark com qualidade e classificação documentadas — sua curadoria é pré-requisito operacional.
- **D-04:** a calibração do limiar de "confiável" (MS-04) depende da coleta do primeiro lote de avaliações com veredito humano de referência.

---

## 11. Registro de Decisões (ambiguidades resolvidas)

As 10 ambiguidades da versão 0.1 foram resolvidas e incorporadas. Registro para rastreabilidade:

| ID | Decisão |
|---|---|
| **EC-01** | Classificação de topologia em 3 níveis por heurística (≥2 sinais ⇒ multiagente; 1 sinal ⇒ agente único/borderline). Nunca recusa; avalia com ressalva; confiança da classificação reportada. → RF-04, RF-05, RF-07. |
| **EC-02** | Perfil de pesos inferido do tipo de sistema na triagem, aplicado automaticamente; fallback para pesos iguais quando o tipo não é inferível; perfil declarado e sobrescrevível. → RF-06, RF-16, RF-17. |
| **EC-03** | Escala definida na Spec: 0–100 por dimensão e agregado, com faixas (0–49 insuficiente / 50–74 adequado com ressalvas / 75–100 pronto). Dimensões comportamentais na Fase 1 reportam "prontidão de projeto" + confiança reduzida. → Seção 4.2.6. |
| **EC-04** | Condições de aprovação geradas automaticamente pelo AVALIA a partir dos achados, acionáveis, priorizadas e rastreáveis; usuário não configura. → RF-19, Seção 4.2.4. |
| **EC-05** | Sem autenticação na Fase 1; controle de acesso só entra na Fase 2 e como decisão de deployment, se a execução tocar credenciais/serviços reais. → RNF-11, NOO7, S-03. |
| **EC-06** | Reproduzibilidade estatística (vereditos e dimensões reprovadas estáveis, achados críticos presentes; variação textual tolerada). Checagens estáticas determinísticas são idênticas. → RF-26, RNF-01. |
| **EC-07** | Sistema não-multiagente: avaliação normal com nota + ressalva; dimensões inaplicáveis marcadas "não aplicável", excluídas e pesos renormalizados. → RF-21, CB-03. |
| **EC-08** | Detecção explícita de divergências internas; resolução automática primeiro (re-julgamento/reconciliação) e HITL só se persistir; tudo registrado no laudo. → RF-20, RF-24, Seção 4.2.7. |
| **EC-09** | Sem limite rígido de tamanho; degradação graciosa por priorização de arquivos de maior sinal + amostragem/sumarização do resto; teto configurável de custo/tempo interrompe com laudo parcial honesto. → RF-12, CB-05. |
| **EC-10** | Nenhum número arbitrário de concordância fixado na Spec. Métrica primária = concordância em nível de veredito por dimensão; limiar de "confiável" calibrado empiricamente após o primeiro lote. → MS-04, D-04. |

### Consequência de design registrada
EC-02 + EC-07 (e EC-01) tornam a **classificação do sistema-alvo** insumo de múltiplas decisões downstream (perfil de pesos, dimensões aplicáveis, ressalvas, tipo de veredito). Por isso a classificação foi elevada a **requisito funcional de primeira classe** (Seção 5.2), com confiança própria reportada e meta-avaliação dedicada (MS-09) — e não tratada como detalhe da ingestão.

---

*Fim da Especificação — versão 0.4. Pronta para a fase PLAN.*
