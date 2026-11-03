#!/usr/bin/env python3
"""Validate fixed Markdown artifacts using their authoritative template blocks."""
from __future__ import annotations

import argparse
from dataclasses import dataclass, field
from pathlib import Path
import re
import sys

_parser_dir = Path(__file__).resolve().parents[2] / 'ai-constraint-doc-authoring/scripts'
if not (_parser_dir / 'document_markdown.py').is_file():
    raise SystemExit('Missing dependency: install ai-constraint-doc-authoring beside this skill.')
sys.path.insert(0, str(_parser_dir))
from document_markdown import fenced_lines, fences_closed, has_content, prose_without_fences, table_cells

PLACEHOLDER = re.compile(r'\{\{@[^{}\n]+\}\}')
HEADING = re.compile(r'^(#{1,6})\s+(.+?)\s*#*\s*$')
REPEAT = re.compile(r'\s*<!-- repeat(?P<required>-required)? -->\s*$')
FIELD = re.compile(r'^(?:- )?([^\n：:]+[：:])(.*)$')
UNFINISHED = re.compile(r'\{\{@|\b(?:TODO|TBD)\s*:', re.I)
ABSENCE_VALUE = r'(?:无|不适用)[：:，； ]+\S[^\n]*'
ABSENT = re.compile(r'^(?:- )?(?:条目情况|适用性)：' + ABSENCE_VALUE + r'$', re.M)
TABLE_ABSENT = re.compile(r'^(?:- )?条目情况：' + ABSENCE_VALUE + r'$')
VERBATIM = 'text verbatim'


@dataclass
class Node:
    title: str = ''
    level: int = 0
    repeat: bool = False
    required: bool = False
    body: list[str] = field(default_factory=list)
    children: list['Node'] = field(default_factory=list)


@dataclass(frozen=True)
class CodeFence:
    start: int
    end: int
    info: str
    content: str


def code_fences(lines: list[str]) -> list[CodeFence]:
    """Group the shared lexer's fence spans; matching rules stay in that lexer."""
    result = []
    opening = None
    for index, (line, kind) in enumerate(fenced_lines('\n'.join(lines))):
        if kind != 'marker':
            continue
        if opening is None:
            info = re.match(r'^\s*(?:`+|~+)(.*)$', line)[1].strip()
            opening = (index, info)
        else:
            start, info = opening
            result.append(CodeFence(start, index + 1, info, '\n'.join(lines[start + 1:index])))
            opening = None
    if opening is not None:
        start, info = opening
        result.append(CodeFence(start, len(lines), info, '\n'.join(lines[start + 1:])))
    return result


def check_code(expected: Node, actual: Node, where: str) -> list[str]:
    expected_blocks = code_fences(expected.body)
    actual_blocks = code_fences(actual.body)
    errors = []
    matching_count = len(expected_blocks) == len(actual_blocks)
    if expected_blocks and not matching_count:
        errors.append(f'{where}: declared code block count differs from template')
    literal_lines = set()
    for index, block in enumerate(actual_blocks):
        if 'verbatim' in block.info.split():
            errors.append(f'{where}: document contains a template-only verbatim marker')
        declared = expected_blocks[index] if matching_count and index < len(expected_blocks) else None
        if declared and not block.content.strip():
            errors.append(f'{where}: declared code block is empty')
        if declared and declared.info == VERBATIM:
            if block.content.strip() == declared.content.strip():
                errors.append(f'{where}: verbatim source slot is still unfilled')
            literal_lines.update(range(block.start, block.end))
    checked = '\n'.join(line for index, line in enumerate(actual.body) if index not in literal_lines)
    if '{{@' in checked or '<!-- repeat' in checked:
        errors.append(f'{where}: body contains unfilled placeholders or template markers')
    pending = code_fences(checked.splitlines())
    while pending:
        block = pending.pop()
        if 'document-template' in block.info:
            errors.append(f'{where}: document contains a template wrapper')
            break
        # Ordinary code cannot hide a wrapper inside a longer outer fence.
        # Declared verbatim sources were removed from checked above.
        pending.extend(code_fences(block.content.splitlines()))
    return errors


