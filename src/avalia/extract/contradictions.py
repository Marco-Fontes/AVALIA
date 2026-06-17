"""T-106 — Detecção de contradições internas config↔código (CB-08, RNF-08).

Compara fatos do TSM entre si para achar incoerências do PRÓPRIO artefato (não opinião):
- **modelo declarado ≠ usado** (`CONTRADICAO_MODELO_CONFIG`, dimensão Custo): uma config
  declara um modelo e o código chama outro slug literal diferente.
- **prompt assume fluxo inexistente** (`CONTRADICAO_FLUXO_PROMPT`, dimensão Trajetória): um
  prompt manda encaminhar/rotear para um nó/agente que as arestas/agentes não implementam.

Cada contradição vira um `Finding` com evidência dos DOIS lados (RNF-07). Heurísticas
determinísticas e conservadoras (baixo falso-positivo). Nada executa o alvo (RNF-05).

Rastreabilidade: CB-08, RNF-08; T-106; regra 4 (Finding na dimensão dona).
"""

from __future__ import annotations

import re

from avalia.domain.contracts import Finding
from avalia.domain.enums import Urgency
from avalia.domain.evidence import EvidenceRef
from avalia.domain.taxonomy import FindingType
from avalia.domain.tsm import ConfigItem, TargetStaticModel

# Slug de modelo: contém dígito, '-' ou '/' (ex.: "gpt-4o", "claude-opus", "claude-3-5").
# Um identificador puro ("MODEL_NAME") NÃO casa → é tratado como referência a config, não slug.
_SLUG = re.compile(r"^[A-Za-z0-9._/-]+$")
# Verbos de roteamento seguidos do nome do destino (pt/en).
_ROUTE = re.compile(
    r"(?:encaminh\w*|rotei\w*|deleg\w*|hand[\s-]?off|route|transfira|transfere|passe?)\s+"
    r"(?:para|to|ao|à|o|a)?\s*['\"]?([A-Za-z_][A-Za-z0-9_]*)",
    re.IGNORECASE,
)


def _looks_like_slug(expr: str) -> bool:
    return bool(_SLUG.match(expr)) and (
        "-" in expr or "/" in expr or any(c.isdigit() for c in expr)
    )


def _model_contradictions(tsm: TargetStaticModel) -> list[Finding]:
    """Contradição modelo declarado≠usado, escopada ao MESMO arquivo (precisão > recall).

    Comparar slugs declarados e usados ACROSS-FILE gera falso positivo (ex.: um default/constante
    de modelo num módulo vs. slugs de exemplo em testes de outro módulo). A contradição interna
    (CB-08) que nos interessa é local: uma config e uma chamada divergentes no MESMO arquivo.
    Mantém a heurística conservadora prometida nesta camada (§10 Riscos).
    """
    model_cfgs = [c for c in tsm.configs if "model" in c.key.lower()]
    if not model_cfgs:
        return []

    # Agrupa por arquivo: só comparamos declaração×uso dentro do mesmo arquivo.
    cfgs_by_file: dict[str, list[ConfigItem]] = {}
    for c in model_cfgs:
        cfgs_by_file.setdefault(c.evidence.file_path, []).append(c)

    findings: list[Finding] = []
    seen: set[tuple[str, str]] = set()
    for ma in tsm.model_assignments:
        file_path = ma.evidence.file_path
        file_cfgs = cfgs_by_file.get(file_path)
        if not file_cfgs:
            continue
        declared_slugs = {c.value_expr for c in file_cfgs if _looks_like_slug(c.value_expr)}
        declared_keys = {c.key for c in file_cfgs}
        if not declared_slugs:
            continue
        expr = ma.model_expr
        if expr in declared_keys:  # referencia a config do mesmo arquivo → coerente
            continue
        key = (file_path, expr)
        if _looks_like_slug(expr) and expr not in declared_slugs and key not in seen:
            seen.add(key)
            cfg = file_cfgs[0]
            findings.append(
                Finding(
                    finding_type=FindingType.CONTRADICAO_MODELO_CONFIG,
                    urgency=Urgency.IMPORTANTE,
                    statement=(
                        f"Modelo usado no código ('{expr}') difere do declarado em "
                        f"config '{cfg.key}' ({', '.join(sorted(declared_slugs))})."
                    ),
                    reasoning=(
                        "A configuração e o código discordam sobre qual modelo é usado no mesmo "
                        "arquivo; a config declara um modelo, mas a chamada referencia outro slug "
                        "literal (CB-08). Reduz a confiança das dimensões afetadas."
                    ),
                    evidence=[ma.evidence, cfg.evidence],  # ambos os lados (RNF-07)
                )
            )
    return findings


def _flow_contradictions(tsm: TargetStaticModel) -> list[Finding]:
    known: set[str] = set()
    for e in tsm.edges:
        known.add(e.source.lower())
        known.add(e.target.lower())
    known |= {a.name.lower() for a in tsm.agents}
    known |= {t.name.lower() for t in tsm.tools}

    findings: list[Finding] = []
    seen: set[str] = set()
    for p in tsm.prompts:
        for m in _ROUTE.finditer(p.text):
            dest = m.group(1)
            low = dest.lower()
            if low in known or low in seen:
                continue
            # Só sinaliza se o alvo TEM grafo (há arestas/agentes) — senão não há "fluxo" a violar.
            if not tsm.edges and not tsm.agents:
                continue
            seen.add(low)
            findings.append(
                Finding(
                    finding_type=FindingType.CONTRADICAO_FLUXO_PROMPT,
                    urgency=Urgency.IMPORTANTE,
                    statement=(
                        f"Prompt '{p.name}' encaminha para '{dest}', que não existe como "
                        "nó/aresta/agente no grafo do alvo."
                    ),
                    reasoning=(
                        "O prompt assume um fluxo de roteamento que o código não implementa: o "
                        "destino citado não aparece nas arestas nem entre os agentes (CB-08)."
                    ),
                    evidence=[
                        p.evidence,
                        EvidenceRef(
                            file_path=p.evidence.file_path,
                            symbol=f"<fluxo:{dest}>",
                            component_kind="edge",
                        ),
                    ],
                )
            )
    return findings


def detect_contradictions(tsm: TargetStaticModel) -> list[Finding]:
    """Achados de contradição interna do artefato, por dimensão dona (CB-08)."""
    return _model_contradictions(tsm) + _flow_contradictions(tsm)
