"""Contract regressions: fixed fields, hierarchy, repetition and real template consumers."""
from pathlib import Path
import importlib.util
import re
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'skill-authoring-standard/scripts'))
import validate_document_template as check

CONTRACT = '''````document-template
# {{@报告名称}}

## 结论与范围
- 范围：{{@实际范围}}
- 结论：{{@证据支持的判断}}

## 问题与处理

### Q{{@序号}}：{{@名称}} <!-- repeat -->
- 证据：{{@具体来源}}
- 影响：{{@实际影响}}
- 验证：{{@结果或未执行原因}}

## 验证覆盖

| 场景 | 结果 | 证据 |
| --- | --- | --- |
| {{@场景}} | {{@真实结果}} | {{@定位}} |
````'''

GOOD = '''# 导出行为核查

## 结论与范围
- 范围：仅核查模拟导出接口及权限；用例是假设样例。
- 结论：无权限用户仍可触发导出，存在访问边界缺口。

## 问题与处理

### Q1：无权限导出
- 证据：模拟 fixture 的入口未调用授权检查。
- 影响：未获授权的用户能够导出本应不可见的数据。
- 验证：待验证：需补无权限调用用例，当前仅为格式样例。

## 验证覆盖

| 场景 | 结果 | 证据 |
| --- | --- | --- |
| 无权限调用 | 未执行；需要隔离环境 | fixture，不作为实际项目证据 |
'''


def filled(skeleton):
    """Create syntax fixtures only, never represent these as verified project reports."""
    out = skeleton
    out = re.sub(r' <!-- repeat(?:-required)? -->', '', out)
    out = out.replace(' <!-- flexible-body -->', '')
    out = re.sub(r'^(`{3,}|~{3,})text verbatim$', r'\1text', out, flags=re.M)
    out = check.PLACEHOLDER.sub('样例1', out)
    lines = out.splitlines()
    # Templates may declare a table with header only; add a nonempty test record.
    for index, header in reversed(check.table_headers(lines)):
        if index + 2 >= len(lines) or not lines[index + 2].strip().startswith('|'):
            lines.insert(index + 2, '| ' + ' | '.join(['无：隔离格式样例'] * len(header.split('|'))) + ' |')
    return '\n'.join(lines) + '\n'


