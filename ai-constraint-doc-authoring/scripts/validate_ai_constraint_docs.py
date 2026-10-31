#!/usr/bin/env python3
"""Validate stable AGENTS.md and CLAUDE.md heading contracts."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path


AGENTS_SECTIONS = {
    "zh": [
        "文档职责、适用范围与规则优先级",
        "项目事实与代码结构",
        "变更边界与实现约束",
        "命令与验证",
        "项目特有契约",
        "文档与产物同步",
        "安全、确认门禁与禁止操作",
        "完成标准",
    ],
    "en": [
        "Document Scope and Rule Priority",
        "Project Facts and Code Structure",
        "Change Boundaries and Implementation Constraints",
        "Commands and Verification",
        "Project-Specific Contracts",
        "Documentation and Artifact Synchronization",
        "Safety, Confirmation Gates, and Prohibited Actions",
        "Definition of Done",
    ],
}

CLAUDE_SECTIONS = {
    "zh": [("权威规则入口", True), ("工作方式", True), ("记忆边界", False)],
    "en": [
        ("Authoritative Rule Entry", True),
        ("Working Method", True),
        ("Memory Boundaries", False),
    ],
}

PLACEHOLDER_RE = re.compile(r"(?:待补充|TODO\s*:|TBD\s*:)", re.IGNORECASE)
SHELL_FENCE_RE = re.compile(
    r"^\s*```\s*(?:bash|sh|shell|zsh|fish|powershell|cmd)\b",
    re.MULTILINE | re.IGNORECASE,
)


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


def detect_language(titles: list[str], contracts: dict[str, list[str]]) -> str | None:
    scores = {
        language: sum(title in set(sections) for title in titles)
        for language, sections in contracts.items()
    }
    best = max(scores, key=scores.get)
    return best if scores[best] else None


def validate_custom_structure(text: str, document_name: str) -> list[str]:
    errors: list[str] = []
    h1, sections = parse_sections(text)
    titles = [title for title, _ in sections]

    if len(h1) != 1:
        errors.append(f"{document_name}: expected exactly one level-1 title, found {len(h1)}")
    if not has_content(text):
        errors.append(f"{document_name}: document has no body content")
    if PLACEHOLDER_RE.search(prose_without_fences(text)):
        errors.append(f"{document_name}: document contains placeholder content")
    for title in sorted({title for title in titles if titles.count(title) > 1}):
        errors.append(f"{document_name}: duplicate level-2 section '{title}'")
    for title, body in sections:
        if not has_content(body):
            errors.append(f"{document_name}: section '{title}' is empty")
    return errors


def validate_fixed_sections(
    text: str,
    language: str,
    contracts: dict[str, list[str]],
    document_name: str,
) -> tuple[list[str], str | None]:
    errors: list[str] = []
    h1, sections = parse_sections(text)
    titles = [title for title, _ in sections]

    if len(h1) != 1:
        errors.append(f"{document_name}: expected exactly one level-1 title, found {len(h1)}")

    selected_language = detect_language(titles, contracts) if language == "auto" else language
    if selected_language is None:
        errors.append(f"{document_name}: could not detect contract language")
        return errors, None

    expected = contracts[selected_language]
    for title in expected:
        count = titles.count(title)
        if count != 1:
            errors.append(f"{document_name}: section '{title}' must appear once, found {count}")

    for title in sorted({title for title in titles if titles.count(title) > 1}):
        errors.append(f"{document_name}: duplicate level-2 section '{title}'")

    for title in [title for title in titles if title not in expected]:
        errors.append(f"{document_name}: unexpected level-2 section '{title}'")

    ordered = [title for title in titles if title in expected]
    if ordered != expected:
        errors.append(f"{document_name}: level-2 sections do not follow the contract order")

    for title, body in sections:
        if title in expected and not has_content(body):
            errors.append(f"{document_name}: section '{title}' is empty")
        if PLACEHOLDER_RE.search(prose_without_fences(body)):
            errors.append(f"{document_name}: section '{title}' contains placeholder content")

    return errors, selected_language


def validate_agents(
    text: str, language: str, custom_structure: bool = False
) -> tuple[list[str], str | None]:
    if custom_structure:
        return validate_custom_structure(text, "AGENTS.md"), None
    return validate_fixed_sections(text, language, AGENTS_SECTIONS, "AGENTS.md")


def validate_claude(text: str, language: str, custom_structure: bool = False) -> list[str]:
    contracts = {
        key: [title for title, _ in sections]
        for key, sections in CLAUDE_SECTIONS.items()
    }
    if custom_structure:
        errors = validate_custom_structure(text, "CLAUDE.md")
        if "AGENTS.md" not in text:
            errors.append("CLAUDE.md: must point to AGENTS.md")
        if SHELL_FENCE_RE.search(text):
            errors.append("CLAUDE.md: shell command blocks belong in AGENTS.md")
        return errors

    errors: list[str] = []
    h1, sections = parse_sections(text)
    titles = [title for title, _ in sections]

    if len(h1) != 1:
        errors.append(f"CLAUDE.md: expected exactly one level-1 title, found {len(h1)}")

    selected_language = detect_language(titles, contracts) if language == "auto" else language
    if selected_language is None:
        errors.append("CLAUDE.md: could not detect contract language")
        return errors

    contract = CLAUDE_SECTIONS[selected_language]
    allowed = [title for title, _ in contract]
    required = [title for title, is_required in contract if is_required]

    for title in required:
        count = titles.count(title)
        if count != 1:
            errors.append(f"CLAUDE.md: required section '{title}' must appear once, found {count}")

    for title in sorted({title for title in titles if titles.count(title) > 1}):
        errors.append(f"CLAUDE.md: duplicate level-2 section '{title}'")

    for title in [title for title in titles if title not in allowed]:
        errors.append(f"CLAUDE.md: unexpected level-2 section '{title}'")

    ordered = [title for title in titles if title in allowed]
    if ordered != sorted(ordered, key=allowed.index):
        errors.append("CLAUDE.md: level-2 sections do not follow the contract order")

    for title, body in sections:
        if title in allowed and not has_content(body):
            errors.append(f"CLAUDE.md: section '{title}' is empty")
        if PLACEHOLDER_RE.search(prose_without_fences(body)):
            errors.append(f"CLAUDE.md: section '{title}' contains placeholder content")

    if "AGENTS.md" not in text:
        errors.append("CLAUDE.md: must point to AGENTS.md")
    if SHELL_FENCE_RE.search(text):
        errors.append("CLAUDE.md: shell command blocks belong in AGENTS.md")

    return errors


def validate_repository(
    root: Path, language: str, custom_structure: bool, document: str = "both"
) -> list[str]:
    """Validate only the selected deliverables; the default retains paired checks."""
    errors: list[str] = []
    selected_language = None
    if document in ("agents", "both"):
        path = root / "AGENTS.md"
        if not path.is_file():
            errors.append(f"missing file: {path}")
        else:
            agents_errors, selected_language = validate_agents(
                path.read_text(encoding="utf-8"), language, custom_structure
            )
            errors.extend(agents_errors)
    if document in ("claude", "both"):
        path = root / "CLAUDE.md"
        if not path.is_file():
            errors.append(f"missing file: {path}")
        else:
            claude_language = selected_language if language == "auto" and selected_language else language
            errors.extend(validate_claude(
                path.read_text(encoding="utf-8"), claude_language, custom_structure
            ))
    return errors


def self_test() -> int:
    from tempfile import TemporaryDirectory

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
    agents_zh = """# Demo AI 协作说明

