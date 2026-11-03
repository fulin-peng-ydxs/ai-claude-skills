#!/usr/bin/env python3
"""Validate only the requested AI documents using their authoritative template blocks."""
from pathlib import Path
import argparse
import re
import sys

_engine = Path(__file__).resolve().parents[2] / 'skill-authoring-standard/scripts'
if not (_engine / 'validate_document_template.py').is_file():
    raise SystemExit('Missing dependency: install skill-authoring-standard and ai-constraint-doc-authoring beside this skill.')
sys.path.insert(0, str(_engine))
from validate_document_template import validate, validate_existing

TEMPLATE = Path(__file__).resolve().parents[1] / 'references/output-contract.md'
SHELL_FENCE = re.compile(r'^\s*(?:`{3,}|~{3,})\s*(?:bash|sh|shell|zsh|fish|powershell|cmd)\b', re.M | re.I)


def validate_repository(root: Path, language: str = 'auto', custom_structure: bool = False, document: str = 'both', template: Path = TEMPLATE) -> list[str]:
    errors = []
    for name, block in [('AGENTS.md', 'agents'), ('CLAUDE.md', 'claude')]:
        if document not in (block, 'both'):
            continue
        path = root / name
        if not path.is_file():
            errors.append(f'missing file: {path}')
            continue
        text = path.read_text(encoding='utf-8')
        found = validate_existing(text) if custom_structure else validate(text, template.read_text(encoding='utf-8'), block)
        errors.extend(f'{name}: {error}' for error in found)
        if block == 'claude':
            if 'AGENTS.md' not in text:
                errors.append('CLAUDE.md: must point to AGENTS.md')
            if SHELL_FENCE.search(text):
                errors.append('CLAUDE.md: shell command blocks belong in AGENTS.md')
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('root', type=Path, nargs='?')
    parser.add_argument('--document', choices=['agents', 'claude', 'both'], default='both')
    parser.add_argument('--template', type=Path, default=TEMPLATE)
    parser.add_argument('--language', choices=['auto', 'zh', 'en'], default='auto')
    parser.add_argument('--custom-structure', '--existing-structure', action='store_true', dest='existing')
    parser.add_argument('--self-test', action='store_true')
    args = parser.parse_args()
    if args.self_test:
        sample = '```document-template\n# {{@名称}}\n\n## 范围\n- 依据：{{@来源}}\n```'
        good = '# 项目\n\n## 范围\n- 依据：仓库事实\n'
        return int(bool(validate(good, sample)) or not validate(good.replace('范围', '任意'), sample))
    if not args.root:
        parser.error('root is required')
    try:
        if args.language == 'en' and args.template == TEMPLATE and not args.existing:
            errors = ['English output requires an explicit authoritative translated/project template via --template.']
        else:
            errors = validate_repository(args.root, args.language, args.existing, args.document, args.template)
    except OSError as exc:
        errors = [str(exc)]
    for error in errors:
        print(error, file=sys.stderr)
    if not errors:
        print('PASS: existing structure checks only; fixed-template conformance not checked' if args.existing else 'PASS: selected document structures; command verification and content need separate review')
    return int(bool(errors))


if __name__ == '__main__':
    raise SystemExit(main())
