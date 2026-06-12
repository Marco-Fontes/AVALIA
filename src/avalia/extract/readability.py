"""T-104 — Legibilidade: detecção determinística de arquivos ilegíveis (RF-03, CB-02).

Heurísticas que rodam ANTES/à parte do parse, pegando casos que `ast.parse` não pega
(arquivo binário/compilado por extensão, byte nulo, código ofuscado/minificado que ainda é
Python válido). Arquivo ilegível → não é analisado a fundo e as dimensões dependentes recebem
confiança reduzida (CB-02). Nada executa o alvo (RNF-05): só inspeciona o TEXTO.

Rastreabilidade: RF-03, CB-02; plan §3.1.
"""

from __future__ import annotations

_COMPILED_EXTS = (".pyc", ".pyo", ".so", ".dll", ".pyd", ".exe", ".bin", ".o", ".class")
_MAX_LINE_LEN = 2000  # linha muito longa → minificação/ofuscação
_MIN_SIZE_FOR_MINIFICATION = 800  # só considera minificação em arquivos não-triviais
_NEWLINE_RATIO_FLOOR = 0.002  # < 1 quebra a cada ~500 chars → suspeito de minificação


def _reason_for(path: str, source: str) -> str | None:
    """Razão de ilegibilidade do arquivo, ou None se legível."""
    low = path.replace("\\", "/").lower()
    if low.endswith(_COMPILED_EXTS):
        return f"arquivo compilado/binário (extensão {low.rsplit('.', 1)[-1]})"
    if "\x00" in source:
        return "conteúdo binário (byte nulo no arquivo)"
    if not source.strip():
        return None  # vazio é legível-trivial, não ilegível
    longest = max((len(line) for line in source.splitlines()), default=0)
    if longest > _MAX_LINE_LEN:
        return f"linha de {longest} caracteres — código ofuscado/minificado"
    n = len(source)
    if n >= _MIN_SIZE_FOR_MINIFICATION:
        newlines = source.count("\n")
        if newlines / n < _NEWLINE_RATIO_FLOOR:
            return "densidade de quebras de linha muito baixa — código minificado"
    return None


def unreadable_files(files: dict[str, str]) -> dict[str, str]:
    """Mapa caminho→razão dos arquivos considerados ilegíveis (determinístico)."""
    out: dict[str, str] = {}
    for path, source in files.items():
        reason = _reason_for(path, source)
        if reason is not None:
            out[path] = reason
    return out
