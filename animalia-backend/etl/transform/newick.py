"""Minimal Newick parser for Open Tree of Life output.

Handles quoted labels ('' escapes a quote), unquoted labels (underscores become
spaces, per the Newick spec) and branch lengths (parsed and ignored; Open Tree's
synthetic tree has none). Iterative, so deep single-child chains are fine.
"""

from __future__ import annotations

from dataclasses import dataclass, field


class NewickError(ValueError):
    """The text is not valid Newick."""


@dataclass
class NewickNode:
    label: str | None = None
    children: list[NewickNode] = field(default_factory=list)


_DELIMITERS = set("(),:;")


def parse(text: str) -> NewickNode:
    root = NewickNode()
    current = root
    stack: list[NewickNode] = []
    i = 0
    n = len(text)
    while i < n:
        char = text[i]
        if char.isspace():
            i += 1
        elif char == "(":
            child = NewickNode()
            current.children.append(child)
            stack.append(current)
            current = child
            i += 1
        elif char == ",":
            if not stack:
                raise NewickError(f"',' outside parentheses at offset {i}")
            sibling = NewickNode()
            stack[-1].children.append(sibling)
            current = sibling
            i += 1
        elif char == ")":
            if not stack:
                raise NewickError(f"unbalanced ')' at offset {i}")
            current = stack.pop()
            i += 1
        elif char == ":":
            i += 1
            while i < n and text[i] not in _DELIMITERS:
                i += 1
        elif char == ";":
            break
        elif char == "'":
            label, i = _read_quoted(text, i)
            current.label = label
        else:
            start = i
            while i < n and text[i] not in _DELIMITERS:
                i += 1
            current.label = text[start:i].strip().replace("_", " ")
    if stack:
        raise NewickError("unbalanced '(': input ended inside a clade")
    return root


def _read_quoted(text: str, start: int) -> tuple[str, int]:
    """Read a quoted label starting at ``start``; return it and the next offset."""
    out: list[str] = []
    i = start + 1
    while i < len(text):
        if text[i] == "'":
            if i + 1 < len(text) and text[i + 1] == "'":
                out.append("'")
                i += 2
                continue
            return "".join(out), i + 1
        out.append(text[i])
        i += 1
    raise NewickError(f"unterminated quoted label at offset {start}")
