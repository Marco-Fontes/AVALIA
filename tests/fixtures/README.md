# tests/fixtures — ALVOS estáticos (DADO, nunca executado)

Cada fixture é um mini sistema-alvo sintético, tratado como **dado estático** lido por
`ast` / tree-sitter. **Nada aqui é importado nem executado** pelo AVALIA nem pelos testes
(RNF-05 / S-04 / T-1006). Fixtures podem conter padrões "ruins" de propósito (loop sem
teto, `exec`, prompt-injection embutido) — isso é ENTRADA de teste, não código do avaliador,
e por isso os hooks/guardas ignoram este diretório.

Cenários previstos (T-1001): RAG (alta confiança), agente de ação, agente único/borderline,
grande (estoura teto), ofuscado, config↔código contraditório, indutor de divergência
reconciliável, indutor de divergência persistente, loop sem teto na faixa 50–74.
