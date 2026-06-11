"""T-703 — Renderizadores do laudo: Markdown (humano) e JSON (máquina).

Projeções fiéis do `EvaluationReport` canônico (Pydantic). A estrutura Pydantic é a fonte;
estas são vistas derivadas (RNF-10).

Rastreabilidade: plan §3.10; RNF-10.
"""

from __future__ import annotations

from avalia.domain.contracts import EvaluationReport


def render_json(report: EvaluationReport) -> str:
    """Projeção máquina — JSON fiel do contrato."""
    return report.model_dump_json(indent=2)


def render_markdown(report: EvaluationReport) -> str:
    """Projeção humana — Markdown autocontido."""
    h = report.header
    lines: list[str] = []
    lines.append("# Laudo de Avaliação AVALIA (Fase 1 — estática)")
    lines.append("")
    lines.append(f"- **Veredito:** {h.verdict.value} · **Score:** {h.score}/100")
    lines.append(f"- **Confiança geral:** {h.confidence.value}")
    lines.append(
        f"- **Classificação:** {h.classification.topology.value} "
        f"(confiança {h.classification.classification_conf.value}); "
        f"tipo: {h.classification.system_type or 'indeterminado'}"
    )
    lines.append(f"- **Perfil de pesos:** {h.effective_weights.source.value}")
    if h.classification.caveats:
        lines.append(f"- **Ressalvas de classificação:** {'; '.join(h.classification.caveats)}")
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

    meta = report.metadata
    lines.append("## Metadados e limitações")
    lines.append(f"- Componentes presentes: {', '.join(meta.inventory.present) or '—'}")
    lines.append(f"- Componentes ausentes: {', '.join(meta.inventory.missing) or '—'}")
    if meta.model_substitutions:
        lines.append(f"- Substituições de modelo: {'; '.join(meta.model_substitutions)}")
    for lim in meta.known_limitations:
        lines.append(f"- Limitação: {lim}")
    lines.append("")
    return "\n".join(lines)
