"""T4.5 / T-107 — detecção de harness por config de teste / CI e por caminho (detector único).

Sinergia com a Frente 1: configs já são parseados. T-107 (v1.4): ingestão, TSM e priorização usam
as mesmas funções de `extract/harness.py`, por partes do caminho. Rastreabilidade: RF-DIM-Q1, CA-06.
"""

from __future__ import annotations

import pytest

from avalia.config.evaluator_config import EvaluatorConfig
from avalia.domain.submission import Submission, TargetMetadata
from avalia.extract.harness import detect_harness, is_harness_path
from avalia.extract.prioritize import rank_files
from avalia.extract.tsm_builder import build_tsm
from avalia.ingest import ingest_validate

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


# ---------- T-107 (v1.4) — detector único, por partes do caminho ----------


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        # os 4 casos que falharam na auditoria de 2026-09-22
        ("latest_version.py", False),  # antes: substring "test_" → falso positivo
        ("tests/helpers.py", True),  # antes: "/tests/" exigia barra antes → falso negativo
        ("src/foo.test.ts", True),  # antes: só convenções Python
        (r"src\tests\helpers.py", True),  # separador Windows
        # convenções cobertas
        ("pkg/test/util.py", True),
        ("web/__tests__/app.jsx", True),
        ("test_app.py", True),
        ("app_test.py", True),
        ("src/conftest.py", True),
        ("ui/button.spec.tsx", True),
        # não-testes que substrings enganavam
        ("contest.py", False),
        ("src/attestation.py", False),
        ("docs/testing_guide.md", False),
        ("src/app.spec.md", False),
        ("src/app.py", False),
    ],
)
def test_is_harness_path(path, expected):
    assert is_harness_path(path) is expected


def test_js_test_runner_config_and_ci_signal_harness():
    assert detect_harness({"app.ts": "x", "vitest.config.ts": "export default {}"})
    wf = "jobs:\n  t:\n    steps:\n      - run: npm test\n"
    assert detect_harness({"app.ts": "x", ".github/workflows/ci.yaml": wf})


def _inventory_has_harness(files: dict[str, str]) -> bool:
    sub = Submission(
        artifact_files=files,
        metadata=TargetMetadata(target_id="t", version="1"),
        config=EvaluatorConfig(),
    )
    return "harness" in ingest_validate(sub).inventory.present


@pytest.mark.parametrize(
    "files",
    [
        {"app.py": _APP, "latest_version.py": _APP},
        {"app.py": _APP, "tests/helpers.py": _APP},
        {"app.ts": "x", "src/foo.test.ts": "x"},
        {"app.py": _APP, "pyproject.toml": "[tool.pytest.ini_options]\n"},
        {"app.py": _APP},
    ],
)
def test_ingest_inventory_agrees_with_tsm(files):
    # antes eram heurísticas diferentes; agora o inventário (RF-01) e o TSM (Q1) concordam
    assert _inventory_has_harness(files) is build_tsm(files).has_harness


def test_prioritization_uses_same_path_rule():
    files = {
        "latest_version.py": "SYSTEM_PROMPT = 'x'\n",
        "tests/helpers.py": "SYSTEM_PROMPT = 'x'\n",
    }
    # mesmo conteúdo: só o arquivo de teste de verdade cai para o sinal baixo de harness
    assert rank_files(files) == ["latest_version.py", "tests/helpers.py"]
