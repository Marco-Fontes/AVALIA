"""T-703 — Renderizadores do laudo: Markdown (humano) e JSON (máquina).

Projeções fiéis do `EvaluationReport` canônico (Pydantic). A estrutura Pydantic é a fonte;
estas são vistas derivadas (RNF-10).

Rastreabilidade: plan §3.10; RNF-10.
"""

from __future__ import annotations

from avalia.config.evaluator_config import BandThresholds
from avalia.domain.contracts import (
    BudgetUsage,
    DimensionResult,
    EvaluationReport,
    HarnessCoverageReport,
)
from avalia.domain.enums import Urgency
from avalia.report.harness import CATEGORY_META

_URGENCY_RANK = {Urgency.CRITICO: 3, Urgency.IMPORTANTE: 2, Urgency.SUGESTAO: 1}
_CATEGORY_LABEL = {cat: (num, label) for cat, num, label in CATEGORY_META}


def render_json(report: EvaluationReport) -> str:
    """Projeção máquina — JSON fiel do contrato."""
    return report.model_dump_json(indent=2)


def _band_label(score: int | None, th: BandThresholds) -> str:
    """Faixa do veredito (spec §4.2.6) para exibição por dimensão."""
    if score is None:
        return "não aplicável"
    if score >= th.aprovado_min:
        return "pronto"
    if score >= th.aprovacao_condicional_min:
        return "adequado c/ ressalvas"
    return "insuficiente"


def _top_finding_label(dr: DimensionResult) -> str:
    """Achado de maior urgência da dimensão, para a coluna-resumo da matriz."""
    if not dr.findings:
        return "—"
    top = max(dr.findings, key=lambda f: _URGENCY_RANK.get(f.urgency, 0))
    return f"[{top.urgency.value}] {top.finding_type.value}"


def _harness_section(hc: HarnessCoverageReport) -> list[str]:
    """Tabela da camada de cobertura de harness — o resultado primário (Fase 0)."""
    lines = ["## Cobertura de harness (análise estática)", ""]
    lines.append("| # | Categoria | Cobertura | Confiança | Achados / situação |")
    lines.append("|---|---|---|---|---|")
    for c in hc.categories:
        num, label = _CATEGORY_LABEL[c.category]
        if not c.assessed:
            situacao = c.note or "sem check nesta fase"
            lines.append(f"| {num} | {label} | n/a | — | {situacao} |")
            continue
        cobertura = f"{c.coverage}%"
        conf = c.confidence.value
        if c.findings:
            types = ", ".join(sorted({f.finding_type.value for f in c.findings}))
            situacao = f"{len(c.findings)} achado(s): {types}"
        else:
            situacao = c.note or "nenhum achado"
        lines.append(f"| {num} | {label} | {cobertura} | {conf} | {situacao} |")
    lines.append("")
    return lines


def _ceiling(value: object | None) -> str:
    return "sem teto" if value is None else f"teto {value}"


def describe_budget_usage(usage: BudgetUsage) -> str:
    """Linha legível do consumo vs. tetos (spec v0.5 §4.2.8, DQ-01) — usada no MD e na CLI."""
    tokens = (
        f"{usage.total_tokens} tokens ({usage.input_tokens} entrada / {usage.output_tokens} "
        f"saída; {_ceiling(usage.token_ceiling)})"
    )
    if usage.cost is not None:
        cost = f"custo {usage.cost:.4f} ({_ceiling(usage.cost_ceiling)})"
    else:
        cost = f"custo não calculável — {usage.cost_unavailable_reason}"
    elapsed = f"tempo {usage.elapsed_s:.1f}s ({_ceiling(usage.time_ceiling_s)})"
    parts = [tokens, cost, elapsed]
    if usage.degraded_dims:
        parts.append("dimensões degradadas: " + ", ".join(d.value for d in usage.degraded_dims))
    return "; ".join(parts)


