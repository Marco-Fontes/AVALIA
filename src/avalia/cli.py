"""Porta de entrada de uso (MVP): aponta o AVALIA para o repositório de um sistema-alvo.

`avalia <caminho> [opções]` lê os artefatos do alvo (texto), roda o grafo de avaliação e grava o
laudo em Markdown e JSON, imprimindo um resumo. **Nunca executa o alvo** (RNF-05/S-04) — só leitura
estática. Por padrão roda em modo **determinístico** (sem custo, sem chave de API); `--llm` liga os
juízes-LLM via `ModelGateway` (default Opus→Sonnet, configurável por env — RNF-06/RNF-12).

Baixa fricção (RNF-11): só o caminho do alvo é obrigatório; tipo/perfil/condições são automáticos.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Any

from avalia.config.evaluator_config import EvaluatorConfig
from avalia.domain.enums import RunStatus, Urgency
from avalia.domain.submission import Submission, TargetMetadata
from avalia.graph.build_graph import build_avalia_graph
from avalia.hitl.approval import CLIApprovalProvider, StaticApprovalProvider
from avalia.hitl.runner import run_evaluation
from avalia.loader import read_target_directory
from avalia.report.render import render_json, render_markdown


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="avalia",
        description="AVALIA — avaliador ESTÁTICO de sistemas multiagentes de IA (Fase 1). "
        "Lê o alvo como texto e gera um laudo; nunca executa o alvo.",
    )
    p.add_argument("path", help="Diretório (ou arquivo) do sistema-alvo a avaliar.")
    p.add_argument(
        "--target-id",
        default=None,
        help="Identificador do alvo (default: nome do diretório). Vincula versões no histórico.",
    )
    p.add_argument("--version", default="0", help="Versão/tag do alvo avaliada (default: '0').")
    p.add_argument(
        "-o",
        "--out",
        default="avalia-out",
        help="Diretório de saída do laudo (default: avalia-out).",
    )
    p.add_argument(
        "--format",
        choices=["both", "md", "json"],
        default="both",
        help="Formato(s) do laudo gravado(s) (default: both).",
    )
    p.add_argument(
        "--llm",
        action="store_true",
        help="Liga os juízes-LLM via ModelGateway (requer credencial; default: determinístico).",
    )
    p.add_argument(
        "--max-files",
        type=int,
        default=None,
        help="Teto de arquivos analisados a fundo; acima dele o resto é amostrado (laudo parcial).",
    )
    return p


def _make_config(args: argparse.Namespace) -> EvaluatorConfig:
    return EvaluatorConfig(max_analyzed_files=args.max_files)


def _summary(report: Any, status: RunStatus, mode: str, out_paths: list[Path]) -> str:
    h = report.header
    lines: list[str] = []
    lines.append("")
    lines.append("== AVALIA - resumo do laudo ==")
    if status is RunStatus.PARTIAL:
        lines.append("[!] LAUDO PARCIAL - a análise não foi integral (ver limitações no laudo).")
    lines.append(
        f"  Veredito : {h.verdict.value}   Score: {h.score}/100   Confiança: {h.confidence.value}"
    )
    cls = h.classification
    lines.append(
        f"  Classificação: {cls.topology.value} "
        f"(conf. {cls.classification_conf.value}); tipo: {cls.system_type or 'indeterminado'}"
    )
    lines.append(f"  Perfil de pesos: {h.effective_weights.source.value}   Modo de juízo: {mode}")
    n_crit = sum(1 for dr in report.dimensions for f in dr.findings if f.urgency is Urgency.CRITICO)
    n_imp = sum(
        1 for dr in report.dimensions for f in dr.findings if f.urgency is Urgency.IMPORTANTE
    )
    lines.append(f"  Achados: {n_crit} crítico(s), {n_imp} importante(s)")
    subs = sorted({s for dr in report.dimensions for s in dr.model_substitutions})
    if subs:
        lines.append(f"  Substituições de modelo (RNF-12): {'; '.join(subs)}")
    if report.consolidated_recommendations:
        lines.append("  Recomendações principais:")
        for rec in report.consolidated_recommendations[:5]:
            lines.append(f"    - [{rec.urgency.value}] {rec.statement}")
    lines.append("  Laudo gravado em:")
    for path in out_paths:
        lines.append(f"    - {path}")
    lines.append("")
    return "\n".join(lines)


def _force_utf8_streams() -> None:
    """Evita UnicodeEncodeError em consoles legados (ex.: Windows cp1252) ao imprimir o resumo."""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
        except (AttributeError, ValueError):
            pass


def main(argv: list[str] | None = None) -> int:
    _force_utf8_streams()
    args = _build_parser().parse_args(argv)

    root = Path(args.path)
    target_id = args.target_id or (root.name if root.name else "alvo")
    try:
        files = read_target_directory(root)
    except FileNotFoundError as exc:
        print(f"Erro: {exc}", file=sys.stderr)
        return 2

    config = _make_config(args)
    submission = Submission(
        artifact_files=files,
        metadata=TargetMetadata(target_id=target_id, version=args.version),
        config=config,
    )

    gateway = None
    mode = "determinístico"
    if args.llm:
        from avalia.model_gateway.gateway import ModelGateway

        if not os.environ.get("ANTHROPIC_API_KEY") and not os.environ.get("OPENROUTER_API_KEY"):
            print(
                "Aviso: --llm ligado sem ANTHROPIC_API_KEY/OPENROUTER_API_KEY; o juízo pode "
                "cair para fallback declarado / laudo parcial (RNF-12).",
                file=sys.stderr,
            )
        gateway = ModelGateway(config)
        mode = "juiz-LLM (ModelGateway)"

    graph = build_avalia_graph(gateway=gateway)
    provider = CLIApprovalProvider() if gateway is not None else StaticApprovalProvider([])
    result = run_evaluation(
        graph, {"submission": submission}, approval_provider=provider, thread_id=target_id
    )

    status = result.get("status")
    report = result.get("report")
    if report is None:
        print(f"Erro: {result.get('error_message', 'avaliação não gerou laudo.')}", file=sys.stderr)
        return 2

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_paths: list[Path] = []
    if args.format in ("both", "md"):
        md_path = out_dir / "laudo.md"
        md_path.write_text(render_markdown(report), encoding="utf-8")
        out_paths.append(md_path)
    if args.format in ("both", "json"):
        json_path = out_dir / "laudo.json"
        json_path.write_text(render_json(report), encoding="utf-8")
        out_paths.append(json_path)

    print(_summary(report, status or RunStatus.OK, mode, out_paths))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