def template_blocks(text: str) -> dict[str, str]:
    """Read explicitly marked fenced blocks without treating examples as contracts."""
    result: dict[str, str] = {}
    lines = text.splitlines()
    index = 0
    while index < len(lines):
        match = re.fullmatch(r'(`{3,}|~{3,})document-template(?: ([a-z][a-z0-9-]*))?\s*', lines[index])
        if not match:
            index += 1
            continue
        fence, name = match[1], match[2] or 'document'
        start = index + 1
        index = start
        while index < len(lines) and not re.fullmatch(re.escape(fence[0]) + '{' + str(len(fence)) + r',}\s*', lines[index]):
            index += 1
        if index == len(lines):
            raise ValueError(f'unclosed document-template block: {name}')
        if name in result:
            raise ValueError(f'duplicate document-template block: {name}')
        result[name] = '\n'.join(lines[start:index])
        index += 1
    if not result:
        raise ValueError('missing document-template block')
    return result


def parse_tree(text: str, template: bool = False) -> Node:
    root = Node()
    stack = [root]
    for line, kind in fenced_lines(text):
        match = HEADING.match(line) if kind == 'prose' else None
        if not match:
            stack[-1].body.append(line)
            continue
        title = match[2]
        marker = REPEAT.search(title) if template else None
        if marker:
            title = title[:marker.start()]
        node = Node(title, len(match[1]), bool(marker), bool(marker and marker['required']))
        while stack[-1].level >= node.level:
            stack.pop()
        stack[-1].children.append(node)
        stack.append(node)
    return root


def title_matches(pattern: str, title: str) -> bool:
    parts = re.split(f'({PLACEHOLDER.pattern})', pattern)
    regex = ''.join(r'.+?' if PLACEHOLDER.fullmatch(part) else re.escape(part) for part in parts)
    return bool(re.fullmatch(regex, title))


def table_headers(lines: list[str]) -> list[tuple[int, str]]:
    result = []
    for index in range(len(lines) - 1):
        if lines[index].strip().startswith('|') and re.fullmatch(r'\s*\|?\s*:?-{3,}:?\s*(?:\|\s*:?-{3,}:?\s*)+\|?\s*', lines[index + 1]):
            result.append((index, '|'.join(table_cells(lines[index]))))
    return result


def table_rows(lines: list[str], header_index: int) -> list[list[str]]:
    rows = []
    for line in lines[header_index + 2:]:
        if not line.strip().startswith('|'):
            break
        rows.append(table_cells(line))
    return rows


def body_prose(lines: list[str]) -> list[str]:
    """Hide code while retaining physical offsets for table-local reasons."""
    return [line if kind == 'prose' else '' for line, kind in fenced_lines('\n'.join(lines))]


def table_absences(body: list[str], prose: list[str]) -> dict[int, int]:
    """Bind a reason only to the empty table immediately before it."""
    bindings = {}
    for index, _ in table_headers(prose):
        if table_rows(prose, index):
            continue
        following = next((i for i in range(index + 2, len(body)) if body[i].strip()), None)
        if following is not None and TABLE_ABSENT.fullmatch(body[following]):
            bindings[index] = following
    return bindings


def rows_match(schema: list[list[str]], rows: list[list[str]]) -> bool:
    """Literal first cells identify fixed rows; variable first cells repeat in place."""
    if not schema:
        return True  # A header-only template declares no row identities or patterns.
    fixed_ids = {row[0] for row in schema if not PLACEHOLDER.search(row[0])}
    positions = {0}
    for pattern in schema:
        repeated = bool(PLACEHOLDER.search(pattern[0]))
        def matches(row):
            return (len(row) == len(pattern)
                    and (not repeated or row[0] not in fixed_ids)
                    and all(title_matches(part, value) for part, value in zip(pattern, row)))
        if repeated:
            # Keep all valid endpoints so overlapping variable patterns do not
            # greedily consume later rows. Iteration also handles long tables.
            for position in range(len(rows)):
                if position in positions and matches(rows[position]):
                    positions.add(position + 1)
        else:
            positions = {position + 1 for position in positions
                         if position < len(rows) and matches(rows[position])}
    return len(rows) in positions


