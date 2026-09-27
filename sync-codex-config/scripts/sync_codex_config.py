#!/usr/bin/env python3
"""Synchronize Codex user skills and collaboration instructions to Claude and Kimi."""

from __future__ import annotations

import argparse
import filecmp
import os
import shutil
import stat
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path


IGNORED_NAMES = {
    ".DS_Store",
    ".git",
    ".idea",
    ".obsidian",
    ".system",
    "__pycache__",
    "node_modules",
}

class SyncError(RuntimeError):
    """Raised when synchronization cannot continue safely."""


@dataclass
class Counts:
    created: int = 0
    updated: int = 0
    unchanged: int = 0

    def add(self, other: "Counts") -> None:
        self.created += other.created
        self.updated += other.updated
        self.unchanged += other.unchanged


def expand_path(raw: str) -> Path:
    return Path(os.path.expandvars(os.path.expanduser(raw))).resolve(strict=False)


def default_root(primary_env: str, fallback: str, secondary_env: str | None = None) -> Path:
    value = os.environ.get(primary_env)
    if value is None and secondary_env:
        value = os.environ.get(secondary_env)
    return expand_path(value or fallback)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="将 Codex 全局技能和协作说明更新到 Claude、Kimi 用户目录。"
    )
    parser.add_argument(
        "--target",
        choices=("all", "claude", "kimi"),
        default="all",
        help="同步目标，默认 all。",
    )
    parser.add_argument(
        "--codex-root",
        type=expand_path,
        default=default_root("CODEX_HOME", "~/.codex"),
        help="Codex 用户根目录。",
    )
    parser.add_argument(
        "--claude-root",
        type=expand_path,
        default=default_root("CLAUDE_CONFIG_DIR", "~/.claude", "CLAUDE_HOME"),
        help="Claude Code 用户根目录。",
    )
    parser.add_argument(
        "--kimi-root",
        type=expand_path,
        default=default_root("KIMI_CODE_HOME", "~/.kimi-code"),
        help="Kimi Code 用户根目录。",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="只预览，不创建或更新任何文件。",
    )
    return parser.parse_args()


def is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def validate_paths(source_root: Path, targets: list[tuple[str, Path]]) -> None:
    source_skills = source_root / "skills"
    source_agents = source_root / "AGENTS.md"
    if not source_skills.is_dir():
        raise SyncError(f"Codex skills 目录不存在：{source_skills}")
    if not source_agents.is_file():
        raise SyncError(f"Codex AGENTS.md 不存在：{source_agents}")

    for label, target_root in targets:
        if target_root == source_root:
            raise SyncError(f"{label} 根目录不能与 Codex 根目录相同：{target_root}")
        if is_relative_to(target_root, source_skills):
            raise SyncError(f"{label} 根目录不能位于 Codex skills 内部：{target_root}")
        if target_root.exists() and not target_root.is_dir():
            raise SyncError(f"{label} 根路径不是目录：{target_root}")


def has_skill_frontmatter(path: Path) -> bool:
    try:
        with path.open("r", encoding="utf-8") as handle:
            first = handle.readline().strip()
            if first != "---":
                return False
            fields: set[str] = set()
            for line in handle:
                stripped = line.strip()
                if stripped == "---":
                    break
                if ":" in stripped and not stripped.startswith("#"):
                    fields.add(stripped.split(":", 1)[0].strip())
            else:
                return False
        return {"name", "description"}.issubset(fields)
    except (OSError, UnicodeError):
        return False


def read_skill_frontmatter(path: Path) -> str:
    skill_file = path if path.is_file() else path / "SKILL.md"
    try:
        with skill_file.open("r", encoding="utf-8") as handle:
            if handle.readline().strip() != "---":
                return ""
            lines: list[str] = []
            for line in handle:
                if line.strip() == "---":
                    return "".join(lines)
                lines.append(line)
    except (OSError, UnicodeError):
        return ""
    return ""


def is_excluded_mcp_skill(path: Path) -> bool:
    """Return whether a skill is identified as MCP-related."""
    identity = f"{path.stem if path.is_file() else path.name}\n{read_skill_frontmatter(path)}"
    return "mcp" in identity.casefold()


def discover_skills(skills_root: Path) -> tuple[list[Path], list[Path]]:
    skills: list[Path] = []
    excluded_skills: list[Path] = []
    for entry in sorted(skills_root.iterdir(), key=lambda item: item.name):
        if entry.name.startswith(".") or entry.name in IGNORED_NAMES:
            continue
        is_skill = (
            entry.is_dir()
            and not entry.is_symlink()
            and (entry / "SKILL.md").is_file()
        ) or (
            entry.is_file()
            and entry.suffix.lower() == ".md"
            and has_skill_frontmatter(entry)
        )
        if not is_skill:
            continue
        if is_excluded_mcp_skill(entry):
            excluded_skills.append(entry)
        else:
            skills.append(entry)
    return skills, excluded_skills