class FixedDocumentTests(unittest.TestCase):
    def test_operation_templates_reserve_recovery_and_listening_facts(self):
        source = (ROOT / 'operation-workflow/references/output-templates.md').read_text()
        blocks = check.template_blocks(source)
        unit = filled(blocks['unit'])
        recovery = '- 备份与恢复现状：样例1'
        # Unknown recovery stays explicit and may use a field-owned table.
        detailed = unit.replace(recovery, '- 备份与恢复现状：\n\n'
                                '  | 对象 | 证据与缺口 |\n  | --- | --- |\n'
                                '  | 测试数据 | 未核实：备份责任人及演练未知 |\n')
        self.assertEqual([], check.validate(detailed, source, 'unit'))
        self.assertTrue(check.validate(unit.replace(recovery, ''), source, 'unit'))
        index = filled(blocks['index'])
        self.assertEqual([], check.validate(index, source, 'index'))
        self.assertTrue(check.validate(index.replace('- 监听与访问边界：样例1', ''), source, 'index'))
        self.assertTrue(check.validate(index.replace('版本 / 基础状态', '实时业务健康'), source, 'index'))

    def test_owned_code_fences_use_field_relative_indentation(self):
        source = (ROOT / 'operation-workflow/references/output-templates.md').read_text()
        good = filled(check.template_blocks(source)['unit'])
        field = '- 精确命令与步骤：样例1'
        for indent in [2, 3, 4, 5]:
            for fence in ['```', '~~~~']:
                for inline in ['', '仅为隔离格式样例，未执行。']:
                    with self.subTest(indent=indent, fence=fence, inline=inline):
                        pad = ' ' * indent
                        opening = field.replace('样例1', inline) + '\n\n' + pad + fence + 'bash\n'
                        body = pad + 'printf example\n'
                        closing = pad + fence + '\n'
                        closed = good.replace(field, opening + body + closing, 1)
                        self.assertEqual([], check.validate(closed, source, 'unit'))
                        broken = good.replace(field, opening + body, 1)
                        errors = check.validate(broken, source, 'unit')
                        self.assertTrue(any('unclosed code fence' in error for error in errors), errors)
                        empty = good.replace(field, opening + closing, 1)
                        self.assertTrue(check.validate(empty, source, 'unit'))
        # A fixed code block inside a field uses the same relative fence view.
        declared = '````document-template\n# 命令\n- 步骤：{{@说明}}\n\n    ```bash\n    {{@命令}}\n    ```\n````'
        closed = '# 命令\n- 步骤：静态样例。\n\n    ```bash\n    printf example\n    ```\n'
        self.assertEqual([], check.validate(closed, declared))
        wrapper = '- 精确命令与步骤：\n\n    `````text\n    ```document-template\n    # 未授权模板包装\n    ```\n    `````\n'
        self.assertTrue(check.validate(good.replace(field, wrapper, 1), source, 'unit'))

    def test_all_code_blocks_need_a_declared_location_without_fixed_code(self):
        source = (ROOT / 'operation-workflow/references/output-templates.md').read_text()
        good = filled(check.template_blocks(source)['unit'])
        diagram = '```mermaid\nflowchart LR\n  A --> B\n```\n'
        for indent in [0, 1]:
            block = ''.join(' ' * indent + line + '\n' for line in diagram.splitlines())
            before = good.replace('## 1. 单位范围与运行事实\n', '## 1. 单位范围与运行事实\n\n' + block, 1)
            between = good.replace('- 成员、环境与版本：', block + '- 成员、环境与版本：', 1)
            after = good + '\n' + block
            for text in [before, between, after]:
                with self.subTest(indent=indent, document=text):
                    self.assertTrue(check.validate(text, source, 'unit'))
        nested = ''.join('    ' + line + '\n' for line in diagram.splitlines())
        inside = good.replace('- 成员、环境与版本：样例1', '- 成员、环境与版本：\n\n' + nested, 1)
        self.assertEqual([], check.validate(inside, source, 'unit'))
        free = '```document-template\n# 机制\n## 说明\n{{@完整机制}}\n```'
        self.assertEqual([], check.validate('# 机制\n## 说明\n' + diagram, free))

    def test_field_slots_accept_tables_diagrams_and_block_only_values(self):
        source = '````document-template\n# 单位\n\n## 事实\n- 成员：{{@实际成员}}\n- 验证：{{@实际状态}}\n````'
        table = '  | unit-id | server-id |\n  | --- | --- |\n  | test-unit | test-server |\n'
        diagram = '  ```mermaid\n  flowchart LR\n    Server --> Unit\n  ```\n'
        command = '  ```bash\n  printf example\n  ```\n'
        for content in [table, diagram, command, table + '\n' + diagram + '\n' + command]:
            for inline in ['', '以下内容仅为隔离格式样例。']:
                with self.subTest(content=content, inline=inline):
                    document = '# 单位\n\n## 事实\n- 成员：' + inline + '\n\n' + content + '\n- 验证：未实测。\n'
                    self.assertEqual([], check.validate(document, source))
        # Plain fixed fields use the same continuation contract as list fields.
        plain_source = source.replace('- 成员：', '成员：').replace('- 验证：', '验证：')
        plain = '# 单位\n\n## 事实\n成员：\n\n' + table + '\n验证：未实测。\n'
        self.assertEqual([], check.validate(plain, plain_source))

    def test_standalone_slots_accept_mixed_blocks_between_fixed_anchors(self):
        source = '''````document-template
# 对照
## 正文
开始说明。
{{@前置分析}}
| 固定对象 | 固定结果 |
| --- | --- |
| R1 | {{@结果}} |
{{@补充分析}}
结束说明。
````'''
        extra = '| 路径 | 用途 |\n| --- | --- |\n| /example | 隔离样例 |\n'
        required = '| 固定对象 | 固定结果 |\n| --- | --- |\n| R1 | 未执行 |\n'
        diagram = '```mermaid\nflowchart LR\n  A --> B\n```\n'
        document = '# 对照\n## 正文\n开始说明。\n' + extra + '\n' + required + diagram + extra + '结束说明。\n'
        self.assertEqual([], check.validate(document, source))
        self.assertTrue(check.validate(document.replace(required, ''), source))
        self.assertTrue(check.validate(document.replace('结束说明。\n', '结束说明。\n' + extra), source))
        self.assertEqual([], check.validate(document.replace('结束说明。', '结束：固定说明。'), source.replace('结束说明。', '结束：固定说明。')))
        self.assertTrue(check.validate(document.replace('结束说明。\n', '结束：固定说明。\n' + extra), source.replace('结束说明。', '结束：固定说明。')))
        free = '```document-template\n# 机制\n## 说明\n{{@完整机制}}\n```'
        self.assertEqual([], check.validate('# 机制\n## 说明\n背景：隔离样例。\n' + extra + diagram, free))

    def test_content_tables_do_not_replace_or_reorder_declared_tables(self):
        source = '''````document-template
# 对照
## 事实
- 分析：{{@实际分析}}
| 固定对象 | 结果 |
| --- | --- |
| A | {{@结果}} |
| B | {{@结果}} |
- 证据：{{@证据}}
| 验收 | 状态 |
| --- | --- |
| C | {{@状态}} |
````'''
        first = '| 固定对象 | 结果 |\n| --- | --- |\n| A | 未执行 |\n| B | 未执行 |\n'
        second = '| 验收 | 状态 |\n| --- | --- |\n| C | 未执行 |\n'
        nested = '  | 对象 | 属性 |\n  | --- | --- |\n  | 服务 | 版本未知 |\n'
        prefix = '# 对照\n## 事实\n- 分析：隔离样例。\n' + nested + '\n'
        document = prefix + first + '- 证据：尚未采集。\n' + second
        self.assertEqual([], check.validate(document, source))
        variants = [document.replace(first, ''),
                    document.replace(first, ''.join('  ' + line + '\n' for line in first.splitlines())),
                    document.replace(first, first.replace('| A | 未执行 |\n', '')),
                    document.replace(first, first.replace('| A | 未执行 |\n| B | 未执行 |', '| B | 未执行 |\n| A | 未执行 |')),
                    document.replace(first, first.replace('| 固定对象 | 结果 |', '| 对象 | 结果 |')),
                    document.replace(first, first + first),
                    prefix + second + '- 证据：尚未采集。\n' + first]
        for document in variants:
            with self.subTest(document=document):
                self.assertTrue(check.validate(document, source))

    def test_declared_tables_inside_field_values_remain_required(self):
        source = '```document-template\n# 事实\n- 清单：{{@说明}}\n\n  | 成员 | 状态 |\n  | --- | --- |\n  | S1 | {{@状态}} |\n- 验证：{{@结果}}\n```'
        extra = '  | 路径 | 用途 |\n  | --- | --- |\n  | /example | 隔离样例 |\n'
        required = '  | 成员 | 状态 |\n  | --- | --- |\n  | S1 | 未执行 |\n'
        document = '# 事实\n- 清单：隔离样例。\n' + extra + '\n' + required + '- 验证：待核实。\n'
        self.assertEqual([], check.validate(document, source))
        self.assertTrue(check.validate(document.replace(required, ''), source))
        self.assertTrue(check.validate(document.replace(required, required + '\n' + required), source))

    def test_slot_tables_keep_syntax_empty_reason_and_outer_field_checks(self):
        source = '````document-template\n# 事实\n## 说明\n- 清单：{{@内容}}\n- 证据：{{@来源}}\n````'
        table = '  | 对象 | 结果 |\n  | --- | --- |\n  | 服务 | 未执行 |\n'
        document = '# 事实\n## 说明\n- 清单：\n\n' + table + '- 证据：隔离样例。\n'
        self.assertEqual([], check.validate(document, source))
        empty = table[:table.index('  | 服务 |')]
        self.assertEqual([], check.validate(document.replace(table, empty + '  条目情况：无：已检查，尚无对象。\n'), source))
        for bad in [document.replace('  | 服务 | 未执行 |', '  | 服务 |'),
                    document.replace('  | 服务 | 未执行 |', '  | 服务 | |'),
                    document.replace(table, empty), document.replace(table, ''),
                    document.replace(table, empty + '条目情况：无：不属于该字段的说明。\n'),
                    document.replace('- 证据：隔离样例。\n', ''),
                    document.replace('- 证据：', '- 自定义字段：越界。\n- 证据：'),
                    document + '\n## 新增章节\n越界。\n',
                    document.replace('未执行', '{{@未填}}'),
                    document.replace('- 清单：', '- 清单：\n  ```mermaid\n  flowchart LR\n    A --> B')]:
            with self.subTest(document=bad):
                self.assertTrue(check.validate(bad, source))
        self.assertTrue(check.validate(document.replace(table, '\n'.join(line[1:] for line in table.splitlines()) + '\n'), source))

    def test_content_table_separators_follow_the_header_width(self):
        source = '```document-template\n# 对照\n## 说明\n{{@完整说明}}\n```'
        one = '# 对照\n## 说明\n| 成员 |\n| --- |\n| S1 |\n'
        self.assertEqual([], check.validate(one, source))
        two = '# 对照\n## 说明\n| 成员 | 状态 |\n| --- | --- |\n| S1 | 未执行 |\n'
        self.assertEqual([], check.validate(two, source))
        for separator in ['| --- |', '| --- | --- | --- |']:
            self.assertTrue(check.validate(two.replace('| --- | --- |', separator), source))
        declared = '```document-template\n# 对照\n| 成员 | 状态 |\n| --- |\n| S1 | {{@状态}} |\n```'
        self.assertTrue(check.check_template(declared))

    def test_slot_code_does_not_change_declared_code_or_verbatim_exemptions(self):
        source = '````document-template\n# 记录\n- 分析：{{@分析}}\n\n```text verbatim\n{{@原文}}\n```\n````'
        diagram = '  ```mermaid\n  flowchart LR\n    A --> B\n  ```\n'
        raw = '原文中的 {{@示例}} 与 <!-- repeat -->'
        original = '```text\n' + raw + '\n```\n'
        document = '# 记录\n- 分析：格式样例。\n\n' + diagram + original
        self.assertEqual([], check.validate(document, source))
        for bad in [document.replace(original, ''), document + original,
                    document.replace('    A --> B', '    {{@图待填}}'),
                    document.replace('  ```mermaid', '  ```text verbatim'),
                    document.replace('  flowchart LR\n    A --> B\n', ''),
                    document.replace(raw, '{{@原文}}')]:
            with self.subTest(document=bad):
                self.assertTrue(check.validate(bad, source))

    def test_real_operation_unit_slot_can_hold_the_inventory_table(self):
        source = (ROOT / 'operation-workflow/references/output-templates.md').read_text()
        good = filled(check.template_blocks(source)['unit'])
        table = '\n\n  | unit-id | server-id | 版本 |\n  | --- | --- | --- |\n  | test-unit | test-server | 未核实 |\n'
        document = good.replace('- 成员、环境与版本：样例1', '- 成员、环境与版本：隔离格式样例。' + table)
        self.assertEqual([], check.validate(document, source, 'unit'))

    def test_declared_nested_code_is_not_swallowed_by_its_field_slot(self):
        source = '````document-template\n# 操作\n- 步骤：{{@说明}}\n\n  ```bash\n  {{@精确命令}}\n  ```\n- 验证：{{@结果}}\n````'
        declared = '  ```bash\n  printf example\n  ```\n'
        diagram = '  ```mermaid\n  flowchart LR\n    A --> B\n  ```\n'
        document = '# 操作\n- 步骤：隔离格式样例。\n\n' + diagram + declared + '- 验证：未实测。\n'
        self.assertEqual([], check.validate(document, source))
        self.assertTrue(check.validate(document.replace(declared, ''), source))
        self.assertTrue(check.validate(document.replace(declared, declared + declared), source))
        self.assertTrue(check.validate(document.replace('  ```bash', '  ```text'), source))

    def test_literal_anchors_disambiguate_identical_headers_and_code_languages(self):
        source = '''````document-template
# 对照
## 正文
{{@分析}}
以下是固定结果。
| 对象 | 结果 |
| --- | --- |
| R1 | {{@结果}} |
```bash
{{@固定命令}}
```
````'''
        extra = '| 对象 | 结果 |\n| --- | --- |\n| 临时对照 | 仅说明 |\n\n```bash\nprintf content\n```\n'
        required = '| 对象 | 结果 |\n| --- | --- |\n| R1 | 未执行 |\n```bash\nprintf required\n```\n'
        document = '# 对照\n## 正文\n' + extra + '以下是固定结果。\n' + required
        self.assertEqual([], check.validate(document, source))
        self.assertTrue(check.validate(document.replace(required, ''), source))

    def test_fixed_business_fields_allow_rich_explanation_and_still_reject_omissions(self):
        cases = [
            ('requirement-closure-design/references/closure-template.md', '功能点：', '前置、操作与反馈'),
            ('requirement-doc-authoring/references/requirement-template.md', 'R', '输入、操作与校验'),
            ('development-workflow/references/output-template.md', 'T', '实施方案'),
            ('project-module-architecture-doc-authoring/references/output-contract.md', '机制：', '处理与结果'),
            ('business-closed-loop-analysis/references/output-contract.md', '环节：', '处理与校验'),
            ('project-handover-analysis/assets/project-handover-report-template.md', '链路：', '调用与交接'),
        ]
        def find(node, prefix):
            for child in node.children:
                if child.title.startswith(prefix):
                    return child
                found = find(child, prefix)
                if found:
                    return found
        for path, prefix, field in cases:
            with self.subTest(template=path):
                source = (ROOT / path).read_text()
                skeleton = check.template_blocks(source)['document']
                good = filled(skeleton)
                original = f'- {field}：样例1'
                self.assertIn(original, good)
                expanded = f'''- {field}：隔离格式样例，不代表实际项目事实。
  1. 校验身份和必填项后提交；缺项时保留原内容并提示原因，检查状态不变。
  2. 更新状态并创建唯一任务；失败时回滚，重复请求返回原结果，判据是只产生一个任务。尚未运行验证。
  ```mermaid
  flowchart LR
    A[草稿] --> B[待审核与唯一任务]
  ```'''
                document = good.replace(original, expanded, 1)
                self.assertEqual([], check.validate(document, source))
                self.assertEqual([], check.validate(good.replace(original, f'- {field}：未知：缺少接口或源码依据，影响判断；补齐后再复核。', 1), source))
                unit = find(check.parse_tree(skeleton, True), prefix)
                self.assertIsNotNone(unit)
                for line in unit.body:
                    match = check.FIELD.match(line)
                    if match and check.PLACEHOLDER.search(match[2]):
                        missing = re.sub(r'^(?:- )?' + re.escape(match[1]) + r'.*\n', '', good, count=1, flags=re.M)
                        self.assertTrue(good != missing, match[1])
                        self.assertTrue(check.validate(missing, source), match[1])
                self.assertTrue(check.validate(document.replace(expanded, expanded + '\n##### 临时子标题\n额外内容。', 1), source))
                self.assertTrue(check.validate(document.replace(expanded, expanded + '\n| 临时列 | 内容 |\n| --- | --- |\n| A | B |', 1), source))

    def test_skill_body_allows_useful_local_structure_inside_fixed_topics(self):
        source = (ROOT / 'skill-authoring-standard/references/skill-template.md').read_text()
        good = filled(check.template_blocks(source)['document'])
        good = good.replace('## 执行流程\n\n样例1', '''## 执行流程

### 模式选择

| 请求 | 下一步 | 失败出口 |
| --- | --- | --- |
| 仅保存已有成果 | 核对基线后保存 | 基线不明时等待选择 |

### 生成步骤

#### 读取依据

先读取已确认输入，缺失时标明影响。
''')
        self.assertEqual([], check.validate(good, source))
        # Retain the outer contract while allowing an entire topic to use subsections.
        self.assertTrue(check.validate(good.replace('## 职责与边界\n\n样例1\n\n', ''), source))
        self.assertTrue(check.validate(good.replace('## 输入与前置条件', '## 临时替代主题'), source))
        self.assertTrue(check.validate(good.replace('## 输入与前置条件', '## 核心约束'), source))
        self.assertTrue(check.validate(good + '\n## 未声明主题\n正文\n', source))
        reordered = good.replace('## 核心约束', '## 交换主题').replace('## 产出边界与交付', '## 核心约束').replace('## 交换主题', '## 产出边界与交付')
        self.assertTrue(check.validate(reordered, source))
        for broken in (
            good.replace('### 模式选择', '#### 模式选择'),
            good.replace('### 生成步骤', '### 模式选择'),
            good.replace('先读取已确认输入，缺失时标明影响。', ''),
            good.replace('核对基线后保存 | 基线不明时等待选择', '核对基线后保存'),
            good.replace('### 模式选择', '### 模式选择 <!-- flexible-body -->'),
            good.replace('先读取已确认输入，缺失时标明影响。', '{{@未填写}}'),
            good + '\n```bash\n未闭合代码',
        ):
            with self.subTest(broken=broken):
                self.assertTrue(check.validate(broken, source))

    def test_flexible_slots_do_not_relax_undeclared_report_structure(self):
        self.assertTrue(check.validate(GOOD.replace('## 结论与范围', '## 结论与范围\n### 临时子标题\n说明'), CONTRACT))
        self.assertTrue(check.validate(GOOD + '\n### 临时表格\n| 列 | 值 |\n| --- | --- |\n| A | B |\n', CONTRACT))
        self.assertTrue(check.validate(GOOD.replace('- 结论：', '- 临时字段：额外内容\n- 结论：'), CONTRACT))
        self.assertTrue(check.validate(GOOD.replace('| 场景 | 结果 | 证据 |', '| 场景 | 临时列 | 证据 |'), CONTRACT))
        source = '```document-template\n# 名称\n## 自由内容 <!-- flexible-body -->\n{{@内容}}\n```'
        self.assertEqual([], check.check_template(source))
        for body in ('{{@内容}}\n### 固定子节\n{{@说明}}', '- 字段：{{@内容}}',
                     '| 列 | 值 |\n| --- | --- |\n| {{@列}} | {{@值}} |',
                     '{{@内容}}\n~~~bash\necho fixed\n~~~'):
            with self.subTest(body=body):
                self.assertTrue(check.check_template(source.replace('{{@内容}}', body)))

    def test_requirement_goal_absence_cannot_waive_missing_integration_acceptance(self):
        source = (ROOT / 'requirement-doc-authoring/references/requirement-template.md').read_text()
        good = filled(check.template_blocks(source)['document'])
        good = good.replace('- 适用性：样例1\n- 流程与交接：样例1',
                            '- 适用性：存在跨需求流程，必须集成验收。\n- 流程与交接：审批完成后交接执行任务。')
        start, end = good.index('## 3.'), good.index('## 4.')
        lines = good[start:end].splitlines()
        tables = [index for index, _ in check.table_headers(lines)]
        self.assertEqual(2, len(tables))
        target, acceptance = tables
        lines[target + 2] = '条目情况：不适用：本次没有共用性能、安全目标。'
        goal_absent = good[:start] + '\n'.join(lines) + '\n\n' + good[end:]
        self.assertEqual([], check.validate(goal_absent, source))
        # This is the reviewed failure: only the goal table has an absence reason.
        missing = lines[:acceptance + 2] + lines[acceptance + 3:]
        errors = check.validate(good[:start] + '\n'.join(missing) + '\n\n' + good[end:], source)
        self.assertTrue(errors)
        self.assertTrue(any('验收标识 / 关联差异' in error for error in errors))
        lines[acceptance + 2] = '条目情况：不适用：独立场景没有跨需求流程或集成验收。'
        both_absent = good[:start] + '\n'.join(lines) + '\n\n' + good[end:]
        both_absent = both_absent.replace('存在跨需求流程，必须集成验收。', '不涉及跨需求流程或集成验收。')
        self.assertEqual([], check.validate(both_absent, source))

    def test_empty_tables_require_their_own_immediately_following_reason(self):
        source = '''```document-template
# 隔离空表样例
| 目标 | 依据 |
| --- | --- |
| {{@目标}} | {{@实际依据}} |

| 验收 | 条件 |
| --- | --- |
| {{@验收}} | {{@条件}} |
```'''
        first = '# 隔离空表样例\n| 目标 | 依据 |\n| --- | --- |\n'
        second = '\n| 验收 | 条件 |\n| --- | --- |\n'
        reason_a = '条目情况：不适用：隔离场景没有目标条目。\n'
        reason_b = '条目情况：无：已核对隔离场景，没有验收对象。\n'
        self.assertEqual([], check.validate(first + reason_a + second + reason_b, source))
        self.assertEqual([], check.validate(first + '\n' + reason_a + second + '| A1 | 可观察结果 |\n', source))
        for bad in [first + reason_a + second, first + second + reason_b,
                    first + reason_a + second + '其他事项说明。\n' + reason_b,
                    reason_a + first + second + reason_b,
                    first + '- 适用性：不适用：另一个对象的判断。\n' + second + reason_b,
                    first + '> ' + reason_a + second + reason_b,
                    first + '```text\n无关代码内容\n```\n' + reason_a + second + reason_b]:
            with self.subTest(document=bad):
                self.assertTrue(check.validate(bad, source))

    def test_table_absence_does_not_omit_a_separate_repeated_unit(self):
        source = '''```document-template
# 隔离空集合样例
| 数据 | 依据 |
| --- | --- |
| {{@实际数据}} | {{@来源}} |

## 对象：{{@名称}} <!-- repeat -->
- 证据：{{@实际证据}}
```'''
        document = '# 隔离空集合样例\n| 数据 | 依据 |\n| --- | --- |\n条目情况：无：仅说明该表没有记录。\n'
        self.assertTrue(check.validate(document, source))
        standalone = document.replace('# 隔离空集合样例\n', '# 隔离空集合样例\n条目情况：无：已核对，没有额外对象。\n\n')
        self.assertEqual([], check.validate(standalone, source))

    def test_fixed_table_dimensions_cannot_be_removed_duplicated_or_reordered(self):
        source = (ROOT / 'project-handover-analysis/assets/project-handover-report-template.md').read_text()
        good = filled(check.template_blocks(source)['document'])
        self.assertEqual([], check.validate(good, source))
        lines = good.splitlines()
        start = next(i for i, line in enumerate(lines) if line.startswith('| 维度 |')) + 2
        rows = lines[start:start + 8]
        self.assertEqual(8, len(rows))
        variants = [rows[:1], rows + rows[:1], list(reversed(rows)),
                    rows + [rows[0].replace('源码', '额外维度')],
                    ['条目情况：不适用：固定维度不能因此省略。']]
        variants.extend(rows[:i] + rows[i + 1:] for i in range(len(rows)))
        for replacement in variants:
            with self.subTest(rows=replacement):
                bad = '\n'.join(lines[:start] + replacement + lines[start + 8:])
                self.assertTrue(check.validate(bad, source))

    def test_fixed_and_variable_table_rows_follow_the_authoritative_patterns(self):
        source = '''```document-template
# 隔离表格样例
| 标识 | 内容 |
| --- | --- |
| 开端 | 固定内容 |
| 项{{@编号}} | {{@实际内容}} |
| 末尾 | {{@实际结果}} |
```'''
        first = '# 隔离表格样例\n| 标识 | 内容 |\n| --- | --- |\n| 开端 | 固定内容 |\n'
        last = '| 末尾 | 未执行：隔离格式样例 |\n'
        for middle in ['', '| 项1 | 一项 |\n', '| 项1 | 一项 |\n| 项2 | 二项 |\n']:
            self.assertEqual([], check.validate(first + middle + last, source))
        for bad in [first.replace('固定内容', '被改写') + last,
                    first + '| 任意身份 | 越过原型 |\n' + last,
                    first + last + '| 项1 | 错误位置 |\n', first + first.splitlines()[-1] + '\n' + last]:
            self.assertTrue(check.validate(bad, source))
        duplicate = source.replace('| 末尾 | {{@实际结果}} |', '| 开端 | {{@实际结果}} |')
        self.assertTrue(check.check_template(duplicate))
        header_only = '```document-template\n# 自由数据表\n| 标识 | 内容 |\n| --- | --- |\n```'
        self.assertEqual([], check.validate('# 自由数据表\n| 标识 | 内容 |\n| --- | --- |\n| 真实对象 | 非空记录 |\n', header_only))

    def test_indented_template_wrappers_are_rejected_but_declared_sources_are_preserved(self):
        source = '````document-template\n# 隔离样例\n\n## 正文\n{{@实际正文}}\n````'
        good = '# 隔离样例\n\n## 正文\n仅验证格式，不作为实际项目证据。\n'
        self.assertEqual([], check.validate(good, source))
        for indent in range(4):
            for fence in ['```', '~~~~']:
                with self.subTest(indent=indent, fence=fence):
                    wrapper = ' ' * indent + fence + 'document-template named\n包装泄漏\n' + ' ' * indent + fence + '\n'
                    self.assertTrue(check.validate(good + wrapper, source))
                    nested = good + '`````text\n' + wrapper + '`````\n'
                    self.assertTrue(check.validate(nested, source))
                    literal = '````document-template\n# 隔离样例\n\n## 正文\n```text verbatim\n{{@用户原文}}\n```\n````'
                    document = '# 隔离样例\n\n## 正文\n`````text\n' + wrapper + '`````\n'
                    self.assertEqual([], check.validate(document, literal))

    def test_business_state_machines_repeat_as_complete_object_units(self):
        source = (ROOT / 'business-closed-loop-analysis/references/output-contract.md').read_text()
        good = filled(check.template_blocks(source)['document'])
        start, end = good.index('### 状态机：'), good.index('## 三、')
        unit = good[start:end]
        first = unit.replace('### 状态机：样例1', '### 状态机：审批单')
        second = unit.replace('### 状态机：样例1', '### 状态机：执行任务')
        two = good[:start] + first + second + good[end:]
        self.assertEqual([], check.validate(two, source))
        absent = good[:start] + '条目情况：不适用：隔离查询场景不维护对象状态。\n\n' + good[end:]
        self.assertEqual([], check.validate(absent, source))
        self.assertTrue(check.validate(good[:start] + good[end:], source))
        unknown = good.replace('- 状态语义与联动：样例1', '- 状态语义与联动：未知：缺少状态来源，无法确认终态；取得源码后补证。')
        self.assertEqual([], check.validate(unknown, source))
        for bad in [good[:start] + first + first + good[end:],
                    two.replace('- 状态语义与联动：样例1\n', '', 1),
                    two.replace('| 当前状态 |', '| 自定义状态 |', 1)]:
            self.assertTrue(check.validate(bad, source))
        # The former output put a second bare state table in the parent section.
        table = unit[unit.index('| 当前状态 |'):]
        self.assertTrue(check.validate(good[:start] + table + table + good[end:], source))

    def test_requirement_goal_tables_cover_local_shared_absent_and_unknown_targets(self):
        source = (ROOT / 'requirement-doc-authoring/references/requirement-template.md').read_text()
        good = filled(check.template_blocks(source)['document'])
        self.assertEqual([], check.validate(good, source))
        header = '| 目标标识 / 关联需求 |'
        lines = good.splitlines()
        starts = [i for i, line in enumerate(lines) if line.startswith(header)]
        self.assertEqual(2, len(starts))
        more = lines[:]
        for index in reversed(starts):
            more.insert(index + 3, '| 目标2 / R1、R2 | 安全 / 隔离样例入口 | 禁止越权读取 | 以角色范围为依据 | A2 |')
        self.assertEqual([], check.validate('\n'.join(more), source))
        for index in starts:
            missing_table = '\n'.join(lines[:index] + lines[index + 3:])
            self.assertTrue(check.validate(missing_table, source))
        absent = lines[:]
        unknown = lines[:]
        for index in reversed(starts):
            absent[index + 2] = '条目情况：不适用：已核对隔离样例，没有该层级的实质目标。'
            unknown[index + 2] = '| 待定目标 / R1 | 性能 / 查询 | 待确认：响应目标未知 | 缺少负载基线，影响阈值制定；补测后确认 | A1待补充 |'
        self.assertEqual([], check.validate('\n'.join(absent), source))
        self.assertEqual([], check.validate('\n'.join(unknown), source))
        no_reason = [line for i, line in enumerate(lines) if i not in {n + 2 for n in starts}]
        self.assertTrue(check.validate('\n'.join(no_reason), source))

    def test_duplicate_template_and_document_headings_are_rejected(self):
        duplicate = '```document-template\n# 报告\n\n## 结论\n第一项。\n\n## 结论\n第二项。\n```'
        self.assertTrue(check.check_template(duplicate))
        self.assertTrue(check.validate('# 报告\n\n## 结论\n第一项。\n\n## 结论\n第二项。\n', duplicate))
        dynamic = '```document-template\n# 报告\n\n## {{@甲}}\n内容。\n\n## {{@乙}}\n内容。\n```'
        self.assertTrue(check.check_template(dynamic))
        separate = '```document-template\n# 报告\n\n## 甲\n### 结论\n内容。\n\n## 乙\n### 结论\n内容。\n```'
        self.assertEqual([], check.validate(filled(check.template_blocks(separate)['document']), separate))

    def test_code_slots_require_content_and_reject_reserved_placeholders(self):
        source = '````document-template\n# 命令记录\n\n## 内容\n- 范围：{{@对象}}\n```sh\n{{@待填命令}}\n```\n````'
        good = '# 命令记录\n\n## 内容\n- 范围：隔离样例。\n```sh\n# TODO: legitimate source comment\necho "{id}"\n```\n'
        self.assertEqual([], check.validate(good, source))
        for command in ['{{@待填命令}}', '{{@未闭合', '', '<!-- repeat -->']:
            with self.subTest(command=command):
                bad = good.replace('# TODO: legitimate source comment\necho "{id}"', command)
                self.assertTrue(check.validate(bad, source))
        missing = good[:good.index('```sh')]
        self.assertTrue(check.validate(missing, source))

    def test_verbatim_scope_comes_from_the_template_and_retains_real_source(self):
        source = '````document-template\n# 原文记录\n- 来源：{{@实际来源}}\n\n```text verbatim\n{{@用户原文}}\n```\n````'
        raw = '原文中的 {{@占位示例}}\n<!-- repeat -->\n```document-template\n# 示例\n```\nTODO: 原始待办'
        good = '# 原文记录\n- 来源：隔离样例原文。\n\n````text\n' + raw + '\n````\n'
        self.assertEqual([], check.validate(good, source))
        for content in ['{{@用户原文}}', '']:
            bad = '# 原文记录\n- 来源：隔离样例。\n\n```text\n' + content + '\n```\n'
            self.assertTrue(check.validate(bad, source))
        self.assertTrue(check.validate(good.replace('````text\n', '````text verbatim\n'), source))
        self.assertTrue(check.validate(good + '\n```text\n额外块\n```\n', source))
        normal = source.replace('text verbatim', 'text')
        self.assertTrue(check.validate(good, normal))
        self.assertTrue(check.validate(good.replace('````text\n', '````text verbatim\n'), normal))

    def test_plan_consumes_reuse_analysis_in_its_own_fields(self):
        source = (ROOT / 'development-workflow/references/output-template.md').read_text()
        good = filled(check.template_blocks(source)['document'])
        good = good.replace('- 实施方案：样例1', '- 实施方案：复用已有筛选入口；隔离样例定位为 existing/filter.ts。\n  候选筛选状态：已比较旧、新页面的共同变化点；保留各自的数据请求。')
        good = good.replace('- 影响与保持项：样例1', '- 影响与保持项：旧、新消费者共同接入，迁移步骤纳入当前任务；保留提交行为。')
        good = good.replace('- 完成条件：样例1', '- 完成条件：验证两处消费者及项目要求的登记维护。')
        self.assertEqual([], check.validate(good, source))
        snippet = '### 共用筛选状态\n- 现状与依据：已比较两处。\n- 判断与边界：复用已有入口。\n- 消费方与处理：迁移两处。\n- 验证与维护：安排回归。\n\n'
        self.assertTrue(check.validate(good.replace('## 3. 验收与交付', snippet + '## 3. 验收与交付'), source))

    def test_operation_workflow_command_rule_fragments_resolve_to_real_sections(self):
        skill = ROOT / 'operation-workflow/SKILL.md'
        references = re.findall(r'\]\((references/command-policy\.md)#([^)]*)\)', skill.read_text())
        self.assertTrue(references)
        for relative, fragment in references:
            tree = check.parse_tree((skill.parent / relative).read_text())
            nodes, headings = [tree], set()
            while nodes:
                node = nodes.pop()
                headings.add(node.title)
                nodes.extend(node.children)
            # These Chinese fragments directly name headings; use the shared
            # Markdown parser so code-fence content cannot satisfy the route.
            self.assertIn(fragment, headings, relative + '#' + fragment)

    def test_operation_review_and_evidence_are_separate_contracts(self):
        source = (ROOT / 'operation-workflow/references/output-templates.md').read_text()
        blocks = check.template_blocks(source)
        self.assertEqual({'access', 'index', 'unit', 'record', 'execution'}, set(blocks))
        review = filled(blocks['record'])
        for field in ['- 待办与决定：样例1\n', '- 异常与未验证：样例1\n', '- 人工决定：样例1\n',
                      '- 影响：样例1\n', '- 备份与回退：样例1\n', '- 验证标准：样例1\n',
                      '- 结果与证据：样例1\n']:
            self.assertTrue(check.validate(review.replace(field, '', 1), source, 'record'))
        # Raw input can contain template-like text without changing the contract.
        skeleton = blocks['execution'].replace('```text verbatim', '`````text')
        skeleton = re.sub(r'^```$', '`````', skeleton, flags=re.M)
        raw = '批准S01/v1限定检查\n{{@原始示例}}\n```document-template\n# 原文\n```\n<!-- repeat -->'
        document = check.PLACEHOLDER.sub(
            lambda m: raw if '实际需求或决定原文' in m[0] else '隔离样例1', skeleton)
        document = re.sub(r' <!-- repeat(?:-required)? -->', '', document)
        self.assertEqual([], check.validate(document, source, 'execution'))
        self.assertIn(raw, document)
        for field in ['- 来源与范围：隔离样例1\n', '- 方案与授权：隔离样例1\n',
                      '- 执行结果：隔离样例1\n', '- 关键证据：隔离样例1\n']:
            self.assertTrue(check.validate(document.replace(field, '', 1), source, 'execution'))

    def test_operation_versions_and_units_repeat_without_detaching_decisions(self):
        # Structural repetition only; this does not prove navigation or source semantics.
        source = (ROOT / 'operation-workflow/references/output-templates.md').read_text()
        for block, marker, finish, fields in [
            ('record', '### 方案：', '## 3. 验收与归档', ('前提与范围', '变更与步骤')),
            ('execution', '### 操作：', '## 3. 需求与决定来源', ('命令与参数', '执行结果')),
        ]:
            with self.subTest(block=block):
                document = filled(check.template_blocks(source)[block])
                begin, end = document.index(marker), document.index(finish)
                unit = document[begin:end]
                first = unit.replace(marker + '样例1', marker + 'S01/v1', 1)
                second = unit.replace(marker + '样例1', marker + 'S01/v2', 1)
                combined = document[:begin] + first + second + document[end:]
                self.assertEqual([], check.validate(combined, source, block))
                duplicated = document[:begin] + first + first + document[end:]
                self.assertTrue(check.validate(duplicated, source, block))
                a, b = fields
                reordered = combined.replace(f'- {a}：样例1\n- {b}：样例1',
                                             f'- {b}：样例1\n- {a}：样例1', 1)
                self.assertTrue(check.validate(reordered, source, block))
                required = '人工决定' if block == 'record' else '方案与授权'
                detached = document[:begin] + first + second.replace(f'- {required}：样例1\n', '', 1) + document[end:]
                self.assertTrue(check.validate(detached, source, block))

    def test_operation_review_tables_preserve_navigation_and_separate_archive_states(self):
        source = (ROOT / 'operation-workflow/references/output-templates.md').read_text()
        blocks = check.template_blocks(source)
        for block, header in [
            ('record', '| 方案版本与详情 | 整体批准 | 执行与验证 | 操作入口 |'),
            ('record', '| 事项 | 当前状态与范围 | 来源或证据 |'),
            ('execution', '| 核对项 | 预期 | 实际与判定 | 证据入口 |'),
        ]:
            with self.subTest(block=block, header=header):
                document = filled(blocks[block])
                self.assertEqual([], check.validate(document, source, block))
                self.assertIn(header, document)
                begin = document.index(header)
                end = document.find('\n\n', begin)
                if end == -1:
                    end = len(document)
                self.assertTrue(check.validate(document[:begin] + document[end:], source, block))
                self.assertTrue(check.validate(document.replace(header, header.replace(' |', '', 1)), source, block))
        review = filled(blocks['record'])
        for item in ['结果确认', '归档批准', '索引检查', '本地提交', '推送']:
            with self.subTest(item=item):
                row = f'| {item} | 样例1 | 样例1 |\n'
                self.assertIn(row, review)
                self.assertTrue(check.validate(review.replace(row, ''), source, 'record'))
        detail = filled(blocks['execution'])
        self.assertTrue(check.validate(detail.replace('| 样例1 | 样例1 | 样例1 | 样例1 |',
                                                     '| 样例1 | 样例1 | | 样例1 |'), source, 'execution'))

    def test_operation_without_execution_keeps_unknown_and_rejected_states(self):
        source = (ROOT / 'operation-workflow/references/output-templates.md').read_text()
        blocks = check.template_blocks(source)
        evidence = filled(blocks['execution'])
        begin = evidence.index('### 操作：')
        end = evidence.index('## 3. 需求与决定来源')
        absence = '条目情况：无：未执行，等待明确批准或补齐权限。\n\n'
        for state in ['待批准', '拒绝本版方案', '未知：权限不可用']:
            with self.subTest(state=state):
                review = filled(blocks['record']).replace('- 人工决定：样例1', '- 人工决定：' + state)
                review = review.replace('- 结果与证据：样例1', '- 结果与证据：未执行；缺批准或必要权限。')
                pending = evidence[:begin] + absence + evidence[end:]
                pending = pending.replace('- 策略依据：样例1', '- 策略依据：命令allow，仅免逐条询问；整体变更方案仍按人工决定字段判断。')
                pending = pending.replace('```text\n样例1\n```', '```text\n' + state + '\n```', 1)
                self.assertEqual([], check.validate(review, source, 'record'))
                self.assertEqual([], check.validate(pending, source, 'execution'))
                self.assertTrue(check.validate(pending.replace(absence, ''), source, 'execution'))

    def test_operation_plan_does_not_require_a_precomputed_command_list(self):
        source = (ROOT / 'operation-workflow/references/output-templates.md').read_text()
        blocks = check.template_blocks(source)
        review = filled(blocks['record'])
        detail = filled(blocks['execution'])
        fields = {
            '用途与归属': '隔离试填的人工审阅入口，明细见[O01](execution.md#操作o01)；不代表真实服务器任务。',
            '目标与验收': '测试服务demo_portal从1副本扩至2副本；期望与运行均为2，业务健康另行检查。',
            '当前结论': '待执行；目前没有服务器变更。',
            '异常与未验证': '运行副本数及业务均未验证，尚不能判断目标达成。',
            '待办与决定': '请决定是否批准[S01/v1](#方案s01v1)；批准后方可执行O01。',
            '前提与范围': '仅测试服务demo_portal，样例原副本数1；不改镜像和持久化数据。',
            '变更与步骤': '副本数1→2；先核对原值，再按[O01](execution.md#操作o01)更新并检查运行数。',
            '影响': '新增一个服务副本，增加资源占用；不修改其他服务。',
            '备份与回退': '保留原副本数1；无数据文件变更。验证失败停止后续动作，仅在身份和基线符合时按O01所列恢复目标回退至1。',
            '验证标准': 'O01需核对运行数2/2；业务健康未纳入本轮，不据此宣布业务验收。',
            '人工决定': '待批准；只有[R01](execution.md#来源r01)需求，尚无批准来源。',
            '结果与证据': '未执行，等待S01/v1整体批准；[O01](execution.md#操作o01)仅记录待执行范围和预期。',
            '验收与剩余问题': '副本数未验证，业务未检查；先等待方案决定。',
            '文档与提交范围': '仅本试填的record.md与execution.md；没有实际暂存或提交，不纳入真实项目。',
        }
        for field, value in fields.items():
            review = review.replace(f'- {field}：样例1', f'- {field}：{value}')
        review = review.replace('### 方案：样例1', '### 方案：S01/v1')
        review = review.replace('| 样例1 | 样例1 | 样例1 | 样例1 |',
                                '| [S01/v1](#方案s01v1) | 待批准 | 未执行 | [O01](execution.md#操作o01) |')
        for item in ['结果确认', '归档批准', '索引检查', '本地提交', '推送']:
            review = review.replace(f'| {item} | 样例1 | 样例1 |',
                                    f'| {item} | 未执行：方案尚待批准 | 无：没有实际决定或执行证据 |')
        fields = {
            '用途与归属': '隔离试填明细，人工决定见[S01/v1](record.md#方案s01v1)，不连接真实服务器。',
            '目标与身份': '模拟测试服务demo_portal；身份和提权仅为候选，执行前必须核实。',
            '连接与核验': '未连接；本测试只验证文档结构，不产生连接授权。',
            '策略依据': '模拟策略将候选命令判为allow，仅免逐条询问，整体变更仍待批准。',
            '方案与授权': '[S01/v1](record.md#方案s01v1)待批准；[R01](#来源r01)仅为需求，不能执行。',
            '命令与参数': '尚未执行，无实际命令；具体命令在执行当次生成并判定权限，执行后汇总。',
            '执行结果': '未执行：整体方案尚待批准，无执行时点和退出码。',
            '关键证据': '无：未执行，没有运行输出。',
            '异常与后续': '批准及身份核验完成前保持未执行，不因命令allow直接变更。',
            '来源与范围': '隔离模拟用户需求R01，仅提出扩容目标，不批准方案。',
        }
        for field, value in fields.items():
            detail = detail.replace(f'- {field}：样例1', f'- {field}：{value}')
        detail = detail.replace('### 操作：样例1', '### 操作：O01').replace('### 来源：样例1', '### 来源：R01')
        detail = detail.replace('| 样例1 | 样例1 | 样例1 | 样例1 |',
                                '| 副本数 | 更新后2/2，回退后1/1 | 未执行，无法判定 | 无：待整体批准后取证 |')
        detail = detail.replace('```text\n样例1\n```', '```text\n隔离模拟需求：把测试服务从1副本扩至2副本。\n```')
        for block, document in [('record', review), ('execution', detail)]:
            with self.subTest(block=block):
                self.assertNotIn('样例1', document)
                self.assertNotIn('docker service update', document)
                self.assertEqual([], check.validate(document, source, block))

    def test_operation_failure_and_recovery_fit_existing_evidence_slots(self):
        source = (ROOT / 'operation-workflow/references/output-templates.md').read_text()
        blocks = check.template_blocks(source)
        # Isolated syntax examples: no server commands are executed by this test.
        for result, evidence, recovery, mount, health, restored in [
            ('样例时点查询退出0；只读，无服务器变更。', '挂载读取返回RW=false；业务未检查。', '无变更，无需回退。',
             '通过：RW=false', '未验证：本次未作健康检查', '不适用：只读无变更'),
            ('样例时点实施退出0，随后验证退出1；部分完成。', '挂载RW=false；健康检查退出1。', '已停止后续动作；回退未执行，当前状态待核实。',
             '通过：RW=false', '失败：健康检查退出1', '未知：回退未执行'),
            ('样例时点实施退出1，获批回退退出0。', '回读恢复原配置；业务未验证。', '配置已恢复；业务验收仍未通过。',
             '未知：中途失败，未完成挂载核验', '未验证：未作业务检查', '通过：配置回读与原基线一致'),
        ]:
            with self.subTest(result=result):
                review = filled(blocks['record']).replace('- 当前结论：样例1', '- 当前结论：' + result)
                review = review.replace('- 结果与证据：样例1', '- 结果与证据：' + recovery + ' 见execution.md对应操作。')
                detail = filled(blocks['execution'])
                detail = detail.replace('- 命令与参数：样例1', '- 命令与参数：隔离语法样例，不实际执行。\n\n  ```sh\n  docker service inspect demo_portal\n  ```')
                detail = detail.replace('- 执行结果：样例1', '- 执行结果：' + result)
                detail = detail.replace('- 关键证据：样例1', '- 关键证据：' + evidence)
                detail = detail.replace('- 异常与后续：样例1', '- 异常与后续：' + recovery)
                detail = detail.replace('| 样例1 | 样例1 | 样例1 | 样例1 |',
                                        '| 挂载 | RW=false | ' + mount + ' | 见本操作关键证据 |\n'
                                        '| 健康 | 健康检查通过 | ' + health + ' | 见本操作关键证据 |\n'
                                        '| 恢复 | 回到变更前基线 | ' + restored + ' | 见本操作关键证据 |')
                self.assertEqual([], check.validate(review, source, 'record'))
                self.assertEqual([], check.validate(detail, source, 'execution'))
                self.assertTrue(check.validate(detail.replace('- 异常与后续：' + recovery, ''), source, 'execution'))

    def test_formal_code_review_reports_have_an_authoritative_contract(self):
        source = (ROOT / 'code-review/references/report-template.md').read_text()
        good = filled(check.template_blocks(source)['document'])
        self.assertEqual([], check.validate(good, source))
        self.assertTrue(check.validate(good.replace('- 用途与归属：样例1\n', ''), source))
        no_issues = good[:good.index('### Q')] + '条目情况：无：已核对本次隔离样例的指定范围。\n\n' + good[good.index('## 3.') :]
        self.assertEqual([], check.validate(no_issues, source))

    def test_valid_report_and_multiple_entries(self):
        self.assertEqual([], check.validate(GOOD, CONTRACT))
        more = GOOD.replace('## 验证覆盖', '### Q2：历史数据范围\n- 证据：另一个模拟入口。\n- 影响：仅影响历史数据。\n- 验证：未验证：历史数据不可访问。\n\n## 验证覆盖')
        self.assertEqual([], check.validate(more, CONTRACT))

    def test_absence_and_unknown_are_preserved(self):
        start, end = GOOD.index('### Q1'), GOOD.index('## 验证覆盖')
        no_issues = GOOD[:start] + '条目情况：无：已检查隔离样例的正常链路。\n\n' + GOOD[end:]
        self.assertEqual([], check.validate(no_issues, CONTRACT))
        self.assertTrue(check.validate(GOOD[:start] + GOOD[end:], CONTRACT))
        unknown = GOOD.replace('模拟 fixture 的入口未调用授权检查。', '无访问权限：源码不可读；无法判断入口鉴权，需补源码后复核。')
        self.assertEqual([], check.validate(unknown, CONTRACT))
        self.assertTrue(check.validate(unknown.replace('- 证据：无访问权限：源码不可读；无法判断入口鉴权，需补源码后复核。\n', ''), CONTRACT))

    def test_fixed_structure_rejects_drift(self):
        mutations = {
            'renamed': GOOD.replace('## 结论与范围', '## 总体情况'),
            'missing-field': GOOD.replace('- 影响：未获授权的用户能够导出本应不可见的数据。\n', ''),
            'field-order': GOOD.replace('- 证据：模拟 fixture 的入口未调用授权检查。\n- 影响：未获授权的用户能够导出本应不可见的数据。', '- 影响：未获授权的用户能够导出本应不可见的数据。\n- 证据：模拟 fixture 的入口未调用授权检查。'),
            'new-field': GOOD.replace('- 影响：', '- 自由发挥：额外字段。\n- 影响：'),
            'empty-field': GOOD.replace('- 验证：待验证：需补无权限调用用例，当前仅为格式样例。', '- 验证：'),
            'changed-field-style': GOOD.replace('- 证据：模拟 fixture', '证据：模拟 fixture'),
            'new-section': GOOD + '\n## 自行新增建议\n内容。\n',
            'wrong-level': GOOD.replace('### Q1', '#### Q1'),
            'duplicate-entry': GOOD.replace('## 验证覆盖', '### Q1：另一名称\n- 证据：来源。\n- 影响：影响。\n- 验证：未验证。\n\n## 验证覆盖'),
            'wrong-columns': GOOD.replace('| 场景 | 结果 | 证据 |', '| 场景 | 结果 |'),
            'empty-cell': GOOD.replace('| 无权限调用 | 未执行；需要隔离环境 |', '| 无权限调用 | |'),
            'placeholder': GOOD.replace('未获授权的用户能够导出本应不可见的数据。', '{{@影响待填}}'),
            'leaked-marker': GOOD.replace('### Q1：无权限导出', '### Q1：无权限导出 <!-- repeat -->'),
            'headings-only': '# 标题\n## 结论与范围\n## 问题与处理\n## 验证覆盖\n',
        }
        for reason, text in mutations.items():
            with self.subTest(reason=reason):
                self.assertTrue(check.validate(text, CONTRACT))

    def test_code_headings_do_not_change_document_structure(self):
        outside = GOOD.replace('## 验证覆盖', '```python\n# implementation note\n## not a document heading\n```\n\n## 验证覆盖')
        self.assertTrue(check.validate(outside, CONTRACT))
        # Code is valid in the declared field, and its headings stay literal.
        text = GOOD.replace('- 证据：模拟 fixture 的入口未调用授权检查。',
                            '- 证据：模拟 fixture 的入口未调用授权检查。\n  ```python\n  # implementation note\n  ## not a document heading\n  ```')
        self.assertEqual([], check.validate(text, CONTRACT))

    def test_unclosed_code_fences_cannot_hide_trailing_content(self):
        broken = GOOD + '\n```python\nprint(1)\n## 意外章节\n{{@未填写}}\n'
        self.assertTrue(check.validate(broken, CONTRACT))
        broken_contract = '````document-template\n# 固定文档\n\n## 说明\n```text\n原文\n````'
        self.assertTrue(check.check_template(broken_contract))
        outside = GOOD + '\n````text\n```python\n# 原始内容\n```\n````\n'
        self.assertTrue(check.validate(outside, CONTRACT))
        nested = GOOD.replace('- 证据：模拟 fixture 的入口未调用授权检查。',
                              '- 证据：模拟 fixture 的入口未调用授权检查。\n  ````text\n  ```python\n  # 原始内容\n  ```\n  ````')
        self.assertEqual([], check.validate(nested, CONTRACT))

    def test_design_fields_cannot_be_dropped_as_writing_instructions(self):
        source = (ROOT / 'design-spec-authoring/references/design-md-template.md').read_text()
        good = filled(check.template_blocks(source)['document'])
        self.assertEqual([], check.validate(good, source))
        for label in ['数据区', '列与长内容', '操作区', '承载容器', '桌面降级',
                      '适用任务与边界', '接入与默认呈现', '使用与禁用', '交互承接',
                      '布局与视口差异', '依据与状态']:
            with self.subTest(field=label):
                missing = re.sub(r'^- ' + re.escape(label) + r'：.*\n', '', good, flags=re.M)
                self.assertTrue(check.validate(missing, source))

    def test_handover_preparation_steps_keep_their_labels(self):
        source = (ROOT / 'project-handover-analysis/assets/project-handover-report-template.md').read_text()
        good = filled(check.template_blocks(source)['document'])
        self.assertEqual([], check.validate(good, source))
        missing = re.sub(r'^1\. .*\n', '', good, count=1, flags=re.M)
        self.assertTrue(check.validate(missing, source))

    def test_business_permission_matrix_has_a_fixed_home(self):
        source = (ROOT / 'business-closed-loop-analysis/references/output-contract.md').read_text()
        good = filled(check.template_blocks(source)['document'])
        self.assertEqual([], check.validate(good, source))
        header = '| 角色/身份 | 入口/资源 | 允许操作 | 数据范围 | 判定位置 | 业务表约束 | 缺口 |'
        missing = re.sub(re.escape(header) + r'\n\|[^\n]+\n(?:\|[^\n]+\n)*', '', good)
        self.assertTrue(check.validate(missing, source))

    def test_memory_report_retains_date_status_and_generation_time(self):
        source = (ROOT / 'backend-memory-risk-analysis/references/output-template.md').read_text()
        good = filled(check.template_blocks(source)['document'])
        self.assertEqual([], check.validate(good, source))
        for label in ['报告日期', '生成时点', '报告状态']:
            with self.subTest(field=label):
                missing = re.sub(r'^- ' + label + r'：.*\n', '', good, flags=re.M)
                self.assertTrue(check.validate(missing, source))

    def test_business_braces_are_not_template_placeholders(self):
        for value in ['`GET /records/{id}`', 'GET /records/{id}', '`{colors.primary}`',
                      '{colors.primary}', '{"status": "ok"}', '{{user.name}}', '{具体来源}']:
            with self.subTest(value=value):
                text = GOOD.replace('模拟 fixture 的入口未调用授权检查。', value)
                self.assertEqual([], check.validate(text, CONTRACT))
                self.assertEqual([], check.validate_existing(text))

    def test_explicit_unfilled_markers_still_fail(self):
        for marker in ['{{@具体来源}}', '{{@影响待填}}', '{{@尚未闭合']:
            with self.subTest(marker=marker):
                text = GOOD.replace('模拟 fixture 的入口未调用授权检查。', marker)
                self.assertTrue(check.validate(text, CONTRACT))
                self.assertTrue(check.validate_existing(text))

    def test_plain_and_bullet_fields_both_reject_unknown_names(self):
        for prefix in ['', '- ', '* ', '**']:
            with self.subTest(prefix=prefix):
                text = GOOD.replace('- 影响：', prefix + '临时自定义字段：未声明字段。\n- 影响：')
                self.assertTrue(check.validate(text, CONTRACT))
        plain_contract = CONTRACT.replace('- 证据：', '证据：').replace('- 影响：', '影响：').replace('- 验证：', '验证：')
        plain_report = GOOD.replace('- 证据：', '证据：').replace('- 影响：', '影响：').replace('- 验证：', '验证：')
        self.assertEqual([], check.validate(plain_report, plain_contract))
        self.assertTrue(check.validate(plain_report.replace('影响：', '临时自定义字段：未声明字段。\n影响：'), plain_contract))
        self.assertTrue(check.validate(GOOD.replace('- 证据：', '  - 证据：'), CONTRACT))

    def test_continuation_quotes_tables_and_free_text_keep_their_meaning(self):
        text = GOOD.replace('- 证据：模拟 fixture 的入口未调用授权检查。',
                            '- 证据：模拟 fixture 的入口未调用授权检查。\n  补充说明：这是字段内的解释。\n  - 影响：这是嵌套说明，不是另一固定字段。\n> 原始记录：静态线索。')
        text = text.replace('| 无权限调用 |', '| 场景说明：无权限调用 |')
        self.assertEqual([], check.validate(text, CONTRACT))
        free_contract = '```document-template\n# 说明\n\n## 机制\n{{@完整机制说明}}\n```'
        self.assertEqual([], check.validate('# 说明\n\n## 机制\n背景：这里是自由文本槽位。\n', free_contract))

    def test_audit_reports_require_priority_at_the_declared_position(self):
        for relative in ['frontend-ux-audit/references/output-template.md',
                         'design-compliance-audit/references/report-template.md']:
            with self.subTest(template=relative):
                source = (ROOT / relative).read_text()
                good = filled(check.template_blocks(source)['document'])
                good = re.sub(r'^优先级：.*$', '优先级：P1；依据为该技能的定级规则。', good, flags=re.M)
                self.assertEqual([], check.validate(good, source))
                missing = re.sub(r'^优先级：.*\n', '', good, flags=re.M)
                self.assertTrue(check.validate(missing, source))
                empty = re.sub(r'^优先级：.*$', '优先级：', good, flags=re.M)
                self.assertTrue(check.validate(empty, source))
                moved = re.sub(r'^优先级：.*\n', '', good, flags=re.M)
                moved = re.sub(r'^(类别：.*)$', '优先级：P1\n\\1', moved, flags=re.M)
                self.assertTrue(check.validate(moved, source))

    def test_multiple_named_entries_and_escaped_table_values(self):
        source = CONTRACT.replace('Q{{@序号}}：{{@名称}}', '对象：{{@名称}}')
        first = GOOD.replace('Q1：无权限导出', '对象：导出')
        more = first.replace('## 验证覆盖', '### 对象：历史查询\n- 证据：模拟查询入口。\n- 影响：历史记录可见范围。\n- 验证：待补隔离样例。\n\n## 验证覆盖')
        self.assertEqual([], check.validate(more, source))
        escaped = GOOD.replace('| 无权限调用 |', '| 带有 a\\|b 参数的调用 |')
        self.assertEqual([], check.validate(escaped, CONTRACT))

    def test_absence_in_declared_applicability_slot(self):
        source = CONTRACT.replace('## 问题与处理\n', '## 问题与处理\n- 适用性：{{@条件及依据}}\n')
        start, end = GOOD.index('### Q1'), GOOD.index('## 验证覆盖')
        text = GOOD[:start] + '- 适用性：不适用：隔离场景不包含问题对象。\n\n' + GOOD[end:]
        self.assertEqual([], check.validate(text, source))

    def test_required_repetition_and_template_errors(self):
        required = CONTRACT.replace('<!-- repeat -->', '<!-- repeat-required -->')
        no_items = GOOD[:GOOD.index('### Q1')] + '条目情况：无：尚无对象。\n\n' + GOOD[GOOD.index('## 验证覆盖'):]
        self.assertTrue(check.validate(no_items, required))
        self.assertTrue(check.check_template('```document-template\n# 标题'))
        self.assertTrue(check.check_template('普通示例不是完整模板'))
        self.assertTrue(check.check_template('```document-template\n# 标题\n### 错层\n正文\n```'))
        self.assertTrue(check.check_template(CONTRACT + '\n' + CONTRACT))

    def test_every_installed_template_is_consumable_and_rejects_new_sections(self):
        covered = set()
        for path in sorted(ROOT.glob('*/**/*.md')):
            if any(part.startswith('.') for part in path.relative_to(ROOT).parts):
                continue
            source = path.read_text(encoding='utf-8')
            if not re.search(r'^`{3,}document-template', source, re.M):
                continue
            self.assertEqual([], check.check_template(source), str(path))
            for name, skeleton in check.template_blocks(source).items():
                with self.subTest(path=path.relative_to(ROOT), block=name):
                    text = filled(skeleton)
                    self.assertEqual([], check.validate(text, source, name), '\n'.join(check.validate(text, source, name)))
                    self.assertTrue(check.validate(text + '\n## 无授权新增章节\n额外内容\n', source, name))
                    covered.add((path.relative_to(ROOT).as_posix(), name))
        # Discover every template, but guard real consumers rather than an arbitrary
        # total that would penalize retiring duplicate artifact contracts.
        required_consumers = {
            ('operation-workflow/references/output-templates.md', 'access'),
            ('operation-workflow/references/output-templates.md', 'index'),
            ('operation-workflow/references/output-templates.md', 'unit'),
            ('operation-workflow/references/output-templates.md', 'record'),
            ('operation-workflow/references/output-templates.md', 'execution'),
            ('development-workflow/references/output-template.md', 'document'),
            ('requirement-doc-authoring/references/requirement-template.md', 'document'),
            ('skill-authoring-standard/references/skill-template.md', 'document'),
        }
        self.assertTrue(required_consumers <= covered, required_consumers - covered)

    def test_existing_document_preserves_original_structure(self):
        existing = '# 原文\n\n## 既有安排\n保留原文细节和确认状态。\n'
        self.assertEqual([], check.validate_existing(existing))
        self.assertTrue(check.validate(existing, CONTRACT))

    def test_selected_artifacts_and_claude_thin_entry(self):
        sys.path.insert(0, str(ROOT / 'ai-constraint-doc-authoring/scripts'))
        import validate_ai_constraint_docs as ai
        source = ai.TEMPLATE.read_text()
        blocks = check.template_blocks(source)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            agents = filled(blocks['agents'])
            (root / 'AGENTS.md').write_text(agents)
            self.assertEqual([], ai.validate_repository(root, document='agents'))
            self.assertTrue(ai.validate_repository(root, document='both'))
            claude = filled(blocks['claude']).replace('样例1', 'AGENTS.md')
            (root / 'CLAUDE.md').write_text(claude)
            self.assertEqual([], ai.validate_repository(root))
            (root / 'CLAUDE.md').write_text(claude + '\n```bash\necho unsafe-copy\n```\n')
            self.assertTrue(ai.validate_repository(root, document='claude'))

    def test_cli_fixed_default_and_existing_mode_are_distinct(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'README.md'
            path.write_text('# 项目\n\n## 原有结构\n已有内容。\n')
            cmd = [sys.executable, str(ROOT / 'project-readme-authoring/scripts/validate_readme_structure.py'), str(path)]
            rejected = subprocess.run(cmd, capture_output=True, text=True)
            self.assertNotEqual(0, rejected.returncode)
            kept = subprocess.run(cmd + ['--existing-structure'], capture_output=True, text=True)
            self.assertEqual(0, kept.returncode, kept.stderr)
            self.assertIn('fixed-template conformance not checked', kept.stdout)

    def test_ascii_colon_fields_do_not_take_over_skill_yaml(self):
        source = (ROOT / 'skill-authoring-standard/references/skill-template.md').read_text()
        good = filled(check.template_blocks(source)['document'])
        good = good.replace('description: 样例1', 'description: 样例1\nlicense: MIT')
        self.assertEqual([], check.validate(good, source))
        ascii_contract = CONTRACT.replace('范围：', '范围:').replace('结论：', '结论:')
        report = GOOD.replace('范围：', '范围:').replace('结论：', '结论:')
        self.assertEqual([], check.validate(report, ascii_contract))
        self.assertTrue(check.validate(report.replace('- 结论:', '- 临时字段: 额外内容\n- 结论:'), ascii_contract))
        numbered = CONTRACT.replace('Q{{@序号}}：{{@名称}}', 'Q{{@序号}}: {{@名称}}')
        duplicate = GOOD.replace('Q1：无权限导出', 'Q1: Export').replace('## 验证覆盖',
            '### Q1: Another title\n- 证据：来源。\n- 影响：影响。\n- 验证：未验证。\n\n## 验证覆盖')
        self.assertTrue(check.validate(duplicate, numbered))

    def test_entrypoints_use_explicit_project_contract_without_language_modes(self):
        source = '```document-template\n# {{@项目名称}}\n\n## 项目约定\n- 用途与归属：{{@实际职责及范围}}\n- 操作入口：{{@真实入口或当前缺口}}\n```'
        good = '# 隔离样例\n\n## 项目约定\n- 用途与归属：仅检查该隔离样例的文档格式，不记录真实项目事实。\n- 操作入口：未接入实际项目；需取得真实入口后补充。\n'
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            contract = root / 'output-contract.md'
            document = root / 'document.md'
            contract.write_text(source)
            document.write_text(good)
            for skill, script in [('project-readme-authoring', 'validate_readme_structure'),
                                  ('project-module-architecture-doc-authoring', 'validate_architecture_doc_structure')]:
                with self.subTest(skill=skill):
                    entry = ROOT / skill / 'scripts' / (script + '.py')
                    cmd = [sys.executable, str(entry), str(document)]
                    self.assertNotEqual(0, subprocess.run(cmd, capture_output=True).returncode)
                    result = subprocess.run(cmd + ['--template', str(contract)], capture_output=True, text=True)
                    self.assertEqual(0, result.returncode, result.stderr)
                    help_text = subprocess.run([sys.executable, str(entry), '--help'], capture_output=True, text=True)
                    self.assertNotIn('--language', help_text.stdout)
                    spec = importlib.util.spec_from_file_location(script, entry)
                    module = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(module)
                    self.assertEqual([], module.validate(good, custom_structure=True))
                    with self.assertRaises(TypeError):
                        module.validate(good, '旧位置参数')
            shared = ROOT / 'skill-authoring-standard/scripts/validate_document_template.py'
            result = subprocess.run([sys.executable, str(shared), str(document), '--template', str(contract)], capture_output=True, text=True)
            self.assertEqual(0, result.returncode, result.stderr)
            document.write_text(good.replace('- 用途与归属：仅检查该隔离样例的文档格式，不记录真实项目事实。\n', ''))
            result = subprocess.run([sys.executable, str(shared), str(document), '--template', str(contract)], capture_output=True)
            self.assertNotEqual(0, result.returncode)


if __name__ == '__main__':
    unittest.main()
