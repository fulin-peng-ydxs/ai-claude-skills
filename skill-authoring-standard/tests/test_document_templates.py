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
    out = re.sub(r'^(`{3,}|~{3,})text verbatim$', r'\1text', out, flags=re.M)
    out = check.PLACEHOLDER.sub('样例1', out)
    lines = out.splitlines()
    # Templates may declare a table with header only; add a nonempty test record.
    for index, header in reversed(check.table_headers(lines)):
        if index + 2 >= len(lines) or not lines[index + 2].strip().startswith('|'):
            lines.insert(index + 2, '| ' + ' | '.join(['无：隔离格式样例'] * len(header.split('|'))) + ' |')
    return '\n'.join(lines) + '\n'


class FixedDocumentTests(unittest.TestCase):
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

    def test_operation_record_keeps_all_three_literal_sources(self):
        source = (ROOT / 'operation-workflow/references/output-templates.md').read_text()
        skeleton = check.template_blocks(source)['record']
        skeleton = skeleton.replace('```text verbatim', '`````text')
        skeleton = re.sub(r'^```$', '`````', skeleton, flags=re.M)
        raw = ['用户输入中的 {{@示例}}\n```document-template\n# 示例\n```',
               '批准原文\n<!-- repeat -->\nTODO: 原始待办',
               '汇报原文\n## 内部标题\n{{@尚未完成的示例}}']
        values = iter(['隔离需求来源及哈希', raw[0], '隔离批准来源及哈希', raw[1], '隔离汇报来源及哈希', raw[2]])
        document = check.PLACEHOLDER.sub(lambda _: next(values), skeleton)
        self.assertEqual([], check.validate(document, source, 'record'))
        for text in raw:
            self.assertIn(text, document)
        self.assertNotIn('text verbatim', document)

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
        text = GOOD.replace('## 验证覆盖', '```python\n# implementation note\n## not a document heading\n```\n\n## 验证覆盖')
        self.assertEqual([], check.validate(text, CONTRACT))

    def test_unclosed_code_fences_cannot_hide_trailing_content(self):
        broken = GOOD + '\n```python\nprint(1)\n## 意外章节\n{{@未填写}}\n'
        self.assertTrue(check.validate(broken, CONTRACT))
        broken_contract = '````document-template\n# 固定文档\n\n## 说明\n```text\n原文\n````'
        self.assertTrue(check.check_template(broken_contract))
        nested = GOOD + '\n````text\n```python\n# 原始内容\n```\n````\n'
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
        count = 0
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
                    count += 1
        self.assertGreaterEqual(count, 25)

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
