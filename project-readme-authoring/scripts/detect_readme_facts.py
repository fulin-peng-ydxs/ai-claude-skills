#!/usr/bin/env python3
"""扫描生成 README 前可用的项目事实。"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Any

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover
    tomllib = None


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
}

DOC_NAMES = {
    "README.md",
    "AGENTS.md",
    "CLAUDE.md",
    "DESIGN.md",
    "CONTRIBUTING.md",
    "LICENSE",
    "LICENSE.md",
    "CHANGELOG.md",
}

KNOWN_NODE_DEPS = {
    "express",
    "fastify",
    "next",
    "nuxt",
    "react",
    "typescript",
    "vite",
    "vue",
}

KNOWN_PYTHON_DEPS = {
    "django",
    "duckdb",
    "fastapi",
    "flask",
    "pandas",
    "pytest",
    "redis",
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


def read_json(path: Path) -> dict[str, Any] | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def read_toml(path: Path) -> dict[str, Any] | None:
    if tomllib is None:
        return None
    try:
        with path.open("rb") as handle:
            return tomllib.load(handle)
    except Exception:
        return None


def read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return ""


def readme_headings(root: Path) -> list[dict[str, Any]]:
    readme = root / "README.md"
    if not readme.exists():
        return []
    headings: list[dict[str, Any]] = []
    in_fence = False
    for line_number, line in enumerate(read_text(readme).splitlines(), start=1):
        if re.match(r"^\s*(```|~~~)", line):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        match = re.match(r"^(#{1,6})\s+(.+?)\s*$", line)
        if match:
            headings.append(
                {
                    "level": len(match.group(1)),
                    "title": match.group(2),
                    "line": line_number,
                }
            )
    return headings


def top_level_dirs(root: Path) -> list[str]:
    dirs = []
    for path in sorted(root.iterdir()):
        if path.is_dir() and path.name not in SKIP_DIRS and not path.name.startswith("."):
            dirs.append(path.name)
    return dirs


def detect_docs(root: Path, files: list[Path]) -> list[str]:
    docs = []
    for path in files:
        if path.name in DOC_NAMES or path.parts[-2:] == ("docs", path.name):
            docs.append(rel(path, root))
            continue
        relative = rel(path, root)
        if relative.startswith("docs/") and path.suffix.lower() in {".md", ".mdx"}:
            docs.append(relative)
        if relative.startswith("agent-works/architecture/") and path.suffix.lower() == ".md":
            docs.append(relative)
    return sorted(set(docs))


def extract_ports(text: str) -> list[str]:
    ports: set[str] = set()
    patterns = [
        r"https?://[^\s:]+:(\d{2,5})",
        r"\b[A-Z_]*PORT[A-Z_]*\s*[:=]\s*[\"']?(\d{2,5})",
        r"--port\s+[\"']?(\d{2,5})",
        r"(?:端口|port)\s*[=:：]?\s*(\d{2,5})",
    ]
    for pattern in patterns:
        for match in re.finditer(pattern, text, flags=re.IGNORECASE):
            value = match.group(1)
            number = int(value)
            if 0 < number <= 65535:
                ports.add(value)
    return sorted(ports, key=int)


def detect_package_manager(component: Path, package_json: dict[str, Any] | None = None) -> str:
    package_manager = ""
    if package_json:
        raw_package_manager = package_json.get("packageManager")
        if isinstance(raw_package_manager, str):
            package_manager = raw_package_manager.split("@", 1)[0].strip().lower()
    if package_manager in {"npm", "pnpm", "yarn", "bun"}:
        return package_manager
    if (component / "pnpm-lock.yaml").exists():
        return "pnpm"
    if (component / "yarn.lock").exists():
        return "yarn"
    if (component / "bun.lockb").exists() or (component / "bun.lock").exists():
        return "bun"
    return "npm"


def node_install_command(component: Path, package_manager: str) -> dict[str, str]:
    if package_manager == "pnpm":
        if (component / "pnpm-lock.yaml").exists():
            return {"command": "pnpm install --frozen-lockfile", "note": "基于 pnpm-lock.yaml"}
        return {
            "command": "pnpm install",
            "note": "未发现 pnpm-lock.yaml，执行前确认是否允许更新依赖状态",
        }
    if package_manager == "yarn":
        if (component / "yarn.lock").exists():
            return {"command": "yarn install --frozen-lockfile", "note": "基于 yarn.lock"}
        return {
            "command": "yarn install",
            "note": "未发现 yarn.lock，执行前确认是否允许更新依赖状态",
        }
    if package_manager == "bun":
        if (component / "bun.lockb").exists() or (component / "bun.lock").exists():
            return {"command": "bun install --frozen-lockfile", "note": "基于 bun 锁文件"}
        return {
            "command": "bun install",
            "note": "未发现 bun 锁文件，执行前确认是否允许更新依赖状态",
        }
    if (component / "package-lock.json").exists() or (component / "npm-shrinkwrap.json").exists():
        return {"command": "npm ci", "note": "基于 npm 锁文件"}
    return {
        "command": "npm install",
        "note": "未发现 npm 锁文件，执行前确认是否允许更新依赖状态",
    }


def detect_node(root: Path, files: list[Path]) -> list[dict[str, Any]]:
    components: list[dict[str, Any]] = []
    for package_json in sorted(path for path in files if path.name == "package.json"):
        data = read_json(package_json)
        if not data:
            continue
        component = package_json.parent
        scripts = data.get("scripts") if isinstance(data.get("scripts"), dict) else {}
        deps: dict[str, Any] = {}
        for key in ("dependencies", "devDependencies", "peerDependencies"):
            value = data.get(key)
            if isinstance(value, dict):
                deps.update(value)
        stack = "node"
        if "vue" in deps or any((component / "src").glob("**/*.vue")):
            stack = "vue"
        elif "react" in deps:
            stack = "react"
        elif "next" in deps:
            stack = "next"
        package_manager = detect_package_manager(component, data)
        components.append(
            {
                "stack": stack,
                "path": rel(component, root),
                "package_manager": package_manager,
                "install_command": node_install_command(component, package_manager),
                "scripts": scripts,
                "notable_dependencies": sorted(
                    dep for dep in deps if dep in KNOWN_NODE_DEPS
                ),
            }
        )
    return components


def detect_python(root: Path, files: list[Path]) -> list[dict[str, Any]]:
    markers = {
        "pyproject.toml",
        "pytest.ini",
        "requirements.txt",
        "setup.cfg",
        "setup.py",
        "tox.ini",
    }
    component_dirs = sorted({path.parent for path in files if path.name in markers})
    components: list[dict[str, Any]] = []
    for component in component_dirs:
        pyproject_path = component / "pyproject.toml"
        pyproject = read_toml(pyproject_path) if pyproject_path.exists() else None
        requires_python = None
        dependencies: list[str] = []
        pytest_paths: Any = None
        if pyproject:
            project = pyproject.get("project", {})
            requires_python = project.get("requires-python")
            raw_deps = project.get("dependencies")
            if isinstance(raw_deps, list):
                dependencies = [
                    str(dep).split(">=")[0].split("==")[0].split("[")[0]
                    for dep in raw_deps
                ]
            pytest_paths = (
                pyproject.get("tool", {})
                .get("pytest", {})
                .get("ini_options", {})
                .get("testpaths")
            )
        components.append(
            {
                "stack": "python",
                "path": rel(component, root),
                "requires_python": requires_python,
                "has_requirements": (component / "requirements.txt").exists(),
                "install_command": (
                    {
                        "command": "python -m pip install -r requirements.txt",
                        "note": "会修改当前 Python 环境，执行前确认虚拟环境",
                    }
                    if (component / "requirements.txt").exists()
                    else None
                ),
                "pytest_paths": pytest_paths,
                "notable_dependencies": sorted(
                    dep for dep in dependencies if dep in KNOWN_PYTHON_DEPS
                ),
            }
        )
    return components


def detect_java(root: Path, files: list[Path]) -> list[dict[str, Any]]:
    components: list[dict[str, Any]] = []
    build_markers = {"build.gradle", "build.gradle.kts", "pom.xml"}
    for marker in sorted(path for path in files if path.name in build_markers):
        component = marker.parent
        text = read_text(marker)
        build_tool = "maven" if marker.name == "pom.xml" else "gradle"
        components.append(
            {
                "stack": "java",
                "path": rel(component, root),
                "build_tool": build_tool,
                "uses_wrapper": (component / "mvnw").exists() or (component / "gradlew").exists(),
                "spring_boot": "spring-boot" in text or "org.springframework.boot" in text,
            }
        )
    return components


def detect_service_scripts(root: Path, files: list[Path]) -> list[dict[str, Any]]:
    scripts = []
    for script in sorted(path for path in files if re.match(r"start.*\.sh$", path.name)):
        text = read_text(script)
        commands = []
        script_path = rel(script, root)
        for subcommand in ("", "status", "stop", "restart", "logs", "prod"):
            token = f"./{script_path}" if not subcommand else f"./{script_path} {subcommand}"
            if not subcommand or re.search(rf"\b{subcommand}\b", text):
                commands.append(token)
        scripts.append(
            {
                "path": rel(script, root),
                "ports_mentioned": extract_ports(text),
                "commands": commands,
            }
        )
    return scripts


def candidate_commands(report: dict[str, Any]) -> list[dict[str, str]]:
    commands: list[dict[str, str]] = []
    for component in report["components"]:
        cwd = component["path"]
        stack = component["stack"]
        if stack in {"node", "vue", "react", "next"}:
            pm = component.get("package_manager", "npm")
            scripts = component.get("scripts", {})
            commands.append({"cwd": cwd, "command": "node --version", "purpose": "环境"})
            commands.append({"cwd": cwd, "command": f"{pm} --version", "purpose": "环境"})
            install = component.get("install_command")
            if isinstance(install, dict) and install.get("command"):
                command_item = {
                    "cwd": cwd,
                    "command": install["command"],
                    "purpose": "依赖",
                }
                if install.get("note"):
                    command_item["note"] = install["note"]
                commands.append(command_item)
            for name in ("test", "test:unit", "build", "dev", "preview", "lint"):
                if name in scripts:
                    if pm == "npm":
                        run = f"npm run {name}"
                    elif pm == "yarn":
                        run = f"yarn {name}"
                    else:
                        run = f"{pm} run {name}"
                    commands.append({"cwd": cwd, "command": run, "purpose": "脚本"})
        elif stack == "python":
            commands.append({"cwd": cwd, "command": "python --version", "purpose": "环境"})
            commands.append({"cwd": cwd, "command": "python -m pip --version", "purpose": "环境"})
            install = component.get("install_command")
            if isinstance(install, dict) and install.get("command"):
                command_item = {
                    "cwd": cwd,
                    "command": install["command"],
                    "purpose": "依赖",
                }
                if install.get("note"):
                    command_item["note"] = install["note"]
                commands.append(command_item)
            pytest_paths = component.get("pytest_paths")
            if pytest_paths:
                if isinstance(pytest_paths, list):
                    path_text = " ".join(str(item) for item in pytest_paths)
                else:
                    path_text = str(pytest_paths)
                commands.append(
                    {
                        "cwd": cwd,
                        "command": f"python -m pytest {path_text} -q",
                        "purpose": "测试",
                    }
                )
        elif stack == "java":
            tool = component.get("build_tool")
            if tool == "maven":
                mvn = "./mvnw" if component.get("uses_wrapper") else "mvn"
                commands.extend(
                    [
                        {"cwd": cwd, "command": "java -version", "purpose": "环境"},
                        {"cwd": cwd, "command": f"{mvn} test", "purpose": "测试"},
                        {"cwd": cwd, "command": f"{mvn} package", "purpose": "构建"},
                    ]
                )
            if tool == "gradle":
                gradle = "./gradlew" if component.get("uses_wrapper") else "gradle"
                commands.extend(
                    [
                        {"cwd": cwd, "command": "java -version", "purpose": "环境"},
                        {"cwd": cwd, "command": f"{gradle} test", "purpose": "测试"},
                        {"cwd": cwd, "command": f"{gradle} build", "purpose": "构建"},
                    ]
                )
    for script in report["service_scripts"]:
        for command in script.get("commands", []):
            commands.append({"cwd": ".", "command": command, "purpose": "服务"})
    return commands


def build_report(root: Path) -> dict[str, Any]:
    files = walk_files(root)
    components = detect_python(root, files) + detect_node(root, files) + detect_java(root, files)
    report = {
        "root": str(root),
        "existing_readme_headings": readme_headings(root),
        "top_level_dirs": top_level_dirs(root),
        "documents": detect_docs(root, files),
        "components": components,
        "service_scripts": detect_service_scripts(root, files),
    }
    report["candidate_commands"] = candidate_commands(report)
    return report


def format_markdown(report: dict[str, Any]) -> str:
    lines = ["# README 事实扫描", "", f"根目录：`{report['root']}`", ""]
    if report["existing_readme_headings"]:
        lines.extend(["## 现有 README 章节", ""])
        for heading in report["existing_readme_headings"]:
            lines.append(f"- H{heading['level']} 第 {heading['line']} 行：{heading['title']}")
        lines.append("")
    if report["components"]:
        lines.extend(["## 技术组件", ""])
        for component in report["components"]:
            lines.append(f"- `{component['path']}`：{component['stack']}")
            for key in ("package_manager", "requires_python", "build_tool"):
                if component.get(key):
                    lines.append(f"  - {key}: `{component[key]}`")
            scripts = component.get("scripts")
            if scripts:
                lines.append(f"  - scripts: {', '.join(sorted(scripts.keys()))}")
        lines.append("")
    if report["service_scripts"]:
        lines.extend(["## 服务脚本", ""])
        for script in report["service_scripts"]:
            ports = ", ".join(script["ports_mentioned"]) or "未发现"
            lines.append(f"- `{script['path']}`，端口：{ports}")
        lines.append("")
    if report["candidate_commands"]:
        lines.extend(["## 候选命令", ""])
        for item in report["candidate_commands"]:
            note = f"，说明：{item['note']}" if item.get("note") else ""
            lines.append(
                f"- `{item['command']}`，工作目录 `{item['cwd']}`"
                f"（{item['purpose']}）{note}"
            )
        lines.append("")
    if report["documents"]:
        lines.extend(["## 文档入口候选", ""])
        for path in report["documents"][:80]:
            lines.append(f"- `{path}`")
        lines.append("")
    if report["top_level_dirs"]:
        lines.extend(
            [
                "## 顶层目录",
                "",
                ", ".join(f"`{path}`" for path in report["top_level_dirs"]),
                "",
            ]
        )
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