## 文档职责、适用范围与规则优先级
范围。
## 项目事实与代码结构
结构。
## 变更边界与实现约束
约束。
## 命令与验证
命令。
## 项目特有契约
契约。
## 文档与产物同步
同步。
## 安全、确认门禁与禁止操作
安全。
## 完成标准
标准。
"""
    claude_zh = """# Claude Code 项目入口

## 权威规则入口
以 `AGENTS.md` 为准。
## 工作方式
先阅读规则。
"""
    agents_en = """# Demo AI Instructions

## Document Scope and Rule Priority
Scope.
## Project Facts and Code Structure
Structure.
## Change Boundaries and Implementation Constraints
Constraints.
## Commands and Verification
Commands.
## Project-Specific Contracts
Contracts.
## Documentation and Artifact Synchronization
Synchronization.
## Safety, Confirmation Gates, and Prohibited Actions
Safety.
## Definition of Done
Done.
"""
    claude_en = """# Claude Code Project Entry

## Authoritative Rule Entry
Follow `AGENTS.md`.
## Working Method
Read project rules first.
"""
    if (
        validate_agents(agents_zh, "zh")[0]
        or validate_claude(claude_zh, "zh")
        or validate_agents(agents_en, "en")[0]
        or validate_claude(claude_en, "en")
    ):
        print("self-test failed: valid fixtures rejected", file=sys.stderr)
        return 1
    if not validate_agents(agents_zh.replace("## 命令与验证\n命令。\n", ""), "zh")[0]:
        print("self-test failed: invalid AGENTS.md accepted", file=sys.stderr)
        return 1
    if not validate_claude(claude_zh.replace("AGENTS.md", "project rules"), "zh"):
        print("self-test failed: invalid CLAUDE.md accepted", file=sys.stderr)
        return 1
    custom_agents = "# Custom\n\n## Custom Rules\nRules.\n"
    custom_claude = "# Custom\n\n## Entry\nFollow `AGENTS.md`.\n"
    if validate_agents(custom_agents, "auto", True)[0] or validate_claude(
        custom_claude, "auto", True
    ):
        print("self-test failed: valid custom fixtures rejected", file=sys.stderr)
        return 1
    # Thin entries need no artificial H2, while empty bodies and placeholders fail.
    thin_claude = "# Claude Code 项目入口\n\n本文仅维护入口；规则以 [AGENTS.md](AGENTS.md) 为准，改动前先读取规则与相关实现。\n"
    custom_cases = [
        (thin_claude, True),
        ("# Custom\n\n```text\nTODO: example data\n```\n", True),
        ("# Custom\n", False),
        ("# Custom\n\n```\n```\n", False),
        ("# Custom\nTODO: finish introduction\n", False),
        ("# Custom\nTODO: introduction\n## Scope\nContent.\n", False),
        ("# Custom\nContent.\n## Empty\n", False),
        ("# Custom\n## Same\nFirst.\n## Same\nSecond.\n", False),
    ]
    for sample, valid in custom_cases:
        if (not validate_agents(sample, "auto", True)[0]) != valid:
            print("self-test failed: custom body validation", file=sys.stderr)
            return 1
    if validate_claude(thin_claude, "auto", True) or not validate_claude(thin_claude, "zh"):
        print("self-test failed: thin entry or fixed contract validation", file=sys.stderr)
        return 1
    for invalid in [
        thin_claude.replace("AGENTS.md", "missing-source"),
        thin_claude + "\n```bash\necho run\n```\n",
    ]:
        if not validate_claude(invalid, "auto", True):
            print("self-test failed: invalid thin entry accepted", file=sys.stderr)
            return 1
    # Selection checks real files: an unselected file must not become a prerequisite.
    with TemporaryDirectory(prefix="ai-constraint-validation-") as directory:
        root = Path(directory)
        for selected, other, content in [
            ("agents", "CLAUDE.md", custom_agents),
            ("claude", "AGENTS.md", thin_claude),
        ]:
            target = root / ("AGENTS.md" if selected == "agents" else "CLAUDE.md")
            if not validate_repository(root, "auto", True, selected):
                print("self-test failed: missing selected file accepted", file=sys.stderr)
                return 1
            target.write_text(content, encoding="utf-8")
            if validate_repository(root, "auto", True, selected):
                print("self-test failed: single deliverable rejected", file=sys.stderr)
                return 1
            if not validate_repository(root, "auto", True):
                print("self-test failed: default no longer requires both files", file=sys.stderr)
                return 1
            companion = root / other
            companion.write_text("# Unfinished\n", encoding="utf-8")
            if validate_repository(root, "auto", True, selected) or not validate_repository(root, "auto", True):
                print("self-test failed: selection did not isolate validation", file=sys.stderr)
                return 1
            companion.unlink()
            target.unlink()
        (root / "AGENTS.md").write_text(custom_agents, encoding="utf-8")
        (root / "CLAUDE.md").write_text(thin_claude, encoding="utf-8")
        if validate_repository(root, "auto", True):
            print("self-test failed: valid pair rejected", file=sys.stderr)
            return 1
    print("self-test passed")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "repo_root",
        nargs="?",
        help="repository root containing the selected document(s)",
    )
    parser.add_argument(
        "--document", choices=("agents", "claude", "both"), default="both",
        help="deliverables to validate (default: both); does not create missing files",
    )
    parser.add_argument("--language", choices=("auto", "zh", "en"), default="auto")
    parser.add_argument("--custom-structure", action="store_true")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()

    if args.self_test:
        return self_test()
    if not args.repo_root:
        parser.error("repo_root is required unless --self-test is used")

    root = Path(args.repo_root)
    errors = validate_repository(root, args.language, args.custom_structure, args.document)

    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1
    print(f"AI constraint document structure valid ({args.document}): {root}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