def check_body(expected: Node, actual: Node, where: str) -> list[str]:
    errors = check_code(expected, actual, where)
    expected_lines = prose_without_fences('\n'.join(expected.body)).splitlines()
    actual_lines = body_prose(actual.body)
    fields = []
    # Frontmatter belongs to the artifact's machine contract (e.g. skill-creator),
    # rather than the Markdown field namespace below its first heading.
    for line in expected_lines if expected.level else []:
        match = FIELD.match(line.strip())
        if match and PLACEHOLDER.search(match[2]):
            fields.append(('- ' if line.startswith('- ') else '', match[1]))
    labels = {label for _, label in fields}
    observed_fields = []
    for line in actual_lines:
        # Indented lines continue a field; quotes and table cells are content,
        # not declarations in the current section's fixed field namespace.
        if line[:1].isspace() or line.startswith(('|', '>')):
            continue
        match = FIELD.match(line)
        if match and match[1] in labels:
            prefix = line[:len(line) - len(line.lstrip())] + ('- ' if line.lstrip().startswith('- ') else '')
            observed_fields.append((prefix, match[1]))
            if not match[2].strip():
                errors.append(f'{where}: empty field {match[1]}')
        elif fields and match and not ABSENT.fullmatch(line):
            errors.append(f'{where}: unexpected field {match[1]}')
    if observed_fields != fields:
        errors.append(f'{where}: fields missing, duplicated or out of order; expected {fields}, found {observed_fields}')
    expected_tables = table_headers(expected_lines)
    actual_tables = table_headers(actual_lines)
    absence_bindings = table_absences(actual.body, actual_lines)
    if [header for _, header in actual_tables] != [header for _, header in expected_tables]:
        errors.append(f'{where}: table columns or table order differ from template')
    for table_index, (index, header) in enumerate(actual_tables):
        column_count = len(table_cells(actual_lines[index]))
        data = table_rows(actual_lines, index)
        for cells in data:
            if len(cells) != column_count or any(not cell for cell in cells):
                errors.append(f'{where}: table row has missing/empty columns')
        if table_index < len(expected_tables):
            schema = table_rows(expected_lines, expected_tables[table_index][0])
            if not rows_match(schema, data):
                errors.append(f'{where}: fixed table rows or row patterns are missing, duplicated, unexpected or out of order')
        if not data and index not in absence_bindings:
            errors.append(f'{where}: table {header!r} has no records and no immediately following table-specific absence reason')
    if (fields or expected_tables or (not expected.children and has_content('\n'.join(expected.body)))) and not has_content('\n'.join(actual.body)):
        errors.append(f'{where}: empty body')
    return errors


def check_node(expected: Node, actual: Node, where: str = 'document') -> list[str]:
    errors = check_body(expected, actual, where)
    standalone_absence = False
    if any(child.repeat and not child.required for child in expected.children):
        prose = body_prose(actual.body)
        table_reasons = set(table_absences(actual.body, prose).values())
        standalone_absence = bool(ABSENT.search('\n'.join(
            line for index, line in enumerate(prose) if index not in table_reasons)))
    titles = [child.title for child in actual.children]
    if len(titles) != len(set(titles)):
        errors.append(f'{where}: duplicate sibling headings')
    position = 0
    for child in expected.children:
        count = 0
        identities = set()
        while position < len(actual.children):
            observed = actual.children[position]
            if observed.level != child.level or not title_matches(child.title, observed.title):
                break
            # Numbered items use their stable identifier; named items use the full title.
            identifier_pattern = re.split('[：:]', child.title, maxsplit=1)[0]
            identity = re.split('[：:]', observed.title, maxsplit=1)[0] if PLACEHOLDER.search(identifier_pattern) else observed.title
            if child.repeat and identity in identities:
                errors.append(f'{where}: duplicate repeated entry identity {identity}')
            identities.add(identity)
            errors.extend(check_node(child, observed, f'{where}/{observed.title}'))
            position += 1
            count += 1
            if not child.repeat:
                break
        if not count:
            if not child.repeat or child.required:
                errors.append(f'{where}: missing or out-of-order heading {child.title}')
            elif not standalone_absence:
                errors.append(f'{where}: omitted repeated entries require 条目情况：无/不适用 and a reason')
    for child in actual.children[position:]:
        errors.append(f'{where}: unexpected, duplicate or out-of-order heading {child.title}')
    return errors


def check_template(text: str) -> list[str]:
    errors = []
    try:
        blocks = template_blocks(text)
    except ValueError as exc:
        return [str(exc)]
    for name, skeleton in blocks.items():
        if not fences_closed(skeleton):
            errors.append(f'{name}: template contains an unclosed code fence')
        if '{{@' in PLACEHOLDER.sub('', skeleton):
            errors.append(f'{name}: template contains a malformed placeholder')
        root = parse_tree(skeleton, True)
        if not root.children:
            errors.append(f'{name}: template has no headings')
        def walk(node):
            patterns = set()
            lines = prose_without_fences('\n'.join(node.body)).splitlines()
            for index, _ in table_headers(lines):
                rows = table_rows(lines, index)
                columns = len(table_cells(lines[index]))
                if any(len(row) != columns or any(not cell for cell in row) for row in rows):
                    errors.append(f'{name}: template table row has missing/empty columns')
                identities = [row[0] for row in rows if row and not PLACEHOLDER.search(row[0])]
                if len(identities) != len(set(identities)):
                    errors.append(f'{name}: duplicate fixed table row identity')
            for block in code_fences(node.body):
                if 'verbatim' in block.info.split() and (
                        block.info != VERBATIM or not PLACEHOLDER.fullmatch(block.content.strip())):
                    errors.append(f'{name}: verbatim fence must contain exactly one source placeholder')
            for child in node.children:
                pattern = PLACEHOLDER.sub('{{@}}', child.title)
                if pattern in patterns:
                    errors.append(f'{name}: duplicate sibling heading pattern {child.title}')
                patterns.add(pattern)
                if child.level != node.level + 1:
                    errors.append(f'{name}: skipped heading level at {child.title}')
                if child.repeat and not PLACEHOLDER.search(child.title):
                    errors.append(f'{name}: repeated heading needs a variable identity')
                if not child.children and not has_content('\n'.join(child.body)):
                    errors.append(f'{name}: heading has no fillable body: {child.title}')
                walk(child)
        walk(root)
    return errors