def render_markdown(report: EvaluationReport) -> str:
    """Projeção humana — Markdown autocontido."""
    h = report.header
    lines: list[str] = []
    lines.append("# Laudo de Avaliação AVALIA (Fase 1 — estática)")
    lines.append("")
    if any(lim.startswith("Laudo PARCIAL") for lim in report.metadata.known_limitations):
        lines.append(
            "> ⚠️ **LAUDO PARCIAL** — a análise não foi integral; confiança reduzida (RF-12)."
        )
        lines.append("")
    # O resultado é a COBERTURA DE HARNESS por categoria; o veredito é o título.
    lines.append(f"- **Veredito:** {h.verdict.value}")
    hc = report.harness_coverage
    if hc is not None:
        lines.append(
            f"- **Cobertura de harness — análise estática:** {hc.coverage}/100 "
            f"({hc.passed_categories} de {hc.assessed_categories} categorias avaliadas sem "
            "achado; categorias n/a declaradas abaixo, fora do denominador). 100 = tudo que se "
            "checa estaticamente está presente; comportamento real depende de execução (Fase 2)."
        )
    lines.append(
        f"- **Classificação:** {h.classification.topology.value} "
        f"(confiança {h.classification.classification_conf.value}); "
        f"tipo: {h.classification.system_type or 'indeterminado'}"
    )
    lines.append(f"- **Perfil de pesos:** {h.effective_weights.source.value}")
    if h.classification.caveats:
        lines.append(f"- **Ressalvas de classificação:** {'; '.join(h.classification.caveats)}")
    lines.append("")

    # Resultado primário: cobertura pelas categorias de harness que o time usa como checklist.
    if hc is not None:
        lines.extend(_harness_section(hc))

    # Mecânica interna: as 7 dimensões que alimentam a camada acima (nota ponderada por dimensão).
    th = report.metadata.effective_config.thresholds
    lines.append("## Matriz por dimensão (mecânica interna)")
    lines.append("")
    lines.append("| Dimensão | Nota | Faixa | Confiança | Achado principal |")
    lines.append("|---|---|---|---|---|")
    for dr in report.dimensions:
        if not dr.applicable or dr.score is None:
            lines.append(f"| {dr.dimension.value} | n/a | não aplicável | — | — |")
            continue
        conf = dr.confidence.value
        if dr.static_limitations:
            conf += " (estática: só presença)"
        top = _top_finding_label(dr)
        lines.append(
            f"| {dr.dimension.value} | {dr.score} | {_band_label(dr.score, th)} | {conf} | {top} |"
        )
    lines.append("")

    lines.append("## Dimensões")
    for dr in report.dimensions:
        score = "n/a" if dr.score is None else str(dr.score)
        lines.append(f"### {dr.dimension.value} — {score} (confiança {dr.confidence.value})")
        lines.append(dr.reasoning)
        if dr.static_limitations:
            lines.append(f"> Limitação estática: {dr.static_limitations}")
        for f in dr.findings:
            ev = f.evidence[0]
            loc = f"{ev.file_path}::{ev.symbol}"
            lines.append(
                f"- [{f.urgency.value}] **{f.finding_type.value}** — {f.statement} ({loc})"
            )
        lines.append("")

    if report.approval_conditions:
        lines.append("## Condições de aprovação")
        for c in report.approval_conditions:
            lines.append(f"- [{c.urgency.value}] {c.statement} (achado `{c.traces_to[:12]}…`)")
        lines.append("")

    if report.consolidated_recommendations:
        lines.append("## Recomendações")
        for r in report.consolidated_recommendations:
            lines.append(f"- [{r.urgency.value}] {r.statement}")
        lines.append("")

    if report.divergences:
        lines.append("## Divergências de julgamento")
        for d in report.divergences:
            bands = ", ".join(o.band.value for o in d.conflicting_positions if o.band)
            note = d.resolution_note or "—"
            lines.append(
                f"- **{d.dimension.value}** ({d.threshold_hit}; faixas: {bands}) — "
                f"resolvida por {d.resolved_by.value}: {note}"
            )
        lines.append("")

    if report.comparison is not None:
        cmp = report.comparison
        lines.append("## Comparação com versão anterior")
        lines.append(f"- Laudo anterior: `{cmp.prev_report_id[:12]}…`")
        if cmp.regressions:
            lines.append(f"- Regressões: {', '.join(cmp.regressions)}")
        if cmp.improvements:
            lines.append(f"- Melhorias: {', '.join(cmp.improvements)}")
        lines.append(
            f"- Achados: {len(cmp.resolved_findings)} resolvido(s), "
            f"{len(cmp.persistent_findings)} persistente(s), {len(cmp.new_findings)} novo(s)"
        )
        lines.append("")

    meta = report.metadata
    lines.append("## Metadados e limitações")
    lines.append(f"- Componentes presentes: {', '.join(meta.inventory.present) or '—'}")
    lines.append(f"- Componentes ausentes: {', '.join(meta.inventory.missing) or '—'}")
    if meta.model_substitutions:
        lines.append(f"- Substituições de modelo: {'; '.join(meta.model_substitutions)}")
    if meta.budget_usage is not None:
        lines.append(f"- Consumo de orçamento: {describe_budget_usage(meta.budget_usage)}")
    for lim in meta.known_limitations:
        lines.append(f"- Limitação: {lim}")
    lines.append("")
    return "\n".join(lines)
