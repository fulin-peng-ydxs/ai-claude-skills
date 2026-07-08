#!/usr/bin/env python3
"""检测 AI 约束文档生成前的候选验证命令。"""

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


def command(
    cwd: Path,
    cmd: str,
    purpose: str,
    source: str,
    *,
    required: bool = True,
    long_running: bool = False,
    success: str = "exit code 0",
    cleanup: str | None = None,
    notes: str | None = None,
) -> dict[str, Any]:
    data: dict[str, Any] = {
        "cwd": str(cwd),
        "command": cmd,
        "purpose": purpose,
        "source": source,
        "required_for_landing": required,
        "success_condition": success,
    }
    if long_running:
        data["long_running"] = True
    if cleanup:
        data["cleanup"] = cleanup
    if notes:
        data["notes"] = notes
    return data


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


def package_manager(component: Path) -> tuple[str, str, str, bool]:
    if (component / "pnpm-lock.yaml").exists():
        return "pnpm", "pnpm install --frozen-lockfile", "pnpm-lock.yaml", True
    if (component / "yarn.lock").exists():
        return "yarn", "yarn install --frozen-lockfile", "yarn.lock", True
    if (component / "bun.lockb").exists() or (component / "bun.lock").exists():
        return "bun", "bun install --frozen-lockfile", "bun lock", True
    if (component / "package-lock.json").exists() or (component / "npm-shrinkwrap.json").exists():
        return "npm", "npm ci", "package-lock.json", True
    return "npm", "npm install", "package.json", False


def pm_run(pm: str, script: str) -> str:
    if pm == "npm":
        return f"npm run {script}"
    if pm == "yarn":
        return f"yarn {script}"
    if pm == "pnpm":
        return f"pnpm run {script}"
    if pm == "bun":
        return f"bun run {script}"
    return f"{pm} run {script}"


def detect_node(root: Path, files: list[Path]) -> list[dict[str, Any]]:
    components: list[dict[str, Any]] = []
    for pkg in sorted(path for path in files if path.name == "package.json"):
        component = pkg.parent
        data = read_json(pkg)
        if not data:
            continue
        deps = {}
        for key in ("dependencies", "devDependencies", "peerDependencies"):
            value = data.get(key)
            if isinstance(value, dict):
                deps.update(value)
        scripts = data.get("scripts") if isinstance(data.get("scripts"), dict) else {}
        is_vue = any(
            key in deps for key in ("vue", "@vitejs/plugin-vue", "vue-router", "pinia", "nuxt")
        ) or any((component / "src").glob("**/*.vue"))
        if not is_vue and not scripts:
            continue
        pm, install_cmd, lock_source, has_lock = package_manager(component)
        commands = [
            command(component, "node --version", "environment", "Node 运行时"),
            command(component, f"{pm} --version", "environment", f"{pm} 包管理器"),
            command(
                component,
                install_cmd,
                "dependency",
                lock_source,
                required=has_lock,
                notes="无锁文件时安装可能生成或改写锁文件，先询问用户。" if not has_lock else "如果可能访问私有源，先询问用户。",
            ),
        ]
        for script in ("test", "test:unit", "lint", "build", "preview"):
            if script in scripts:
                purpose = "build" if script == "build" else "test" if script.startswith("test") else script
                commands.append(
                    command(
                        component,
                        pm_run(pm, script),
                        purpose,
                        f"package.json scripts.{script}",
                        required=script != "preview",
                        notes="仅当文档会写入预览模式时才必验。" if script == "preview" else None,
                    )
                )
        if "dev" in scripts:
            commands.append(
                command(
                    component,
                    pm_run(pm, "dev"),
                    "local_start",
                    "package.json scripts.dev",
                    long_running=True,
                    required=False,
                    success="服务有响应或文档端口已监听",
                    cleanup="停止本次验证启动的进程",
                )
            )
        components.append(
            {
                "stack": "vue" if is_vue else "node",
                "path": rel(component, root),
                "evidence": [rel(pkg, root), lock_source],
                "package_manager": pm,
                "scripts": sorted(scripts.keys()),
                "commands": commands,
            }
        )
    return components


