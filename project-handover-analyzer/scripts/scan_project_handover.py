#!/usr/bin/env python3
"""Build a read-only inventory for project handover analysis."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import xml.etree.ElementTree as ET
from collections import Counter
from collections.abc import Iterable
from pathlib import Path
from typing import Any

SKIP_DIRS = {
    ".git",
    ".hg",
    ".svn",
    ".idea",
    ".obsidian",
    ".vscode",
    ".venv",
    "venv",
    "env",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    "node_modules",
    "uni_modules",
    "vendor",
    "vendors",
    "third_party",
    "third-party",
    "libreofficeportable",
    "target",
    "dist",
    "build",
    "coverage",
    ".gradle",
    ".next",
    ".nuxt",
    ".output",
    ".dart_tool",
    "pods",
}

BUILD_MANIFESTS = {
    "pom.xml",
    "build.gradle",
    "build.gradle.kts",
    "settings.gradle",
    "settings.gradle.kts",
    "package.json",
    "pnpm-workspace.yaml",
    "yarn.lock",
    "pnpm-lock.yaml",
    "package-lock.json",
    "pyproject.toml",
    "requirements.txt",
    "Pipfile",
    "poetry.lock",
    "go.mod",
    "go.sum",
    "Cargo.toml",
    "Cargo.lock",
    "Gemfile",
    "composer.json",
    "*.sln",
    "*.csproj",
}

LANGUAGE_BY_SUFFIX = {
    ".java": "Java",
    ".kt": "Kotlin",
    ".kts": "Kotlin",
    ".ts": "TypeScript",
    ".tsx": "TypeScript",
    ".js": "JavaScript",
    ".jsx": "JavaScript",
    ".vue": "Vue",
    ".py": "Python",
    ".go": "Go",
    ".rs": "Rust",
    ".cs": "C#",
    ".php": "PHP",
    ".rb": "Ruby",
    ".swift": "Swift",
    ".scala": "Scala",
    ".sql": "SQL",
}

SENSITIVE_NAME_RE = re.compile(
    r"(^|[._-])(env|secret|secrets|credential|credentials|private|keystore|truststore)([._-]|$)",
    re.IGNORECASE,
)


def relative(path: Path, root: Path) -> str:
    try:
        value = path.relative_to(root)
    except ValueError:
        value = path
    return "." if value == Path(".") else value.as_posix()


def limited(values: Iterable[str], maximum: int) -> tuple[list[str], int]:
    unique = sorted(set(values), key=lambda item: (item.count("/"), item.lower(), item))
    return unique[:maximum], max(0, len(unique) - maximum)


def walk_project(
    root: Path, max_depth: int, skip_dirs: set[str]
) -> tuple[list[Path], list[Path], list[str], list[str]]:
    files: list[Path] = []
    git_roots: list[Path] = []
    skipped: set[str] = set()
    errors: list[str] = []

    def record_error(error: OSError) -> None:
        target = Path(error.filename) if error.filename else root
        errors.append(
            f"{relative(target, root)}: {error.strerror or type(error).__name__}"
        )

    for current, dirs, names in os.walk(root, onerror=record_error):
        current_path = Path(current)
        depth = len(current_path.relative_to(root).parts)

        if ".git" in dirs or ".git" in names:
            git_roots.append(current_path)

        retained_dirs = []
        for name in dirs:
            child = current_path / name
            if name.lower() in skip_dirs:
                skipped.add(relative(child, root))
                continue
            if depth >= max_depth:
                skipped.add(relative(child, root))
                continue
            retained_dirs.append(name)
        dirs[:] = retained_dirs

        for name in names:
            path = current_path / name
            if name == ".git":
                continue
            files.append(path)

    return files, sorted(set(git_roots)), sorted(skipped), sorted(set(errors))


def is_build_manifest(path: Path) -> bool:
    return path.name in BUILD_MANIFESTS or any(
        path.match(pattern) for pattern in BUILD_MANIFESTS if "*" in pattern
    )


def is_deployment_file(path: Path, root: Path) -> bool:
    rel = relative(path, root).lower()
    name = path.name.lower()
    parts = set(Path(rel).parts)
    return bool(
        name.startswith("dockerfile")
        or re.match(r"^(docker-)?compose.*\.ya?ml$", name)
        or name in {"chart.yaml", "jenkinsfile", ".gitlab-ci.yml", "nginx.conf"}
        or {"k8s", "kubernetes", "helm", "deploy", "deployment", "infra"} & parts
        or (
            path.suffix.lower() in {".sh", ".bat", ".ps1"}
            and re.search(r"deploy|release|publish", name)
        )
    )


def is_ci_file(path: Path, root: Path) -> bool:
    rel = relative(path, root).lower()
    return bool(
        rel.startswith(".github/workflows/")
        or "/.github/workflows/" in rel
        or path.name.lower()
        in {
            "jenkinsfile",
            ".gitlab-ci.yml",
            "azure-pipelines.yml",
            "bitbucket-pipelines.yml",
        }
    )


def is_document(path: Path, root: Path) -> bool:
    rel = relative(path, root).lower()
    return path.suffix.lower() == ".md" and (
        path.name.lower() in {"readme.md", "agents.md", "design.md", "architecture.md"}
        or "docs/" in rel
        or "doc/" in rel
        or "agent-works/" in rel
    )


def is_config_file(path: Path) -> bool:
    name = path.name.lower()
    return bool(
        name.startswith(".env")
        or name
        in {
            "application.properties",
            "application.yml",
            "application.yaml",
            "bootstrap.yml",
            "bootstrap.yaml",
        }
        or path.suffix.lower() in {".toml", ".properties", ".conf"}
        or (
            path.suffix.lower() in {".yml", ".yaml", ".json"}
            and re.search(r"config|setting|application|bootstrap", name)
        )
    )


def is_database_file(path: Path, root: Path) -> bool:
    rel = relative(path, root).lower()
    parts = set(Path(rel).parts)
    data_suffixes = {
        ".sql",
        ".jql",
        ".ddl",
        ".prisma",
        ".xml",
        ".yaml",
        ".yml",
        ".json",
    }
    return path.suffix.lower() in {".sql", ".jql", ".ddl", ".prisma"} or bool(
        {
            "migration",
            "migrations",
            "migrate",
            "flyway",
            "liquibase",
            "prisma",
            "schema",
        }
        & parts
        and path.suffix.lower() in data_suffixes
    )


def is_test_file(path: Path, root: Path) -> bool:
    rel = relative(path, root).lower()
    name = path.name.lower()
    test_suffixes = {
        ".py",
        ".go",
        ".js",
        ".jsx",
        ".ts",
        ".tsx",
        ".java",
        ".kt",
        ".cs",
        ".rs",
        ".rb",
        ".php",
    }
    return path.suffix.lower() in test_suffixes and bool(
        re.search(r"(^|/)(test|tests|__tests__|spec|e2e)(/|$)", rel)
        or re.search(
            r"(^test_.*|.*(_test|\.test|\.spec))\.(py|go|js|jsx|ts|tsx|java|kt|cs)$",
            name,
        )
    )


def is_entrypoint(path: Path, root: Path) -> bool:
    name = path.name.lower()
    rel_parts = Path(relative(path, root)).parts
    shallow_index = (
        name in {"index.ts", "index.js"}
        and len(rel_parts) <= 3
        and path.parent.name.lower() in {"src", "app", "server", "cli"}
    )
    return bool(
        name
        in {
            "main.py",
            "app.py",
            "manage.py",
            "server.py",
            "main.go",
            "main.rs",
            "main.ts",
            "main.js",
            "program.cs",
            "cli.py",
            "cli.ts",
            "cli.js",
        }
        or shallow_index
        or name.endswith(("application.java", "application.kt"))
    )


def is_sensitive_candidate(path: Path) -> bool:
    name = path.name
    return bool(
        name.lower().startswith(".env")
        or SENSITIVE_NAME_RE.search(name)
        or path.suffix.lower() in {".pem", ".key", ".p12", ".pfx", ".jks", ".keystore"}
    )


def parse_package_json(
    path: Path,
) -> tuple[dict[str, Any], list[dict[str, str]], str | None]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except OSError as error:
        return {}, [], f"{type(error).__name__}: {error.strerror or 'read failed'}"
    except UnicodeDecodeError as error:
        return {}, [], f"UnicodeDecodeError at byte {error.start}"
    except json.JSONDecodeError as error:
        return {}, [], f"JSONDecodeError at line {error.lineno}, column {error.colno}"

    workspaces = data.get("workspaces", [])
    if isinstance(workspaces, dict):
        workspaces = workspaces.get("packages", [])
    if not isinstance(workspaces, list):
        workspaces = []

    details = {
        "kind": "npm",
        "name": data.get("name"),
        "version": data.get("version"),
        "private": data.get("private"),
        "package_manager": data.get("packageManager"),
        "workspaces": [item for item in workspaces if isinstance(item, str)],
    }
    gaps: list[dict[str, str]] = []
    for workspace in details.get("workspaces", []):
        if (
            workspace.startswith("!")
            or "${" in workspace
            or "{" in workspace
            or "}" in workspace
        ):
            continue
        try:
            matches = list(path.parent.glob(workspace))
        except (NotImplementedError, ValueError):
            continue
        if not matches:
            gaps.append(
                {
                    "manifest": str(path),
                    "reference": workspace,
                    "target": workspace,
                    "reason": "workspace declaration has no matching path",
                }
            )
    for section in (
        "dependencies",
        "devDependencies",
        "peerDependencies",
        "optionalDependencies",
    ):
        values = data.get(section, {})
        if not isinstance(values, dict):
            continue
        for dependency, target in values.items():
            if (
                not isinstance(target, str)
                or not target.startswith(("file:", "link:"))
                or "${" in target
            ):
                continue
            local = target.split(":", 1)[1]
            candidate = (path.parent / local).resolve()
            if not candidate.exists():
                gaps.append(
                    {
                        "manifest": str(path),
                        "reference": dependency,
                        "target": local,
                        "reason": f"missing local {section} target",
                    }
                )
    return (
        {key: value for key, value in details.items() if value not in (None, [], {})},
        gaps,
        None,
    )


def strip_namespace(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def parse_pom(path: Path) -> tuple[dict[str, Any], list[dict[str, str]], str | None]:
    try:
        project = ET.parse(path).getroot()
    except OSError as error:
        return {}, [], f"{type(error).__name__}: {error.strerror or 'read failed'}"
    except ET.ParseError as error:
        line, column = getattr(error, "position", (0, 0))
        return {}, [], f"XML ParseError at line {line}, column {column}"

    direct: dict[str, str] = {}
    modules: list[str] = []
    for child in project:
        tag = strip_namespace(child.tag)
        if tag in {"groupId", "artifactId", "version", "packaging"} and child.text:
            direct[tag] = child.text.strip()
        elif tag == "modules":
            modules = [
                module.text.strip()
                for module in child
                if strip_namespace(module.tag) == "module" and module.text
            ]

    details: dict[str, Any] = {"kind": "maven", **direct}
    if modules:
        details["modules"] = modules
    gaps = []
    for module in modules:
        if "${" in module:
            continue
        target = path.parent / module
        project_file = target if target.name == "pom.xml" else target / "pom.xml"
        if not target.exists() or not project_file.is_file():
            gaps.append(
                {
                    "manifest": str(path),
                    "reference": module,
                    "target": module,
                    "reason": "declared Maven module project is missing",
                }
            )
    return details, gaps, None


def parse_simple_manifest(path: Path) -> tuple[dict[str, Any], str | None]:
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except OSError as error:
        return {}, f"{type(error).__name__}: {error.strerror or 'read failed'}"
    if path.name == "go.mod":
        match = re.search(r"^module\s+(\S+)", text, re.MULTILINE)
        return {"kind": "go", "module": match.group(1) if match else None}, None
    if path.name == "pyproject.toml":
        name = re.search(r"^name\s*=\s*[\"']([^\"']+)", text, re.MULTILINE)
        version = re.search(r"^version\s*=\s*[\"']([^\"']+)", text, re.MULTILINE)
        return (
            {
                "kind": "python",
                "name": name.group(1) if name else None,
                "version": version.group(1) if version else None,
            },
            None,
        )
    if path.name == "Cargo.toml":
        name = re.search(r"^name\s*=\s*[\"']([^\"']+)", text, re.MULTILINE)
        version = re.search(r"^version\s*=\s*[\"']([^\"']+)", text, re.MULTILINE)
        return (
            {
                "kind": "cargo",
                "name": name.group(1) if name else None,
                "version": version.group(1) if version else None,
            },
            None,
        )
    return {}, None


def manifest_details(
    path: Path, root: Path
) -> tuple[dict[str, Any], list[dict[str, str]], str | None]:
    details: dict[str, Any] = {}
    gaps: list[dict[str, str]] = []
    error: str | None = None
    if path.name == "package.json":
        details, gaps, error = parse_package_json(path)
    elif path.name == "pom.xml":
        details, gaps, error = parse_pom(path)
    elif path.name in {"go.mod", "pyproject.toml", "Cargo.toml"}:
        details, error = parse_simple_manifest(path)

    if details:
        details = {key: value for key, value in details.items() if value is not None}
        details["path"] = relative(path, root)
    for gap in gaps:
        gap["manifest"] = relative(Path(gap["manifest"]), root)
    return details, gaps, error


def classify_shape(root: Path, git_roots: list[Path], manifests: list[Path]) -> str:
    root_is_repo = root in git_roots
    nested = [path for path in git_roots if path != root]
    if not root_is_repo and len(nested) > 1:
        return "multi-repository delivery bundle"
    if root_is_repo and nested:
        return "repository containing nested repositories or worktrees"
    if root_is_repo and len(manifests) > 1:
        return "single repository with multiple build units or workspace"
    if len(git_roots) == 1:
        return "single repository"
    if not git_roots and len(manifests) > 1:
        return "unversioned delivery bundle with multiple build units"
    return "undetermined; inspect build and repository evidence"


def build_inventory(
    root: Path,
    max_depth: int,
    max_items: int,
    extra_excludes: Iterable[str] = (),
    include_absolute_root: bool = False,
) -> dict[str, Any]:
    exclude_names = tuple(extra_excludes)
    skip_dirs = SKIP_DIRS | {name.lower() for name in exclude_names}
    files, git_roots, skipped, walk_errors = walk_project(root, max_depth, skip_dirs)
    manifests = [path for path in files if is_build_manifest(path)]
    languages = Counter(
        LANGUAGE_BY_SUFFIX[path.suffix.lower()]
        for path in files
        if path.suffix.lower() in LANGUAGE_BY_SUFFIX
    )

    details = []
    gaps = []
    parse_errors = []
    for manifest in manifests:
        info, manifest_gaps, error = manifest_details(manifest, root)
        if info:
            details.append(info)
        gaps.extend(manifest_gaps)
        if error:
            parse_errors.append({"manifest": relative(manifest, root), "error": error})

    def paths(predicate: Any) -> dict[str, Any]:
        items, omitted = limited(
            (relative(path, root) for path in files if predicate(path)), max_items
        )
        return {"items": items, "omitted": omitted}

    top_level = sorted(
        item.name
        for item in root.iterdir()
        if item.is_dir() and item.name.lower() not in skip_dirs
    )
    sensitive, sensitive_omitted = limited(
        (relative(path, root) for path in files if is_sensitive_candidate(path)),
        max_items,
    )
    skipped_items, skipped_omitted = limited(skipped, max_items)

    report = {
        "root": ".",
        "root_name": root.name,
        "candidate_delivery_shape": classify_shape(root, git_roots, manifests),
        "scan_limits": {
            "max_depth": max_depth,
            "max_items_per_category": max_items,
            "extra_excluded_directories": sorted(set(exclude_names)),
        },
        "summary": {
            "files_seen": len(files),
            "git_repositories": len(git_roots),
            "build_manifests": len(manifests),
            "tests": sum(1 for path in files if is_test_file(path, root)),
            "database_artifacts": sum(
                1 for path in files if is_database_file(path, root)
            ),
            "deployment_artifacts": sum(
                1 for path in files if is_deployment_file(path, root)
            ),
        },
        "top_level_directories": top_level,
        "git_roots": [relative(path, root) for path in git_roots],
        "languages_by_file_count": dict(languages.most_common()),
        "manifest_details": sorted(details, key=lambda item: item["path"]),
        "manifest_parse_errors": sorted(
            parse_errors, key=lambda item: item["manifest"]
        ),
        "declared_local_reference_gaps": sorted(
            gaps, key=lambda item: (item["manifest"], item["reference"])
        ),
        "build_manifests": paths(is_build_manifest),
        "entrypoint_candidates": paths(lambda path: is_entrypoint(path, root)),
        "deployment_artifacts": paths(lambda path: is_deployment_file(path, root)),
        "ci_artifacts": paths(lambda path: is_ci_file(path, root)),
        "database_artifacts": paths(lambda path: is_database_file(path, root)),
        "test_artifacts": paths(lambda path: is_test_file(path, root)),
        "configuration_candidates": paths(is_config_file),
        "documentation": paths(lambda path: is_document(path, root)),
        "sensitive_file_candidates": {
            "items": sensitive,
            "omitted": sensitive_omitted,
            "note": (
                "Filename-based candidates only; contents were not inspected, and an empty "
                "result does not prove that the project contains no secrets."
            ),
        },
        "skipped_directories": {"items": skipped_items, "omitted": skipped_omitted},
        "walk_errors": walk_errors,
    }
    if include_absolute_root:
        report["absolute_root"] = str(root)
    return report


def markdown_list(lines: list[str], title: str, section: dict[str, Any]) -> None:
    lines.extend([f"## {title}", ""])
    if not section["items"]:
        lines.extend(["未发现。", ""])
        return
    lines.extend(f"- `{item}`" for item in section["items"])
    if section.get("omitted"):
        lines.append(f"- 另有 {section['omitted']} 项因输出上限未展开")
    lines.append("")


def format_markdown(report: dict[str, Any]) -> str:
    summary = report["summary"]
    lines = [
        "# 项目接手候选清单",
        "",
        f"- 项目目录：`{report['root_name']}`",
        f"- 候选交付形态：{report['candidate_delivery_shape']}",
        f"- 扫描文件数：{summary['files_seen']}",
        f"- Git 仓库数：{summary['git_repositories']}",
        f"- 构建清单数：{summary['build_manifests']}",
        f"- 测试候选数：{summary['tests']}",
        f"- 数据库材料数：{summary['database_artifacts']}",
        f"- 部署材料数：{summary['deployment_artifacts']}",
        "",
        "> 本清单只辅助发现。模块职责、运行关系、缺失项和生产拓扑必须回读源码与配置确认。",
        "",
        "## 顶层目录",
        "",
    ]
    lines.extend(f"- `{item}`" for item in report["top_level_directories"])
    lines.append("")

    lines.extend(["## 语言线索", "", "| 语言 | 文件数 |", "| --- | ---: |"])
    lines.extend(
        f"| {language} | {count} |"
        for language, count in report["languages_by_file_count"].items()
    )
    lines.extend(
        [
            "",
            "> 文件数包含交付包中的第三方或内置源码，只用于选择后续调查方向，不能直接认定为主技术栈。",
            "",
        ]
    )

    markdown_list(lines, "Git 仓库", {"items": report["git_roots"], "omitted": 0})
    markdown_list(lines, "构建清单", report["build_manifests"])

    lines.extend(["## 构建清单元数据", ""])
    if report["manifest_details"]:
        lines.extend(
            [
                "| 路径 | 类型 | 标识 | 版本 | 聚合信息 |",
                "| --- | --- | --- | --- | --- |",
            ]
        )
        ordered_details = sorted(
            report["manifest_details"],
            key=lambda item: (item["path"].count("/"), item["path"].lower()),
        )
        limit = report["scan_limits"]["max_items_per_category"]
        for detail in ordered_details[:limit]:
            identity = (
                detail.get("artifactId")
                or detail.get("name")
                or detail.get("module")
                or ""
            )
            version = detail.get("version", "")
            composition = ""
            if detail.get("modules"):
                composition = f"{len(detail['modules'])} 个 Maven 模块"
            elif detail.get("workspaces"):
                composition = f"{len(detail['workspaces'])} 个 workspace 声明"
            elif detail.get("package_manager"):
                composition = str(detail["package_manager"])
            lines.append(
                f"| `{detail['path']}` | {detail.get('kind', '')} | `{identity}` | `{version}` | {composition} |"
            )
        omitted_details = max(0, len(ordered_details) - limit)
        if omitted_details:
            lines.append(f"| ... | 另有 {omitted_details} 项未展开 |  |  |  |")
        lines.append("")
    else:
        lines.extend(["未解析到受支持的构建清单元数据。", ""])

    lines.extend(["## 构建清单解析错误", ""])
    if report["manifest_parse_errors"]:
        lines.extend(["| 清单 | 错误 |", "| --- | --- |"])
        for error in report["manifest_parse_errors"]:
            lines.append(f"| `{error['manifest']}` | {error['error']} |")
        lines.append("")
    else:
        lines.extend(["未发现。", ""])

    markdown_list(lines, "启动入口候选", report["entrypoint_candidates"])
    markdown_list(lines, "部署材料", report["deployment_artifacts"])
    markdown_list(lines, "CI 材料", report["ci_artifacts"])
    markdown_list(lines, "数据库材料", report["database_artifacts"])
    markdown_list(lines, "测试材料", report["test_artifacts"])
    markdown_list(lines, "配置候选", report["configuration_candidates"])
    markdown_list(lines, "关键文档", report["documentation"])
    markdown_list(lines, "敏感文件候选（仅路径）", report["sensitive_file_candidates"])

    lines.extend(["## 声明但未找到的本地引用", ""])
    if report["declared_local_reference_gaps"]:
        lines.extend(["| 清单 | 引用 | 目标 | 原因 |", "| --- | --- | --- | --- |"])
        for gap in report["declared_local_reference_gaps"]:
            lines.append(
                f"| `{gap['manifest']}` | `{gap['reference']}` | `{gap['target']}` | {gap['reason']} |"
            )
        lines.append("")
    else:
        lines.extend(["未从支持解析的清单中发现明确缺口。", ""])

    if report["skipped_directories"]["items"]:
        markdown_list(lines, "跳过目录", report["skipped_directories"])
    if report["walk_errors"]:
        lines.extend(["## 无法读取的路径", ""])
        lines.extend(f"- `{item}`" for item in report["walk_errors"])
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "root", nargs="?", default=".", help="Project or delivery-bundle root"
    )
    parser.add_argument("--format", choices=("json", "markdown"), default="json")
    parser.add_argument("--max-depth", type=int, default=10)
    parser.add_argument("--max-items", type=int, default=80)
    parser.add_argument(
        "--exclude-dir",
        action="append",
        default=[],
        help="Additional directory basename to exclude; repeat for multiple names",
    )
    parser.add_argument(
        "--include-absolute-root",
        action="store_true",
        help="Include the absolute project root in JSON output",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    root = Path(args.root).expanduser().resolve()
    if not root.is_dir():
        print(f"error: not a directory: {root}", file=sys.stderr)
        return 2
    if args.max_depth < 1 or args.max_items < 1:
        print("error: --max-depth and --max-items must be positive", file=sys.stderr)
        return 2

    report = build_inventory(
        root,
        args.max_depth,
        args.max_items,
        extra_excludes=args.exclude_dir,
        include_absolute_root=args.include_absolute_root,
    )
    if args.format == "markdown":
        sys.stdout.write(format_markdown(report))
    else:
        json.dump(report, sys.stdout, ensure_ascii=False, indent=2)
        sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
