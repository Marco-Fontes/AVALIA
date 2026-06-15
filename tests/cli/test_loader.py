"""Testes do loader de diretório-alvo (porta de entrada do MVP).

Nada é importado/executado do alvo (RNF-05) — só leitura de texto.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from avalia.loader import read_target_directory

pytestmark = pytest.mark.fast


def test_reads_python_text_and_skips_junk_and_binary(tmp_path: Path):
    (tmp_path / "main.py").write_text("def agent(state):\n    return state\n", encoding="utf-8")
    (tmp_path / "prompts.py").write_text("SYSTEM_PROMPT = 'oi'\n", encoding="utf-8")
    # ruído: diretórios ignorados
    (tmp_path / ".git").mkdir()
    (tmp_path / ".git" / "config").write_text("[core]\n", encoding="utf-8")
    (tmp_path / "__pycache__").mkdir()
    (tmp_path / "__pycache__" / "x.pyc").write_bytes(b"\x00\x01")
    # binário no topo → pulado (UnicodeDecodeError)
    (tmp_path / "blob.bin").write_bytes(b"\x00\xff\x00\xff")

    files = read_target_directory(tmp_path)
    assert set(files) == {"main.py", "prompts.py"}
    assert "def agent" in files["main.py"]


def test_skips_oversized_files(tmp_path: Path):
    (tmp_path / "huge.py").write_text("x = 1\n" * 10000, encoding="utf-8")
    (tmp_path / "small.py").write_text("y = 2\n", encoding="utf-8")
    files = read_target_directory(tmp_path, max_bytes=100)
    assert "small.py" in files and "huge.py" not in files


def test_nested_paths_use_posix_separators(tmp_path: Path):
    sub = tmp_path / "agents"
    sub.mkdir()
    (sub / "planner.py").write_text("def planner(state):\n    return state\n", encoding="utf-8")
    files = read_target_directory(tmp_path)
    assert "agents/planner.py" in files


def test_missing_path_raises(tmp_path: Path):
    with pytest.raises(FileNotFoundError):
        read_target_directory(tmp_path / "does-not-exist")
