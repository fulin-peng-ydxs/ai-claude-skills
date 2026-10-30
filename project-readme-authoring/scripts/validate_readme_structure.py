#!/usr/bin/env python3
"""Validate the stable README heading contract."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path


SECTIONS = {
    "zh": [
        ("项目概览", True),
        ("核心能力与适用边界", True),
        ("快速开始", True),
        ("使用说明", True),
        ("API 与 CLI", False),
        ("架构与代码结构", False),
        ("配置与环境变量", False),
        ("数据准备与迁移", False),
        ("开发与验证", True),
        ("部署与运维", False),
        ("故障排查", False),
        ("兼容性", False),
        ("文档导航", True),
        ("贡献指南", False),
        ("许可证与引用", False),
    ],
    "en": [
        ("Overview", True),
        ("Capabilities and Scope", True),
        ("Quick Start", True),
        ("Usage", True),
        ("API and CLI", False),
        ("Architecture and Code Structure", False),
        ("Configuration and Environment Variables", False),
        ("Data Preparation and Migrations", False),
        ("Development and Verification", True),
        ("Deployment and Operations", False),
        ("Troubleshooting", False),
        ("Compatibility", False),
        ("Documentation", True),
        ("Contributing", False),
        ("License and Attribution", False),
    ],
}

PLACEHOLDER_RE = re.compile(r"(?:待补充|TODO\s*:|TBD\s*:)", re.IGNORECASE)


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


def detect_language(titles: list[str]) -> str | None:
    scores = {
        language: sum(title in {name for name, _ in sections} for title in titles)
        for language, sections in SECTIONS.items()
    }
    best = max(scores, key=scores.get)
    return best if scores[best] else None


def has_content(body: str) -> bool:
    return any(
        line.strip() and (kind == "code" or not line.strip().startswith("#"))
        for line, kind in fenced_lines(body)
        if kind != "marker"
    )


def prose_without_fences(body: str) -> str:
    return "\n".join(line for line, kind in fenced_lines(body) if kind == "prose")


def validate(text: str, language: str, custom_structure: bool = False) -> list[str]:
    errors: list[str] = []
    h1, sections = parse_sections(text)
    titles = [title for title, _ in sections]

    if len(h1) != 1:
        errors.append(f"expected exactly one level-1 title, found {len(h1)}")

    if custom_structure:
        if not sections:
            errors.append("expected at least one non-empty level-2 section")
        for title in sorted({title for title in titles if titles.count(title) > 1}):
            errors.append(f"duplicate level-2 section: '{title}'")
        for title, body in sections:
            if not has_content(body):
                errors.append(f"section '{title}' is empty")
            if PLACEHOLDER_RE.search(prose_without_fences(body)):
                errors.append(f"section '{title}' contains placeholder content")
        return errors

    selected_language = detect_language(titles) if language == "auto" else language
    if selected_language is None:
        errors.append("could not detect README contract language")
        return errors

    contract = SECTIONS[selected_language]
    allowed = [name for name, _ in contract]
    required = [name for name, is_required in contract if is_required]

    for title in required:
        count = titles.count(title)
        if count != 1:
            errors.append(f"required section '{title}' must appear once, found {count}")

    for title in sorted({title for title in titles if titles.count(title) > 1}):
        errors.append(f"duplicate level-2 section: '{title}'")

    for title in [title for title in titles if title not in allowed]:
        errors.append(f"unexpected level-2 section: '{title}'")

    ordered = [title for title in titles if title in allowed]
    if ordered != sorted(ordered, key=allowed.index):
        errors.append("level-2 sections do not follow the contract order")

    for title, body in sections:
        if title in allowed and not has_content(body):
            errors.append(f"section '{title}' is empty")
        if PLACEHOLDER_RE.search(prose_without_fences(body)):
            errors.append(f"section '{title}' contains placeholder content")

    return errors


def self_test() -> int:
    # Markdown examples may contain shorter or different fence markers.
    for opening, inner, closing in [("````markdown", "```python", "````"), ("~~~", "```", "~~~"), ("````", "```", "`````")]:
        sample = f"# Title\n## Real\n{opening}\n{inner}\n## Example\nTODO: code\n{closing}\n## Next\nText.\n"
        _, parsed = parse_sections(sample)
        if [title for title, _ in parsed] != ["Real", "Next"]:
            print("self-test failed: fenced heading parsed as a section", file=sys.stderr)
            return 1
        code_body = parsed[0][1]
        if not has_content(code_body) or "TODO:" in prose_without_fences(code_body):
            print("self-test failed: fenced content classified as prose", file=sys.stderr)
            return 1
    if has_content("```\n```") or prose_without_fences("```\ncode\n```\nTODO: prose") != "TODO: prose":
        print("self-test failed: fence boundary misclassified", file=sys.stderr)
        return 1
    valid_zh = """# Demo

定位。

## 项目概览
概览。
## 核心能力与适用边界
能力。
## 快速开始
步骤。
## 使用说明
说明。
## 开发与验证
验证。
## 文档导航
导航。
"""
    valid_en = """# Demo

Purpose.

## Overview
Overview.
## Capabilities and Scope
Capabilities.
## Quick Start
Steps.
## Usage
Usage.
## Development and Verification
Verification.
## Documentation
Documentation.
"""
    invalid_missing = valid_zh.replace("## 快速开始\n步骤。\n", "")
    invalid_order = valid_zh.replace(
        "## 项目概览\n概览。\n## 核心能力与适用边界\n能力。",
        "## 核心能力与适用边界\n能力。\n## 项目概览\n概览。",
    )
    if validate(valid_zh, "zh") or validate(valid_en, "en"):
        print("self-test failed: valid fixture rejected", file=sys.stderr)
        return 1
    if not validate(invalid_missing, "zh") or not validate(invalid_order, "zh"):
        print("self-test failed: invalid fixture accepted", file=sys.stderr)
        return 1
    if validate("# Custom\n\n## Custom Section\nContent.\n", "auto", True):
        print("self-test failed: valid custom fixture rejected", file=sys.stderr)
        return 1
    print("self-test passed")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", nargs="?", help="README path")
    parser.add_argument("--language", choices=("auto", "zh", "en"), default="auto")
    parser.add_argument("--custom-structure", action="store_true")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()

    if args.self_test:
        return self_test()
    if not args.path:
        parser.error("path is required unless --self-test is used")

    path = Path(args.path)
    if not path.is_file():
        print(f"ERROR: missing file: {path}", file=sys.stderr)
        return 1
    errors = validate(path.read_text(encoding="utf-8"), args.language, args.custom_structure)
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1
    print(f"README structure valid: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
