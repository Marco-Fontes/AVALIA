"""T4.5 — detecção de harness por config de teste / CI, não só por `test_*`.

Sinergia com a Frente 1: configs já são parseados. Rastreabilidade: RF-DIM-Q1.
"""

from __future__ import annotations

import pytest

from avalia.extract.tsm_builder import build_tsm

pytestmark = pytest.mark.fast

_APP = "X = 1\n"


def test_harness_via_pyproject_tool_pytest():
    tsm = build_tsm({"app.py": _APP, "pyproject.toml": "[tool.pytest.ini_options]\naddopts='-q'\n"})
    assert tsm.has_harness


def test_harness_via_conftest():
    assert build_tsm({"app.py": _APP, "conftest.py": "import pytest\n"}).has_harness


def test_harness_via_tox_ini():
    assert build_tsm({"app.py": _APP, "tox.ini": "[tox]\nenvlist=py312\n"}).has_harness


def test_harness_via_github_workflow_with_pytest():
    wf = "jobs:\n  test:\n    steps:\n      - run: pytest -q\n"
    assert build_tsm({"app.py": _APP, ".github/workflows/ci.yml": wf}).has_harness


def test_harness_via_tests_dir():
    assert build_tsm(
        {"src/app.py": _APP, "tests/test_app.py": "def test_x():\n    pass\n"}
    ).has_harness


def test_no_harness_when_absent():
    assert not build_tsm({"app.py": _APP, "pyproject.toml": "[project]\nname='x'\n"}).has_harness
