#!/usr/bin/env python3
"""Check user skill identities; semantic naming rules remain in skill-naming.md."""

import argparse
import re
from pathlib import Path

import yaml


CAPABILITIES = {
    "authoring", "design", "analysis", "review", "audit", "refactoring",
    "governance", "maintenance", "management", "sync", "workflow", "standard",
}
DOMAINS = {
    "ai", "automation", "backend", "business", "code", "config", "design",
    "development", "frontend", "git", "investment", "project", "requirement",
    "skill", "system", "operation",
}
EXCEPTIONS = {"git-push"}
WEAK_WORDS = {"auto", "smart", "advanced", "msg", "dev"}


def validate_skill(path):
    """Return actionable errors without modifying skill files."""
    path = Path(path)
    errors = []
    try:
        text = (path / "SKILL.md").read_text(encoding="utf-8")
        match = re.match(r"\A---\r?\n(.*?)\r?\n---(?:\r?\n|$)", text, re.S)
        if not match:
            return ["SKILL.md 缺少有效 YAML frontmatter"]
        metadata = yaml.safe_load(match.group(1))
    except (OSError, UnicodeError, yaml.YAMLError) as error:
        return [f"无法读取技能元数据：{error}"]
    if not isinstance(metadata, dict):
        return ["技能元数据必须为映射"]
    name = metadata.get("name")
    if not isinstance(name, str) or not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", name) or len(name) > 64:
        errors.append("name 须为不超过 64 字符的小写 kebab-case 标识")
    else:
        if path.name != name:
            errors.append("技能目录名与 name 不一致")
        words = name.split("-")
        if words[0] not in DOMAINS:
            errors.append("name 须以统一一级领域开头，细分对象或范围放在后续层级")
        if any(word in WEAK_WORDS or re.fullmatch(r"v\d+", word) for word in words):
            errors.append("name 含弱语义修饰、非规范缩写或版本标记")
        if name not in EXCEPTIONS and (len(words) < 2 or words[-1] not in CAPABILITIES):
            errors.append("name 须以规范任务能力词结尾，并包含一级领域")
    title_match = re.search(r"^# ([^\n]+)$", text[match.end():], re.M)
    title = title_match.group(1).strip() if title_match else ""
    if not re.search(r"[\u3400-\u9fff]", title):
        errors.append("正文一级标题须为中文名称")
    if re.search(r"(?:生成器|分析器|设计器|审查器|维护者|助手)$", title):
        errors.append("中文名称不得以角色词结尾")
    ui_path = path / "agents/openai.yaml"
    if ui_path.exists():
        try:
            ui = yaml.safe_load(ui_path.read_text(encoding="utf-8"))
            if not isinstance(ui, dict) or not isinstance(ui.get("interface"), dict):
                errors.append("UI 元数据须包含 interface 映射")
            else:
                interface = ui["interface"]
                if "display_name" in interface and interface["display_name"] != title:
                    errors.append("display_name 与正文中文名称不一致")
                if "default_prompt" in interface:
                    prompt = interface["default_prompt"]
                    if not isinstance(prompt, str) or not isinstance(name, str) or not re.search(r"\$" + re.escape(name) + r"(?![a-z0-9-])", prompt):
                        errors.append("default_prompt 须通过 $当前技能标识 引用本技能")
        except (OSError, UnicodeError, yaml.YAMLError) as error:
            errors.append(f"无法读取 UI 元数据：{error}")
    return errors


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="+", type=Path, help="自有技能目录或仅包含自有技能的根目录")
    args = parser.parse_args()
    paths = set()
    for supplied in args.paths:
        if (supplied / "SKILL.md").is_file():
            paths.add(supplied.resolve())
        elif supplied.is_dir():
            found = {p.resolve() for p in supplied.iterdir() if not p.name.startswith(".") and (p / "SKILL.md").is_file()}
            if not found:
                parser.error(f"未找到用户技能：{supplied}")
            paths.update(found)
        else:
            parser.error(f"目录不存在：{supplied}")
    failures = 0
    for path in sorted(paths):
        errors = validate_skill(path)
        for error in errors:
            print(f"{path}: {error}")
        failures += bool(errors)
    print(f"检查 {len(paths)} 个技能，{failures} 个失败")
    return int(bool(failures))


if __name__ == "__main__":
    raise SystemExit(main())