def validate(text: str, template_text: str, block: str = 'document') -> list[str]:
    try:
        blocks = template_blocks(template_text)
        if block not in blocks:
            return [f'unknown template block: {block}']
        errors = check_template(template_text)
        if errors:
            return errors
        expected = parse_tree(blocks[block], True)
        actual = parse_tree(text)
        errors = check_node(expected, actual)
        if not fences_closed(text):
            errors.append('document contains an unclosed code fence')
        prose = prose_without_fences(text)
        if UNFINISHED.search(prose) or '<!-- repeat' in prose:
            errors.append('document contains unfilled placeholders or template markers')
        return errors
    except ValueError as exc:
        return [str(exc)]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('document', type=Path, nargs='?')
    parser.add_argument('--template', type=Path, required=True)
    parser.add_argument('--block', default='document')
    parser.add_argument('--check-template', action='store_true')
    args = parser.parse_args()
    try:
        contract = args.template.read_text(encoding='utf-8')
        if args.check_template:
            errors = check_template(contract)
        elif args.document:
            errors = validate(args.document.read_text(encoding='utf-8'), contract, args.block)
        else:
            parser.error('document is required unless --check-template is used')
    except (OSError, ValueError) as exc:
        errors = [str(exc)]
    for error in errors:
        print(error, file=sys.stderr)
    if not errors:
        print('PASS: template structure' if args.check_template else 'PASS: fixed document structure; content and runtime evidence need separate review')
    return bool(errors)


def validate_existing(text: str) -> list[str]:
    """Check an existing document without claiming migration to a new template."""
    root = parse_tree(text)
    errors = []
    if len(root.children) != 1 or root.children[0].level != 1:
        errors.append('existing document must have exactly one level-1 title')
    def walk(node):
        seen = set()
        for child in node.children:
            if child.title in seen:
                errors.append(f'duplicate heading: {child.title}')
            seen.add(child.title)
            if not child.children and not has_content('\n'.join(child.body)):
                errors.append(f'empty section: {child.title}')
            walk(child)
    walk(root)
    if UNFINISHED.search(prose_without_fences(text)):
        errors.append('document contains unfilled placeholders')
    return errors


def artifact_cli(default_template: Path) -> int:
    """Shared CLI for existing README and architecture entrypoints."""
    parser = argparse.ArgumentParser(description='Validate against the authoritative fixed template.')
    parser.add_argument('document', type=Path, nargs='?')
    parser.add_argument('--template', type=Path, default=default_template)
    parser.add_argument('--custom-structure', '--existing-structure', action='store_true', dest='existing', help='Existing document preservation only; does not certify the fixed template.')
    parser.add_argument('--self-test', action='store_true')
    args = parser.parse_args()
    if args.self_test:
        example = '```document-template\n# {{@名称}}\n\n## 范围\n- 依据：{{@来源}}\n```'
        good = '# 工程\n\n## 范围\n- 依据：已核对仓库\n'
        return int(bool(validate(good, example)) or not validate(good.replace('范围', '任意标题'), example))
    if not args.document:
        parser.error('document is required')
    try:
        text = args.document.read_text(encoding='utf-8')
        if args.existing:
            errors = validate_existing(text)
        else:
            errors = validate(text, args.template.read_text(encoding='utf-8'))
    except OSError as exc:
        errors = [str(exc)]
    for error in errors:
        print(error, file=sys.stderr)
    if not errors:
        print('PASS: existing structure checks only; fixed-template conformance not checked' if args.existing else 'PASS: fixed document structure; content and runtime evidence need separate review')
    return int(bool(errors))


if __name__ == '__main__':
    raise SystemExit(main())
