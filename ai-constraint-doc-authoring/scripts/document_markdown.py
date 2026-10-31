"""Shared Markdown parsing for document validators; no document-specific rules."""

from __future__ import annotations

import re


def fenced_lines(text: str):
    """Classify lines using matching fence characters and opening fence length."""
    fence = ""
    for line in text.splitlines():
        if fence:
            if re.fullmatch(r" {0,3}" + re.escape(fence[0]) + "{" + str(len(fence)) + r",}[ \t]*", line):
                fence = ""
                yield line, "marker"
            else:
                yield line, "code"
            continue
        opening = re.match(r"^ {0,3}(`{3,}|~{3,})(.*)$", line)
        if opening and not (opening[1][0] == "`" and "`" in opening[2]):
            fence = opening[1]
            yield line, "marker"
        else:
            yield line, "prose"


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


def has_content(body: str) -> bool:
    return any(
        line.strip() and (kind == "code" or not line.strip().startswith("#"))
        for line, kind in fenced_lines(body)
        if kind != "marker"
    )


def prose_without_fences(body: str) -> str:
    return "\n".join(line for line, kind in fenced_lines(body) if kind == "prose")
