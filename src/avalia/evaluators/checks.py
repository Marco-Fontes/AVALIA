"""T-301 — Framework de check determinístico (TSM → `CheckOutcome`).

Checks puros sobre o TSM, sem LLM: regra → resultado. O `deterministic_hash` é derivado dos
fatos salientes por SHA-256 sobre serialização canônica → **bit-idêntico** entre execuções
(RNF-01/RF-26/CA-14). Não usa o hash() salgado do Python.

Rastreabilidade: RNF-01, RF-26; CA-14.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from avalia.domain.contracts import CheckOutcome
from avalia.domain.enums import CheckNature
from avalia.domain.evidence import EvidenceRef


def deterministic_hash(check_id: str, facts: Any) -> str:
    """SHA-256 de (check_id, fatos) em forma canônica (ordenada) — estável entre processos."""
    payload = json.dumps(
        {"check": check_id, "facts": facts}, sort_keys=True, ensure_ascii=False, default=str
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def deterministic_outcome(
    check_id: str,
    *,
    passed: bool,
    facts: Any,
    evidence: list[EvidenceRef] | None = None,
) -> CheckOutcome:
    """Constrói um `CheckOutcome` determinístico já com o hash estável."""
    return CheckOutcome(
        check_id=check_id,
        nature=CheckNature.DETERMINISTICO,
        passed=passed,
        evidence=evidence or [],
        deterministic_hash=deterministic_hash(check_id, facts),
    )
