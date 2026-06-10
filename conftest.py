"""Configuração de testes: torna o pacote `avalia` importável a partir de src/ (layout src).

Não importa, instancia nem executa nenhum ALVO (RNF-05 / S-04) — apenas ajusta o sys.path
para o código do próprio AVALIA, antes que o pacote esteja instalado em modo editável.
"""

from __future__ import annotations

import sys
from pathlib import Path

_SRC = Path(__file__).parent / "src"
if _SRC.exists() and str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))