def destination_kind_conflicts(source: Path, destination: Path) -> bool:
    if not destination.exists() and not destination.is_symlink():
        return False
    if source.is_symlink():
        return destination.is_dir() and not destination.is_symlink()
    if source.is_dir():
        return not destination.is_dir() or destination.is_symlink()
    return destination.is_dir() or destination.is_symlink()


def files_equal(source: Path, destination: Path) -> bool:
    return (
        destination.is_file()
        and not destination.is_symlink()
        and filecmp.cmp(source, destination, shallow=False)
        and stat.S_IMODE(source.stat().st_mode) == stat.S_IMODE(destination.stat().st_mode)
    )


def sync_entry(source: Path, destination: Path, dry_run: bool) -> Counts:
    if destination_kind_conflicts(source, destination):
        raise SyncError(f"路径类型冲突：{source} -> {destination}")

    if source.is_symlink():
        link_target = os.readlink(source)
        if destination.is_symlink() and os.readlink(destination) == link_target:
            return Counts(unchanged=1)
        existed = destination.exists() or destination.is_symlink()
        if not dry_run:
            if destination.is_symlink() or destination.is_file():
                destination.unlink()
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.symlink_to(link_target, target_is_directory=source.is_dir())
        return Counts(updated=1) if existed else Counts(created=1)

    if source.is_dir():
        existed = destination.exists()
        if not dry_run:
            destination.mkdir(parents=True, exist_ok=True)
        counts = Counts(unchanged=1) if existed else Counts(created=1)
        for child in sorted(source.iterdir(), key=lambda item: item.name):
            if child.name in IGNORED_NAMES or child.suffix == ".pyc":
                continue
            counts.add(sync_entry(child, destination / child.name, dry_run))
        return counts

    if files_equal(source, destination):
        return Counts(unchanged=1)
    existed = destination.exists() or destination.is_symlink()
    if not dry_run:
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination, follow_symlinks=False)
    return Counts(updated=1) if existed else Counts(created=1)


def sync_document(source: Path, destination: Path, dry_run: bool) -> str:
    if destination.exists() and destination.is_dir():
        raise SyncError(f"文档目标是目录：{destination}")
    if files_equal(source, destination):
        return "未变化"
    status = "更新" if destination.exists() or destination.is_symlink() else "新增"
    if dry_run:
        return status

    destination.parent.mkdir(parents=True, exist_ok=True)
    file_descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{destination.name}.", dir=destination.parent
    )
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(file_descriptor, "wb") as target_handle, source.open("rb") as source_handle:
            shutil.copyfileobj(source_handle, target_handle)
        shutil.copymode(source, temporary_path)
        os.replace(temporary_path, destination)
    finally:
        if temporary_path.exists():
            temporary_path.unlink()
    return status


def selected_targets(args: argparse.Namespace) -> list[tuple[str, Path]]:
    targets: list[tuple[str, Path]] = []
    if args.target in ("all", "claude"):
        targets.append(("Claude", args.claude_root))
    if args.target in ("all", "kimi"):
        targets.append(("Kimi", args.kimi_root))
    return targets


def target_document_name(label: str) -> str:
    if label == "Claude":
        return "CLAUDE.md"
    return "AGENTS.md"


def main() -> int:
    args = parse_args()
    targets = selected_targets(args)
    try:
        validate_paths(args.codex_root, targets)
        source_skills_root = args.codex_root / "skills"
        source_agents = args.codex_root / "AGENTS.md"
        skills, excluded_skills = discover_skills(source_skills_root)
        if not skills:
            raise SyncError(f"未发现可同步技能：{source_skills_root}")

        mode = "预览" if args.dry_run else "执行"
        print(f"模式：{mode}")
        print(f"Codex 源：{args.codex_root}")
        print(f"发现技能：{len(skills)}")
        if excluded_skills:
            excluded_names = "、".join(skill.name for skill in excluded_skills)
            print(f"排除 MCP 相关技能：{len(excluded_skills)}（{excluded_names}）")

        for label, target_root in targets:
            skill_counts = Counts()
            for skill in skills:
                skill_destination = target_root / "skills" / skill.name
                existed = skill_destination.exists() or skill_destination.is_symlink()
                result = sync_entry(skill, skill_destination, args.dry_run)
                if not existed:
                    skill_counts.created += 1
                elif result.created or result.updated:
                    skill_counts.updated += 1
                else:
                    skill_counts.unchanged += 1
            document_name = target_document_name(label)
            document_status = sync_document(
                source_agents, target_root / document_name, args.dry_run
            )
            print(
                f"{label}：{target_root} | "
                f"技能新增 {skill_counts.created}、更新 {skill_counts.updated}、"
                f"未变化 {skill_counts.unchanged} | {document_name} {document_status}"
            )
        return 0
    except (OSError, SyncError) as error:
        print(f"错误：{error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
