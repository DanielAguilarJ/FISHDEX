"""
Docstring accuracy.

A docstring that names parameters the function does not have is worse than no
docstring: it sends the reader looking for something that is not there, and it
survives every refactor that renames an argument.

This audit added ~48 docstrings and got five of them wrong that way — documenting
``in_ch``/``out_ch``/``k`` for a constructor whose parameters are
``in_channels``/``out_channels``/``kernel_size``, and similar. Only writing a test
against the real signatures caught it.

The checks here are structural, not stylistic: they verify that documentation and
code agree, and that public API surfaces are documented at all.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

PACKAGE = Path(__file__).resolve().parents[1] / "app"

# Reference data: 15k lines of coordinate literals with no logic to document.
EXCLUDED = {"czech_areas.py"}

SECTION_HEADINGS = (
    "Returns:",
    "Raises:",
    "Yields:",
    "Example:",
    "Examples:",
    "Note:",
    "Notes:",
    "Attributes:",
    "Warning:",
)


def python_modules() -> list[Path]:
    """Return every module under app/ that should be checked."""
    return sorted(p for p in PACKAGE.rglob("*.py") if p.name not in EXCLUDED)


def documented_parameters(docstring: str) -> set[str]:
    """
    Extract the parameter names listed under an ``Args:`` section.

    Args:
        docstring: The function's docstring.

    Returns:
        The set of documented parameter names, empty when there is no Args block.
    """
    if "Args:" not in docstring:
        return set()

    block = docstring.split("Args:", 1)[1]
    for heading in SECTION_HEADINGS:
        block = block.split(heading, 1)[0]
    return set(re.findall(r"^\s{4,}(\w+):", block, re.MULTILINE))


def real_parameters(node: ast.FunctionDef | ast.AsyncFunctionDef) -> set[str]:
    """
    Collect every parameter name a function actually accepts.

    Args:
        node: The function definition.

    Returns:
        Parameter names, including ``*args``/``**kwargs`` and keyword-only ones.
    """
    names = {
        arg.arg
        for arg in node.args.posonlyargs + node.args.args + node.args.kwonlyargs
    }
    if node.args.vararg:
        names.add(node.args.vararg.arg)
    if node.args.kwarg:
        names.add(node.args.kwarg.arg)
    return names


def iter_functions():
    """Yield (path, function node, docstring) for every documented function."""
    for path in python_modules():
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError:  # pragma: no cover — a syntax error fails elsewhere
            continue
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                yield path, node, ast.get_docstring(node)


# ─────────────────────────────────────────────────────────────────────────────
# Accuracy
# ─────────────────────────────────────────────────────────────────────────────
def test_docstrings_only_document_parameters_that_exist() -> None:
    """
    Every name under ``Args:`` must be a real parameter.

    Catches the copy-paste-then-rename failure mode, where documentation drifts
    away from the signature silently.
    """
    problems: list[str] = []
    for path, node, docstring in iter_functions():
        if not docstring:
            continue
        bogus = documented_parameters(docstring) - real_parameters(node) - {"self", "cls"}
        if bogus:
            problems.append(
                f"{path.relative_to(PACKAGE.parent)}:{node.lineno} {node.name}() "
                f"documents non-existent {sorted(bogus)}"
            )

    assert problems == [], "docstrings disagree with signatures:\n" + "\n".join(problems)


# ─────────────────────────────────────────────────────────────────────────────
# Coverage
# ─────────────────────────────────────────────────────────────────────────────
def test_every_function_has_a_docstring() -> None:
    """Held at 100% by this audit; this keeps it there."""
    missing = [
        f"{path.relative_to(PACKAGE.parent)}:{node.lineno} {node.name}()"
        for path, node, docstring in iter_functions()
        if not docstring
    ]

    assert missing == [], "functions without a docstring:\n" + "\n".join(missing)


def test_every_class_has_a_docstring() -> None:
    missing: list[str] = []
    for path in python_modules():
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef) and not ast.get_docstring(node):
                missing.append(
                    f"{path.relative_to(PACKAGE.parent)}:{node.lineno} {node.name}"
                )

    assert missing == [], "classes without a docstring:\n" + "\n".join(missing)


def test_every_module_has_a_docstring() -> None:
    """A module docstring is where the 'why does this exist' answer lives."""
    missing = []
    for path in python_modules():
        if path.name == "__init__.py" and path.stat().st_size == 0:
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError:
            continue
        if not ast.get_docstring(tree):
            missing.append(str(path.relative_to(PACKAGE.parent)))

    assert missing == [], "modules without a docstring:\n" + "\n".join(missing)


# ─────────────────────────────────────────────────────────────────────────────
# Return annotations
# ─────────────────────────────────────────────────────────────────────────────
def test_functions_documenting_a_return_value_declare_a_return_type() -> None:
    """
    If a docstring promises a ``Returns:`` section, the signature should say what
    type it is — otherwise the reader has to infer it from the body.
    """
    problems = [
        f"{path.relative_to(PACKAGE.parent)}:{node.lineno} {node.name}()"
        for path, node, docstring in iter_functions()
        if docstring and "Returns:" in docstring and node.returns is None
    ]

    assert problems == [], (
        "functions documenting a return value without a return annotation:\n"
        + "\n".join(problems)
    )


def test_functions_documenting_raises_actually_raise() -> None:
    """
    A documented ``Raises:`` with no ``raise`` anywhere in the body is stale
    documentation from a removed error path.
    """
    problems = []
    for path, node, docstring in iter_functions():
        if not docstring or "Raises:" not in docstring:
            continue
        raises = any(isinstance(child, ast.Raise) for child in ast.walk(node))
        calls_something = any(isinstance(child, ast.Call) for child in ast.walk(node))
        # A function may legitimately document exceptions propagated by a callee.
        if not raises and not calls_something:
            problems.append(
                f"{path.relative_to(PACKAGE.parent)}:{node.lineno} {node.name}()"
            )

    assert problems == [], (
        "functions documenting Raises: without raising or calling anything:\n"
        + "\n".join(problems)
    )


@pytest.mark.parametrize("module", [p.name for p in python_modules()])
def test_module_parses(module: str) -> None:
    """Sanity check that every module under app/ is syntactically valid."""
    path = next(p for p in python_modules() if p.name == module)

    ast.parse(path.read_text(encoding="utf-8"))