def python_test_paths(pyproject: dict[str, Any] | None, component: Path) -> list[str]:
    if pyproject:
        testpaths = (
            pyproject.get("tool", {})
            .get("pytest", {})
            .get("ini_options", {})
            .get("testpaths")
        )
        if isinstance(testpaths, list):
            return [str(item) for item in testpaths]
        if isinstance(testpaths, str):
            return [testpaths]
    candidates = [path.name for path in component.iterdir() if path.is_dir() and path.name == "tests"]
    if (component / "backend" / "tests").exists():
        candidates.append("backend/tests")
    return candidates


def detect_python(root: Path, files: list[Path]) -> list[dict[str, Any]]:
    markers = {"pyproject.toml", "requirements.txt", "setup.py", "setup.cfg", "tox.ini", "pytest.ini"}
    component_dirs = sorted({path.parent for path in files if path.name in markers})
    if not component_dirs and any(path.suffix == ".py" for path in files):
        component_dirs = [root]
    components: list[dict[str, Any]] = []
    for component in component_dirs:
        pyproject_path = component / "pyproject.toml"
        pyproject = read_toml(pyproject_path) if pyproject_path.exists() else None
        evidence = [rel(path, root) for path in (pyproject_path, component / "requirements.txt") if path.exists()]
        if not evidence:
            evidence = [rel(component, root)]
        requires_python = None
        has_ruff = False
        if pyproject:
            requires_python = pyproject.get("project", {}).get("requires-python")
            tool = pyproject.get("tool", {})
            has_ruff = "ruff" in tool
        commands = [
            command(component, "python --version", "environment", "Python 运行时"),
            command(component, "python -m pip --version", "environment", "pip"),
        ]
        if (component / "requirements.txt").exists():
            commands.append(command(component, "python -m pip check", "dependency", "已安装依赖", notes="依赖安装完成后使用。"))
        paths = python_test_paths(pyproject, component)
        if paths:
            commands.append(command(component, f"python -m pytest {' '.join(paths)} -q", "test", "pytest configuration"))
        elif any("pytest" in path.name for path in files):
            commands.append(command(component, "python -m pytest -q", "test", "pytest markers"))
        if has_ruff:
            commands.append(command(component, "python -m ruff check .", "lint", "pyproject.toml tool.ruff"))
        if pyproject and pyproject.get("build-system"):
            commands.append(command(component, "python -m build", "build", "pyproject.toml build-system", required=False, notes="仅当文档会写入打包构建时才必验。"))
        if (component / "backend" / "cli.py").exists():
            commands.append(
                command(
                    component,
                    "python -m backend.cli serve",
                    "local_start",
                    "backend/cli.py",
                    required=False,
                    long_running=True,
                    success="服务在文档指定的主机和端口有响应",
                    cleanup="停止本次验证启动的进程",
                )
            )
        components.append(
            {
                "stack": "python",
                "path": rel(component, root),
                "evidence": evidence,
                "requires_python": requires_python,
                "commands": commands,
            }
        )
    return components


def detect_java(root: Path, files: list[Path]) -> list[dict[str, Any]]:
    components: list[dict[str, Any]] = []
    for marker in sorted(path for path in files if path.name in {"pom.xml", "build.gradle", "build.gradle.kts"}):
        component = marker.parent
        text = ""
        try:
            text = marker.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            pass
        commands = [command(component, "java -version", "environment", "JDK")]
        if marker.name == "pom.xml":
            mvn = "./mvnw" if (component / "mvnw").exists() else "mvn"
            commands.append(command(component, f"{mvn} -version", "environment", "Maven"))
            commands.append(command(component, f"{mvn} test", "test", "pom.xml"))
            commands.append(command(component, f"{mvn} package", "build", "pom.xml"))
            if "spring-boot" in text:
                commands.append(
                    command(
                        component,
                        f"{mvn} spring-boot:run",
                        "local_start",
                        "Spring Boot plugin",
                        required=False,
                        long_running=True,
                        success="服务在文档指定的主机和端口有响应",
                        cleanup="停止本次验证启动的进程",
                    )
                )
            tool = "maven"
        else:
            gradle = "./gradlew" if (component / "gradlew").exists() else "gradle"
            commands.append(command(component, f"{gradle} --version", "environment", "Gradle"))
            commands.append(command(component, f"{gradle} test", "test", marker.name))
            commands.append(command(component, f"{gradle} build", "build", marker.name))
            if "org.springframework.boot" in text or "bootRun" in text:
                commands.append(
                    command(
                        component,
                        f"{gradle} bootRun",
                        "local_start",
                        "Spring Boot Gradle plugin",
                        required=False,
                        long_running=True,
                        success="服务在文档指定的主机和端口有响应",
                        cleanup="停止本次验证启动的进程",
                    )
                )
            tool = "gradle"
        components.append(
            {
                "stack": "java",
                "path": rel(component, root),
                "evidence": [rel(marker, root)],
                "build_tool": tool,
                "commands": commands,
            }
        )
    return components


