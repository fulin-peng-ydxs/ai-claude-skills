---
name: ai-trend-knowledge-maintainer
description: 维护 AI 趋势投资知识源仓库。用于用户要求更新、审查、规范化、复盘或自动化维护 /Users/pengshuaifeng/ai-trend-analysis 中的 Markdown 知识库；也用于判断外部新闻、财报、研报、技术路线、资本开支、订单、产能和政策信息是否应进入 data-source，并同步 metadata、更新记录、候选池和校验闭环。
---

# AI趋势知识库维护

## 默认仓库

默认维护路径：

```text
/Users/pengshuaifeng/ai-trend-analysis
```

如果用户明确给出其他路径，以用户路径为准。

## 核心原则

先候选，后正式。自动化运行时由 Codex 按本技能规则完成判断；只有来源冲突、证据不足但影响重大、需要删除大量内容、或会显著改变总纲方法论时，才标记为 `review`。

正式更新必须满足至少一个条件：

- 影响趋势判断；
- 验证或证伪关键瓶颈；
- 改变资本开支传导方向；
- 出现真实订单、收入、利润、产能、交付周期变化；
- 改变某个方向的状态或置信度。

## 工作流程

1. 读取 `README.md`、`metadata/automation-plan.json`、`metadata/taxonomy.json`、`metadata/sources.json`、`metadata/direction-registry.json`、`metadata/company-registry.json`、`metadata/source-registry.json` 和相关目标文档。
2. 读取 `metadata/update-state.json`，识别本次任务类型、处理窗口和上次处理时间。
3. 依据 `metadata/direction-registry.json` 判断输入信息属于已有方向、新方向候选，还是无关信息。
4. 默认先更新 `data-source/05_信息候选池/`。
5. 若证据足够，自动更新正式 Markdown 文档。
6. 同步文档 frontmatter、正文判断、文档内“更新记录”。
7. 新增正式文档时，同步 `metadata/sources.json`。
8. 重要结构变更同步 `CHANGELOG.md`。
9. 更新 `metadata/update-state.json` 的本次运行结果。
10. 最后运行校验：

```bash
node scripts/validate-knowledge-base.js
```

可用本技能脚本简化校验：

```bash
/Users/pengshuaifeng/.claude/skills/ai-trend-knowledge-maintainer/scripts/validate_repo.sh /Users/pengshuaifeng/ai-trend-analysis
```

## 来源层级

- `tier_1`：公司财报、投资者关系、监管文件、官方博客、技术白皮书、监管和交易所披露。可用于正式更新。
- `tier_2`：TrendForce、SemiAnalysis、IDC、Gartner、Omdia 等研究机构或行业数据库。可用于正式更新，但要标注来源。
- `tier_3`：主流财经媒体、产业媒体、会议纪要和专家访谈。通常先进入候选池。
- `low_priority`：社媒观点、二手解读、无明确来源截图。只进入候选池，不直接更新正式结论。

自动化优先从 `metadata/source-registry.json` 读取固定来源。未登记来源可以使用，但必须标注来源层级，并说明为什么采用。

需要更细的处理标准时，读取 `references/update-policy.md`。

## 更新频率

- 日频：只追加候选池，不直接改变正式判断。
- 周频：整理候选池，自动判断是否更新方向研究或观察清单。
- 月频：自动更新观察清单和需要持续验证的信号。
- 季度：自动更新复盘记录。
- 重大事件：财报、资本开支指引、真实订单、政策变化、技术路线变化可随时触发。

## 网络受限处理

自动化遇到网络不可用、DNS 失败、网页无法打开或来源无法访问时，不得中断整个知识库维护流程。

按任务类型处理：

- 日频：不创建空候选信息，不更新正式文档；在 `metadata/update-state.json` 的 `daily.last_status` 写 `network_limited`，`daily.last_error` 写明失败原因，运行本地校验并报告。
- 周频：继续处理本地候选池和已有文档；需要外部来源补充确认的事项标记 `review`。
- 月频：继续基于本地候选池、方向研究和观察清单更新；外部验证缺失的事项标记 `review`。
- 季度：继续基于本地记录复盘；无法外部验证的结论标记 `review`，不要编造新证据。

网络受限时禁止：

- 编造来源；
- 生成无法追溯的新事实；
- 把网络失败当作产业趋势变化；
- 因无法联网而删除已有正式判断。

## 文档契约

