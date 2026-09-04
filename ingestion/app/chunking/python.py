"""Chunking Python by symbol: one chunk per class or function.

A symbol is the unit a reader asks about and the unit `read_file(symbol=...)`
serves, so chunk boundaries follow the AST rather than a character count. A
class too large for one chunk is split per method, each still labelled with
the class it came from.
"""

from __future__ import annotations

import ast

from .base import MAX_CHARS, MIN_CHARS, Chunk

_DEFS = (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)


def chunk_python(text: str, path: str) -> list[Chunk]:
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return []

    lines = text.splitlines()
    chunks: list[Chunk] = []
    module_doc = ast.get_docstring(tree)

    if module_doc and len(module_doc) >= MIN_CHARS:
        chunks.append(
            Chunk(
                text=module_doc,
                start_line=1,
                end_line=module_doc.count("\n") + 1,
                symbol="<module>",
                symbol_kind="module",
                context_header=f"{path} > module docstring",
            )
        )

    for node in tree.body:
        if not isinstance(node, _DEFS):
            continue
        if isinstance(node, ast.ClassDef):
            chunks.extend(_chunk_class(node, lines, path))
        else:
            chunks.append(_chunk_function(node, lines, path, parent=None))

    return [c for c in chunks if len(c.text) >= MIN_CHARS]


def _span(node: ast.AST, lines: list[str]) -> tuple[str, int, int]:
    start = min(
        [node.lineno] + [d.lineno for d in getattr(node, "decorator_list", [])]
    )
    end = getattr(node, "end_lineno", node.lineno) or node.lineno
    return "\n".join(lines[start - 1 : end]), start, end


def _chunk_class(node: ast.ClassDef, lines: list[str], path: str) -> list[Chunk]:
    out: list[Chunk] = []
    methods = [
        n
        for n in node.body
        if isinstance(n, ast.FunctionDef | ast.AsyncFunctionDef)
    ]
    signatures = "\n".join(f"    def {m.name}(...)" for m in methods)
    _, start, end = _span(node, lines)

    if methods:
        first = min(
            min([m.lineno] + [d.lineno for d in m.decorator_list])
            for m in methods
        )
        header_end = first - 1
    else:
        header_end = end
    header_src = "\n".join(lines[start - 1 : header_end])
    if len(header_src) > MAX_CHARS:
        header_src = header_src[:MAX_CHARS] + "\n    # ... truncated"

    summary = header_src
    if signatures:
        summary += f"\n\n    # methods:\n{signatures}"
    summary = summary.strip()
    out.append(
        Chunk(
            text=summary,
            start_line=start,
            end_line=end,
            symbol=node.name,
            symbol_kind="class",
            context_header=f"{path} > class {node.name}",
        )
    )

    for method in methods:
        out.append(_chunk_function(method, lines, path, parent=node.name))
    return out


def _chunk_function(
    node: ast.FunctionDef | ast.AsyncFunctionDef,
    lines: list[str],
    path: str,
    parent: str | None,
) -> Chunk:
    body, start, end = _span(node, lines)
    qualified = f"{parent}.{node.name}" if parent else node.name
    header = (
        f"{path} > " + (f"class {parent} > " if parent else "") + f"def {node.name}"
    )

    if len(body) > MAX_CHARS:
        body = body[:MAX_CHARS] + "\n    # ... truncated, use read_file for full source"

    return Chunk(
        text=body,
        start_line=start,
        end_line=end,
        symbol=qualified,
        symbol_kind="function",
        context_header=header,
    )
