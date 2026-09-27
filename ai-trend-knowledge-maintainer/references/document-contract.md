# 文档契约

## 必需 frontmatter

```yaml
---
schema_version: 1
title: 文档标题
category: 方向研究
status: tracking
updated_at: 2026-06-21
confidence: medium
tags:
  - AI
sources:
  - name: 来源名称
    url: https://example.com
---
```

## category

必须来自仓库 `metadata/taxonomy.json` 的 `categories[].name`。

当前常用值：

- 投资总纲
- 方向研究
- 历史案例
- 观察清单
- 复盘记录
- 信息候选池
- 模板

## status

必须来自仓库 `metadata/taxonomy.json` 的 `statuses[].id`：

- `watching`
- `tracking`
- `validated`
- `weakened`
- `rejected`
- `archived`

## confidence

必须来自仓库 `metadata/taxonomy.json` 的 `confidence_levels`：

- `low`
- `medium`
- `medium_high`
- `high`

这些英文值是 frontmatter 和 `metadata/sources.json` 的机器枚举。正文表格中仅用于展示强度、确定性、观察优先级或预期差的字段使用中文表达，如“高/中高/中/低”。不要把这些中文展示值写入 frontmatter、metadata 索引、方向状态、候选处理结果或来源层级字段。

## 新增正式文档流程

1. 从 `data-source/99_模板/` 选择模板。
2. 新建到对应目录。
3. 填写 frontmatter。
4. 写正文判断。
5. 添加“更新记录”。
6. 在 `metadata/sources.json` 增加索引。
7. 如果是方向研究，同步 `metadata/direction-registry.json`。
8. 如有结构变化，更新 `CHANGELOG.md`。
9. 运行 `node scripts/validate-knowledge-base.js`。

## 时间窗口文件命名

先读取 `metadata/update-state.json` 的 `period_policy.active_research_period`。如果已配置活跃研究周期，优先选择该周期文件；该字段默认应与当前自然季度一致，只有用户明确要求预建未来周期或补录历史周期时才偏离当前自然季度。未配置时，再按当前日期选择周期文件：

- 信息候选池：`data-source/05_信息候选池/YYYYQn_信息候选池.md`
- 观察清单：`data-source/03_观察清单/YYYYQn_观察清单.md`
- 判断复盘：`data-source/04_复盘记录/YYYY_判断复盘.md`

当自动化跨季度或跨年度运行时，如果目标文件不存在，必须创建新文件并加入 `metadata/sources.json`。不要继续写入已经过期的上一季度候选池或观察清单。

季度复盘在 1/4/7/10 月 1 日执行时，复盘上一自然季度；复盘完成后，将活跃研究周期切换或确认到运行日所在自然季度，并创建或更新该季度观察清单。

## 更新已有文档流程

1. 更新正文中受影响的章节。
2. 更新 `updated_at`。
3. 必要时调整 `status`、`confidence` 和 `sources`。
4. 在“更新记录”追加一行。
5. 同步 `metadata/sources.json` 中对应字段。
6. 运行校验脚本。

## 正式文档内容边界

模板说明、填写示例和占位内容只允许出现在 `data-source/99_模板/`。正式文档只保留实际记录、判断、证据、来源和更新记录。

正式文档中禁止残留：

- `填写要求`；
- `待填写` 占位；
- 以“模板”为标题的说明章节；
- 以“记录格式”为标题的说明章节；
- “按下面格式记录”这类填写说明；
- 只用于示例的 Markdown 代码块。

这条规则适用于所有非模板正式文档，不按文档类型例外处理。

## 候选池记录格式

```md
| 日期 | 来源层级 | 来源 | 方向 | 信息摘要 | 初步判断 | 处理结果 |
| --- | --- | --- | --- | --- | --- | --- |
| YYYY-MM-DD | tier_1 | 来源名称和链接 | 方向 | 摘要 | 对判断链条的潜在影响 | watch |
```

新增方向候选的 `处理结果` 使用 `new_direction_candidate`。

`处理结果` 表示候选信息已经完成的处理状态，不是建议动作。只要当前任务尚未实际写入或新建正式文档，就不得使用 `update` 或 `create`；日频已有方向信息默认使用 `watch`，需要正式更新时在“初步判断”中说明由周频复核处理。