所有 `data-source` Markdown 必须包含 YAML frontmatter，至少包括：

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
sources: []
---
```

所有非模板正式文档必须在 `metadata/sources.json` 中有索引，并包含“更新记录”。

frontmatter、`metadata/sources.json`、方向状态、候选处理结果和来源层级使用 `metadata/taxonomy.json` 中的英文机器枚举；正文表格中仅用于展示强度、确定性、观察优先级或预期差的字段使用中文值，如“高/中高/中/低”，不要把中文展示值写入机器字段。

所有正式文档都不得把模板说明写入正文：

- `填写要求`、`待填写`、示例代码块、模板章节、记录格式说明只允许出现在 `data-source/99_模板/` 或技能说明中；
- 正式文档只能保留实际记录、当前判断、证据、来源、更新记录等可被外部系统读取的内容；
- 任何正式文档都不得残留模板式说明。

详细字段和新增文档流程见 `references/document-contract.md`。

## 时间窗口文件

候选池和观察清单按季度组织。自动化运行时必须先读取 `metadata/update-state.json` 的 `period_policy.active_research_period`。

如果配置了 `active_research_period`，优先使用该研究周期；该字段默认应与当前自然季度一致，只有用户明确要求预建未来周期或补录历史周期时才偏离当前自然季度。未配置时，再根据当前日期选择文件：

- 候选池：`data-source/05_信息候选池/YYYYQn_信息候选池.md`
- 观察清单：`data-source/03_观察清单/YYYYQn_观察清单.md`
- 年度复盘：`data-source/04_复盘记录/YYYY_判断复盘.md`

如果目标文件不存在，必须从 `data-source/99_模板/` 复制对应结构创建，并同步 `metadata/sources.json`、frontmatter 和“更新记录”。

季度复盘在 1/4/7/10 月 1 日运行时，复盘上一自然季度；复盘完成后，将 `active_research_period` 切换或确认到运行日所在自然季度，并创建或更新该季度观察清单。不要在未明确要求时提前写入未来季度文件。

## 方向管理

方向总表维护在 `metadata/direction-registry.json`。

自动化不得把方向范围写死在 prompt 里。执行时必须：

1. 优先读取方向总表中的 `priority`、`tracking`、`watching` 方向。
2. 对不属于已有方向但满足入库标准的信息，写入候选池并标记 `new_direction_candidate`。
3. 只有新方向具备趋势、瓶颈、资本开支、受益环节和验证信号的基本链条时，才新建正式方向研究文档。
4. 方向可按证据变化在 `candidate`、`watching`、`tracking`、`priority`、`weakened`、`paused`、`archived`、`rejected` 之间流转。

详细方向状态和流转规则见 `references/direction-management.md`。

## 公司观察池

公司注册表维护在 `metadata/company-registry.json`。

公司层信息不得绕过候选池和方向研究闭环。执行时必须：

1. 优先读取公司注册表中的范围、状态、观察池策略和画像策略。
2. 公司相关新信息默认先写入信息候选池；只有周频、月频、季度或重大事件任务实际更新公司注册表、核心标的观察池或公司画像时，候选记录才能标记为 `update`。
3. 核心标的观察池只记录方向匹配、收入承接、验证信号和风险，不输出买入、卖出、目标价或仓位建议。
4. 公司画像创建和更新以 `metadata/company-registry.json` 的 `company_profile_policy` 为唯一规则源。
5. 新建公司画像时必须同步 frontmatter、`metadata/sources.json`、文档内“更新记录”，并运行校验。

## 频率识别

自动化 prompt 必须明确声明本次任务类型：`daily`、`weekly`、`monthly`、`quarterly` 或 `event`。

不要只依赖“距离上次运行多久”推断频率。执行时使用 `metadata/update-state.json` 的 `jobs.<type>.last_success_at` 作为处理窗口起点，并用候选池表格里的日期筛选本窗口信息。

## 决策输出

处理外部信息时，给出明确处理结果：

- `ignore`：不进入知识库，仅保留候选记录；
- `watch`：已进入候选池，等待更多证据或周频复核；日频发现的已有方向信息默认使用该状态；
- `new_direction_candidate`：新方向候选，进入候选池并等待升级判断；
- `update`：已完成已有正式文档更新；不能用于只建议后续更新但尚未写入正式文档的候选记录；
- `create`：已完成新建正式文档；不能用于只建议后续新建但尚未创建文档的候选记录；
- `review`：自动化无法可靠处理，需人工复核后再处理。

`处理结果` 表示已经完成的处理状态，不是建议动作。若信息足以支持后续正式更新，但当前任务没有实际修改正式文档，仍应标记为 `watch`，并在“初步判断”中说明周频复核时优先判断是否更新。日频任务不得使用 `update` 或 `create`，因为日频只追加候选池。

最终回复用户时，说明：

- 更新了哪些文件；
- 信息进入候选池还是正式文档；
- 判断链条受到什么影响；
- 校验是否通过；
- 哪些点仍需人工复核。
