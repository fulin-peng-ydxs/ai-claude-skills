"""Shared Markdown parsing for document validators; no document-specific rules."""

from __future__ import annotations

import re

FIELD_LINE = re.compile(r'^(?:- )?([^\n：:]+[：:])(.*)$')


def table_cells(line: str) -> list[str]:
    """Split Markdown table cells, preserving escaped pipes in values."""
    cells = []
    current = []
    escaped = False
    for character in line.strip():
        if character == '|' and not escaped:
            cells.append(''.join(current).strip())
            current = []
        else:
            current.append(character)
        escaped = character == '\\' and not escaped
    cells.append(''.join(current).strip())
    if cells and not cells[0]:
        cells.pop(0)
    if cells and not cells[-1]:
        cells.pop()
    return cells


def fenced_lines(text: str, *, field_continuations: bool = False):
    """Classify original lines, optionally relative to a field's continuation.

    Template fields own a two-space continuation container. Remove that
    container only for fence recognition; returned lines and offsets stay
    unchanged so source records, ownership checks and diagnostics agree.
    Normal Markdown callers keep the original document-relative behavior.
    """
    fence = ""
    in_field = False
    for line in text.splitlines():
        if not fence and line.strip() and len(line) - len(line.lstrip(' ')) < 2:
            in_field = field_continuations and bool(FIELD_LINE.match(line))
        relative = line[2:] if in_field and line.startswith('  ') else line
        if fence:
            within_container = not in_field or line.startswith('  ')
            if within_container and re.fullmatch(r" {0,3}" + re.escape(fence[0]) + "{" + str(len(fence)) + r",}[ \t]*", relative):
                fence = ""
                yield line, "marker"
            else:
                yield line, "code"
            continue
        opening = re.match(r"^ {0,3}(`{3,}|~{3,})(.*)$", relative)
        if opening and not (opening[1][0] == "`" and "`" in opening[2]):
            fence = opening[1]
            yield line, "marker"
        else:
            yield line, "prose"


def fences_closed(text: str, *, field_continuations: bool = False) -> bool:
    """Require explicit closing fences, using the same matching rules as parsing."""
    return sum(kind == "marker" for _, kind in fenced_lines(text, field_continuations=field_continuations)) % 2 == 0


def parse_sections(text: str) -> tuple[list[str], list[tuple[str, str]]]:
    h1: list[str] = []
    sections: list[tuple[str, list[str]]] = []
    current: list[str] | None = None
    for line, kind in fenced_lines(text):
        if kind != "prose":
            if current is not None:
                current.append(line)
            continue

        match = re.match(r"^(#{1,6})\s+(.+?)\s*$", line)
        if match:
            level = len(match.group(1))
            title = match.group(2).strip().rstrip("#").strip()
            if level == 1:
                h1.append(title)
            elif level == 2:
                current = []
                sections.append((title, current))
            elif current is not None:
                current.append(line)
        elif current is not None:
            current.append(line)

    return h1, [(title, "\n".join(body).strip()) for title, body in sections]


def has_content(body: str, *, field_continuations: bool = False) -> bool:
    return any(
        line.strip() and (kind == "code" or not line.strip().startswith("#"))
        for line, kind in fenced_lines(body, field_continuations=field_continuations)
        if kind != "marker"
    )


def prose_without_fences(body: str, *, field_continuations: bool = False) -> str:
    return "\n".join(line for line, kind in fenced_lines(body, field_continuations=field_continuations) if kind == "prose")
