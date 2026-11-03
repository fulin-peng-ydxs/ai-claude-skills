#!/usr/bin/env python3
"""Check user skill identities; semantic naming rules remain in skill-naming.md."""

import argparse
import re
from pathlib import Path
import sys

import yaml


_parser_dir = Path(__file__).resolve().parents[2] / 'ai-constraint-doc-authoring/scripts'
if not (_parser_dir / 'document_markdown.py').is_file():
    raise SystemExit('Missing dependency: install ai-constraint-doc-authoring beside this skill.')
sys.path.insert(0, str(_parser_dir))
from document_markdown import fenced_lines, table_cells

REFERENCE = Path(__file__).resolve().parents[1] / 'references/skill-naming.md'


def load_vocabulary(path=REFERENCE):
    """Read maintained vocabulary from the existing naming contract, failing closed."""
    tables = {'一级领域': set(), '任务能力词': set()}
    terms = {}
    section = ''
    for line, kind in fenced_lines(Path(path).read_text(encoding='utf-8')):
        if kind != 'prose':
            continue
        if line.startswith('## '):
            section = line[3:].strip()
        if section in tables and line.startswith('|'):
            cells = table_cells(line)
            match = re.fullmatch(r'`([a-z]+)`', cells[0]) if cells else None
            if cells and cells[0] not in {'一级领域', '能力词'} and not re.fullmatch(r':?-{3,}:?', cells[0]) and not match:
                raise ValueError(f'命名规范词表条目格式无效：{section}')
            if match:
                if match[1] in tables[section]:
                    raise ValueError(f'命名规范词表重复：{section}/{match[1]}')
                tables[section].add(match[1])
        for label in ['非规范缩写', '弱语义词', '保留例外']:
            match = re.match(r'^(?:- )?' + label + r'：(.*?)(?:；|$)', line)
            if match:
                if label in terms:
                    raise ValueError(f'命名规范词条重复：{label}')
                if not re.fullmatch(r'\s*`[a-z0-9]+(?:-[a-z0-9]+)*`(?:[、，,]\s*`[a-z0-9]+(?:-[a-z0-9]+)*`)*\s*', match[1]):
                    raise ValueError(f'命名规范词条格式无效：{label}')
                values = re.findall(r'`([a-z0-9]+(?:-[a-z0-9]+)*)`', match[1])
                if not values or len(values) != len(set(values)):
                    raise ValueError(f'命名规范词条无效：{label}')
                terms[label] = set(values)
    for label, values in tables.items():
        if not values:
            raise ValueError(f'命名规范缺少有效词表：{label}')
    for label in ['非规范缩写', '弱语义词', '保留例外']:
        if label not in terms:
            raise ValueError(f'命名规范缺少词条：{label}')
    return tables['一级领域'], tables['任务能力词'], terms['保留例外'], terms['非规范缩写'] | terms['弱语义词']


try:
    DOMAINS, CAPABILITIES, EXCEPTIONS, WEAK_WORDS = load_vocabulary()
except (OSError, ValueError) as error:
    raise SystemExit(f'无法读取命名规范：{error}') from None


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