def detect_service_scripts(root: Path, files: list[Path]) -> list[dict[str, Any]]:
    scripts: list[dict[str, Any]] = []
    for script in sorted(path for path in files if re.match(r"start.*\.sh$", path.name)):
        try:
            text = script.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            text = ""
        commands = [
            command(root, f"./{rel(script, root)} status", "status", rel(script, root), required=False),
            command(root, f"./{rel(script, root)}", "local_start", rel(script, root), required=False, long_running=True, success="脚本报告就绪或状态检查健康"),
            command(root, f"./{rel(script, root)} stop", "cleanup", rel(script, root), required=False),
        ]
        ports = extract_ports(text)
        scripts.append(
            {
                "path": rel(script, root),
                "ports_mentioned": ports,
                "commands": commands,
            }
        )
    return scripts


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


def build_report(root: Path) -> dict[str, Any]:
    files = walk_files(root)
    return {
        "root": str(root),
        "components": detect_python(root, files) + detect_node(root, files) + detect_java(root, files),
        "service_scripts": detect_service_scripts(root, files),
    }


def format_markdown(report: dict[str, Any]) -> str:
    purpose_names = {
        "environment": "环境",
        "dependency": "依赖",
        "test": "测试",
        "build": "构建",
        "lint": "Lint",
        "preview": "预览",
        "local_start": "本地启动",
        "status": "状态检查",
        "cleanup": "停止清理",
    }
    lines = [f"# 项目命令候选清单", "", f"根目录：`{report['root']}`", ""]
    for component in report["components"]:
        lines.extend([f"## {component['stack']} 组件：`{component['path']}`", ""])
        evidence = ", ".join(f"`{item}`" for item in component.get("evidence", []))
        if evidence:
            lines.extend([f"依据：{evidence}", ""])
        for cmd in component["commands"]:
            req = "必验" if cmd.get("required_for_landing") else "条件性验证"
            purpose = purpose_names.get(cmd["purpose"], cmd["purpose"])
            lines.append(f"- `{cmd['command']}`，工作目录 `{cmd['cwd']}`（{purpose}，{req}）")
            if cmd.get("notes"):
                lines.append(f"  - {cmd['notes']}")
        lines.append("")
    if report["service_scripts"]:
        lines.extend(["## 服务脚本", ""])
        for script in report["service_scripts"]:
            ports = ", ".join(script.get("ports_mentioned") or [])
            suffix = f" 提到的端口：{ports}。" if ports else ""
            lines.append(f"- `{script['path']}`。{suffix}")
            for cmd in script["commands"]:
                purpose = purpose_names.get(cmd["purpose"], cmd["purpose"])
                lines.append(f"  - `{cmd['command']}`（{purpose}）")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", nargs="?", default=".", help="Repository root")
    parser.add_argument("--format", choices=("markdown", "json"), default="markdown")
    args = parser.parse_args()

    root = Path(args.root).expanduser().resolve()
    if not root.exists() or not root.is_dir():
        print(f"Not a directory: {root}", file=sys.stderr)
        return 2

    report = build_report(root)
    if args.format == "json":
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(format_markdown(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
