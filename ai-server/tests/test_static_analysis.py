"""
Static analysis guards.

Two classes of defect in this codebase are invisible to the test suite because
they live on code paths the tests do not reach — ``job_service`` alone is only
~30% covered. Both are cheap to detect statically:

* **F821 undefined name.** A misspelled or extracted-away local raises
  ``NameError`` only when that branch actually executes. The audit found one in
  ``retry_service`` (a call to a function that was never defined, which left jobs
  stuck in ``pending_crop`` forever) and the refactor briefly introduced fourteen
  more by moving locals into helpers.
* **F841 unused variable.** Usually the residue of a removed feature, and
  occasionally a real bug where a computed value was meant to be used.

These run through ruff, which is already a declared dev dependency. The test skips
rather than fails when ruff is absent, so a minimal install can still run the
suite.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

APP_ROOT = Path(__file__).resolve().parents[1]
PACKAGE = APP_ROOT / "app"

requires_ruff = pytest.mark.skipif(
    shutil.which("ruff") is None and not (Path(sys.executable).parent / "ruff").exists(),
    reason="ruff is not installed (pip install -r requirements-dev.txt)",
)


def run_ruff(*rules: str) -> tuple[int, str]:
    """
    Run ruff over the application package for the given rule codes.

    Args:
        rules: Ruff rule selectors, e.g. ``"F821"``.

    Returns:
        Tuple of (exit status, combined output).
    """
    executable = shutil.which("ruff") or str(Path(sys.executable).parent / "ruff")
    completed = subprocess.run(  # noqa: S603 — fixed argument vector, no shell
        [
            executable,
            "check",
            str(PACKAGE),
            "--select",
            ",".join(rules),
            "--no-cache",
            "--output-format",
            "concise",
        ],
        capture_output=True,
        text=True,
        cwd=APP_ROOT,
        check=False,
    )
    return completed.returncode, (completed.stdout + completed.stderr).strip()


@requires_ruff
def test_no_undefined_names() -> None:
    """
    Every name referenced in app/ must be defined.

    An undefined name is a latent NameError that only fires when its branch runs.
    """
    status, output = run_ruff("F821")

    assert status == 0, f"undefined names found:\n{output}"


@requires_ruff
def test_no_unused_variables() -> None:
    """
    A variable that is assigned and never read is either dead code or a bug where
    the computed value was meant to be used.
    """
    status, output = run_ruff("F841")

    assert status == 0, f"unused variables found:\n{output}"


@requires_ruff
def test_no_unused_imports() -> None:
    """Unused imports keep deleted modules alive and slow down startup."""
    status, output = run_ruff("F401")

    assert status == 0, f"unused imports found:\n{output}"


@requires_ruff
def test_no_bare_except_pass() -> None:
    """
    ``try: ... except: pass`` discards the error entirely.

    The audit removed 18 of these; this keeps them from returning. Narrow handlers
    that log are fine — the rule only targets a silent ``pass``.
    """
    status, output = run_ruff("S110")

    assert status == 0, f"silently swallowed exceptions found:\n{output}"


@requires_ruff
def test_no_mutable_default_arguments() -> None:
    """A mutable default is shared across every call and accumulates state."""
    status, output = run_ruff("B006")

    assert status == 0, f"mutable default arguments found:\n{output}"


@requires_ruff
def test_no_f_string_in_logging_calls_without_placeholders() -> None:
    """An f-string with no placeholder is a sign of an edit that lost its data."""
    status, output = run_ruff("F541")

    assert status == 0, f"f-strings without placeholders found:\n{output}"


@requires_ruff
def test_no_comparison_to_none_with_equality() -> None:
    """``== None`` is not the same test as ``is None`` for objects with __eq__."""
    status, output = run_ruff("E711")

    assert status == 0, f"equality comparison to None found:\n{output}"


@requires_ruff
def test_no_unreachable_code_after_return() -> None:
    """
    identify.py once carried ~180 lines after an unconditional raise. Unreachable
    code is code nobody maintains but everybody reads.
    """
    status, output = run_ruff("F811", "B012")

    assert status == 0, f"unreachable or shadowed definitions found:\n{output}"
