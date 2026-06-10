"""T-006 — Loader validado de `weight_profiles.yaml`.

Carrega os perfis de peso (dados) em `WeightProfile`, validando que cada perfil:
(a) usa apenas dimensões válidas e cobre as 7; (b) soma ≈ 1 (RF-21). O perfil 'neutro' é o
fallback quando a classificação é incerta (CA-04/CB-09).

Não executa o ALVO — só lê configuração do próprio AVALIA. Rastreabilidade: RF-16, RNF-06.
"""

from __future__ import annotations

from pathlib import Path

import yaml

from avalia.domain.enums import Dimension
from avalia.domain.weights import WeightProfile, WeightSource

_DEFAULT_PATH = Path(__file__).with_name("weight_profiles.yaml")
NEUTRAL_PROFILE = "neutro"


def load_weight_profiles(path: Path | None = None) -> dict[str, WeightProfile]:
    """Lê e valida todos os perfis. Erro descritivo se algum não somar 1 ou tiver chave inválida."""
    src = path or _DEFAULT_PATH
    raw = yaml.safe_load(src.read_text(encoding="utf-8")) or {}
    if not isinstance(raw, dict) or not raw:
        raise ValueError(f"weight_profiles vazio ou malformado em {src}.")

    profiles: dict[str, WeightProfile] = {}
    for name, mapping in raw.items():
        if not isinstance(mapping, dict):
            raise ValueError(f"Perfil '{name}' deve mapear dimensão→peso.")
        try:
            weights = {Dimension(dim): float(w) for dim, w in mapping.items()}
        except ValueError as exc:
            raise ValueError(f"Perfil '{name}' tem dimensão/peso inválido: {exc}.") from exc
        missing = set(Dimension) - set(weights)
        if missing:
            raise ValueError(
                f"Perfil '{name}' não cobre todas as dimensões; faltam: "
                f"{sorted(d.value for d in missing)}."
            )
        source = WeightSource.FALLBACK_NEUTRO if name == NEUTRAL_PROFILE else WeightSource.INFERIDO
        # WeightProfile valida não-negatividade e soma≈1 (RF-21).
        profiles[name] = WeightProfile(source=source, weights=weights, normalized=True)

    if NEUTRAL_PROFILE not in profiles:
        raise ValueError(f"Perfil obrigatório '{NEUTRAL_PROFILE}' ausente.")
    return profiles
