#!/usr/bin/env python3
"""扫描项目中的模块架构文档候选事实。"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Any


SKIP_DIRS = {
    ".git",
    ".idea",
    ".venv",
    "venv",
    "env",
    "__pycache__",
    ".pytest_cache",
    ".ruff_cache",
    ".mypy_cache",
    "node_modules",
    "dist",
    "build",
    "coverage",
    "target",
    ".gradle",
    "__tests__",
}


def rel(path: Path, root: Path) -> str:
    try:
        value = path.relative_to(root)
    except ValueError:
        value = path
    return "." if str(value) == "." else str(value)


def walk_files(root: Path) -> list[Path]:
    files: list[Path] = []
    for current, dirs, names in os.walk(root):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        current_path = Path(current)
        for name in names:
            files.append(current_path / name)
    return files


def read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return ""


def headings(path: Path) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    in_fence = False
    for line_number, line in enumerate(read_text(path).splitlines(), start=1):
        if re.match(r"^\s*(```|~~~)", line):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        match = re.match(r"^(#{1,6})\s+(.+?)\s*$", line)
        if match:
            result.append(
                {
                    "level": len(match.group(1)),
                    "title": match.group(2),
                    "line": line_number,
                }
            )
    return result


def existing_architecture_dirs(root: Path) -> list[Path]:
    candidates = [
        root / "agent-works" / "architecture",
        root / "architecture",
    ]
    return [path for path in candidates if path.exists() and path.is_dir()]


def recommended_output_dir(root: Path) -> Path:
    dirs = existing_architecture_dirs(root)
    if dirs:
        return dirs[0]
    return root / "agent-works" / "architecture"


def detect_arch_docs(root: Path) -> list[dict[str, Any]]:
    docs: list[dict[str, Any]] = []
    for directory in existing_architecture_dirs(root):
        for path in sorted(directory.glob("*.md")):
            doc_headings = headings(path)
            title = next(
                (heading["title"] for heading in doc_headings if heading["level"] == 1),
                path.stem,
            )
            docs.append(
                {
                    "path": rel(path, root),
                    "title": title,
                    "headings": doc_headings,
                }
            )
    return docs


def detect_python_backend(root: Path, files: list[Path]) -> dict[str, Any]:
    backend = root / "backend"
    if not backend.exists():
        return {}
    groups = {}
    for name in ("api", "services", "storage", "auth", "config", "scheduler", "tests"):
        path = backend / name
        if path.exists():
            groups[name] = sorted(
                rel(item, root)
                for item in path.glob("*.py")
                if item.name != "__init__.py" and not item.name.startswith("test_")
            )
    return groups


def detect_frontend(root: Path) -> dict[str, Any]:
    frontend = root / "frontend" / "src"
    if not frontend.exists():
        return {}
    result: dict[str, Any] = {}
    for name in ("views", "components", "layout", "stores", "api", "router"):
        path = frontend / name
        if path.exists():
            result[name] = sorted(
                rel(item, root)
                for item in path.rglob("*")
                if item.is_file()
                and item.suffix in {".vue", ".ts", ".js"}
                and "__tests__" not in item.parts
                and not re.search(r"(\.spec|\.test)\.[tj]s$", item.name)
            )
    return result


def detect_java(root: Path, files: list[Path]) -> list[str]:
    markers = []
    build_markers = {
        "build.gradle",
        "build.gradle.kts",
        "pom.xml",
        "settings.gradle",
        "settings.gradle.kts",
    }
    for path in files:
        if path.name in build_markers:
            markers.append(rel(path, root))
    return sorted(markers)


def infer_module_candidates(
    root: Path,
    arch_docs: list[dict[str, Any]],
    backend: dict[str, Any],
    frontend: dict[str, Any],
) -> list[dict[str, Any]]:
    candidates: dict[str, dict[str, Any]] = {}
    output_dir = recommended_output_dir(root)
    for doc in arch_docs:
        key = Path(doc["path"]).stem
        candidates[key] = {
            "name": doc["title"],
            "slug": key,
            "output_path": doc["path"],
            "evidence": [doc["path"]],
            "status": "documented",
        }
    for api_file in backend.get("api", []):
        slug = Path(api_file).stem.replace("_", "-")
        candidates.setdefault(
            slug,
            {
                "name": slug,
                "slug": slug,
                "output_path": rel(output_dir / f"{slug}.md", root),
                "evidence": [],
                "status": "source-candidate",
            },
        )
        candidates[slug]["evidence"].append(api_file)
    for view_file in frontend.get("views", []):
        if re.search(r"(\.spec|\.test)\.[tj]s$", view_file):
            continue
        stem = Path(view_file).stem
        slug = re.sub(r"(?<!^)([A-Z])", r"-\1", stem).lower().replace("-view", "")
        candidates.setdefault(
            slug,
            {
                "name": stem,
                "slug": slug,
                "output_path": rel(output_dir / f"{slug}.md", root),
                "evidence": [],
                "status": "source-candidate",
            },
        )
        candidates[slug]["evidence"].append(view_file)
    return sorted(candidates.values(), key=lambda item: item["slug"])


def build_report(root: Path) -> dict[str, Any]:
    files = walk_files(root)
    arch_docs = detect_arch_docs(root)
    backend = detect_python_backend(root, files)
    frontend = detect_frontend(root)
    output_dir = recommended_output_dir(root)
    return {
        "root": str(root),
        "architecture_dirs": [rel(path, root) for path in existing_architecture_dirs(root)],
        "recommended_output_dir": rel(output_dir, root),
        "recommended_output_dir_exists": output_dir.exists(),
        "recommended_output_dir_source": (
            "project-existing"
            if output_dir.exists()
            else "fallback-create-agent-works-architecture"
        ),
        "architecture_docs": arch_docs,
        "backend": backend,
        "frontend": frontend,
        "java_build_files": detect_java(root, files),
        "module_candidates": infer_module_candidates(root, arch_docs, backend, frontend),
    }


def format_markdown(report: dict[str, Any]) -> str:
    lines = ["# 模块架构候选扫描", "", f"根目录：`{report['root']}`", ""]
    if report["architecture_dirs"]:
        lines.extend(["## 架构目录", ""])
        for path in report["architecture_dirs"]:
            lines.append(f"- `{path}`")
        lines.append("")
    status = (
        "已存在"
        if report["recommended_output_dir_exists"]
        else "兜底目录，落地时需要创建"
    )
    lines.extend(
        [
            "## 推荐输出目录",
            "",
            f"`{report['recommended_output_dir']}`（{status}）",
            "",
        ]
    )
    if report["architecture_docs"]:
        lines.extend(["## 已有架构文档", ""])
        for doc in report["architecture_docs"]:
            h2 = [h["title"] for h in doc["headings"] if h["level"] == 2]
            suffix = f"；H2：{', '.join(h2)}" if h2 else ""
            lines.append(f"- `{doc['path']}`：{doc['title']}{suffix}")
        lines.append("")
    if report["module_candidates"]:
        lines.extend(["## 模块候选", ""])
        for item in report["module_candidates"]:
            evidence = ", ".join(f"`{path}`" for path in item["evidence"][:6])
            more = " ..." if len(item["evidence"]) > 6 else ""
            lines.append(f"- `{item['slug']}`：{item['name']}（{item['status']}）")
            lines.append(f"  - 输出：`{item['output_path']}`")
            if evidence:
                lines.append(f"  - 依据：{evidence}{more}")
        lines.append("")
    if report["backend"]:
        lines.extend(["## 后端入口", ""])
        for group, paths in report["backend"].items():
            lines.append(f"- `{group}`：{len(paths)} 个文件")
        lines.append("")
    if report["frontend"]:
        lines.extend(["## 前端入口", ""])
        for group, paths in report["frontend"].items():
            lines.append(f"- `{group}`：{len(paths)} 个文件")
        lines.append("")
    if report["java_build_files"]:
        lines.extend(["## Java 构建文件", ""])
        for path in report["java_build_files"]:
            lines.append(f"- `{path}`")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", nargs="?", default=".", help="仓库根目录")
    parser.add_argument("--format", choices=("markdown", "json"), default="markdown")
    args = parser.parse_args()

    root = Path(args.root).expanduser().resolve()
    if not root.exists() or not root.is_dir():
        print(f"不是目录：{root}", file=sys.stderr)
        return 2

    report = build_report(root)
    if args.format == "json":
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(format_markdown(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
