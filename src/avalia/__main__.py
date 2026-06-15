"""Permite `python -m avalia <caminho>` — delega à CLI (não executa o alvo, RNF-05)."""

from __future__ import annotations

from avalia.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
