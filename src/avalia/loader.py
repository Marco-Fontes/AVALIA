"""Loader de diretório-alvo (porta de entrada do MVP de uso).

Varre o repositório de um sistema-alvo e devolve o mapa `caminho_relativo → texto-fonte` que
alimenta a `Submission`. Apenas LEITURA estática de texto: jamais importa, instancia ou executa
o alvo (RNF-05/S-04). Pula diretórios de ruído (controle de versão, caches, dependências) e
arquivos binários/muito grandes — o resto é decidido a jusante (legibilidade T-104, amostragem
T-105).

Rastreabilidade: RF-01, S-01; RNF-05/S-04.
"""

from __future__ import annotations

from pathlib import Path

# Diretórios de ruído (não fazem parte do artefato avaliável).
_SKIP_DIRS = frozenset(
    {
        ".git",
        ".hg",
        ".svn",
        "__pycache__",
        ".mypy_cache",
        ".ruff_cache",
        ".pytest_cache",
        ".tox",
        ".eggs",
        "node_modules",
        ".venv",
        "venv",
        "env",
        ".idea",
        ".vscode",
        "dist",
        "build",
        "site-packages",
        ".next",
        ".cache",
    }
)
_MAX_BYTES = 512 * 1024  # arquivos maiores são pulados (provável dado/binário, não código)


def _is_skippable_dir(rel_parts: tuple[str, ...]) -> bool:
    return any(part in _SKIP_DIRS for part in rel_parts)


def _is_test_fixture(rel_parts: tuple[str, ...]) -> bool:
    """Diretório de FIXTURES sob `tests/`: dados/alvos sintéticos (muitas vezes adversariais —
    loop sem teto, prompts RAG, contradições), NÃO a lógica do sistema. Avaliá-los poluiria o
    laudo. Mantém `tests/` no escopo (harness — RF-DIM-Q1), mas exclui os fixtures sintéticos.
    Conservador: só pula `fixtures` que esteja DENTRO de um diretório de teste."""
    lower = [p.lower() for p in rel_parts]
    for i, part in enumerate(lower):
        if part in ("fixtures", "fixture", "__fixtures__") and any(
            t in ("test", "tests") for t in lower[:i]
        ):
            return True
    return False


def read_target_directory(root: str | Path, *, max_bytes: int = _MAX_BYTES) -> dict[str, str]:
    """Lê os arquivos-texto do diretório-alvo → `{caminho_relativo: conteúdo}` (RNF-05: só texto).

    Aceita também um único arquivo. Caminhos são relativos à raiz, com separador `/`.
    """
    root_path = Path(root)
    if not root_path.exists():
        raise FileNotFoundError(f"Caminho do alvo não encontrado: {root}")

    files = [root_path] if root_path.is_file() else sorted(root_path.rglob("*"))
    base = root_path.parent if root_path.is_file() else root_path

    out: dict[str, str] = {}
    for path in files:
        if not path.is_file():
            continue
        rel = path.relative_to(base)
        dir_parts = rel.parts[:-1]
        if _is_skippable_dir(dir_parts) or _is_test_fixture(dir_parts):
            continue
        try:
            if path.stat().st_size > max_bytes:
                continue
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue  # binário/ilegível na leitura → fora do pacote textual
        out[rel.as_posix()] = text
    return out
