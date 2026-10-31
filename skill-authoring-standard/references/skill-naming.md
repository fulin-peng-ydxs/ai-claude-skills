# 技能命名规范

## 职责与边界

本文维护用户自有技能的一级领域、英文调用标识、中文名称、UI 名称和重命名契约；编写流程及验证入口由 [技能编写规范](../SKILL.md) 维护。系统、插件及其他第三方技能沿用提供方名称，不因本规范改名。

## 名称层次

| 层次 | 契约 | 示例 |
| --- | --- | --- |
| 英文调用标识 | 技能目录名与 frontmatter 的 `name` 完全一致，用于稳定调用和引用 | `frontend-ux-audit` |
| 中文名称 | `SKILL.md` 正文一级标题，使用“对象 + 任务”，不加角色词 | 页面体验审核 |
| UI 名称 | 配置 `agents/openai.yaml` 的 `interface.display_name` 时，与中文名称完全一致 | 页面体验审核 |
| 触发说明 | `description` 维护触发场景、工作模式及必要边界，不把这些信息全部堆进名称 | 仅审核指定页面或当前改动 |

没有 UI 元数据时不为命名额外创建；配置了 `default_prompt` 时须通过 `$英文调用标识` 引用当前技能，保持其他策略及依赖字段不变。

## 英文标识

采用 `一级领域-[必要的细分对象]-任务能力`：第一个词固定表示所属领域，同领域技能共用前缀，任务能力放在末尾；细分对象按需保留。例如 `design-spec-authoring`、`design-compliance-audit`、`frontend-prototype-design`、`frontend-ux-audit`。

- 仅使用小写英文字母、数字和单个连字符；不得以连字符开头或结尾，长度不超过 64 个字符。
- 优先使用 2～5 个英文单词，准确性优先于短；一级领域必须保留，其余对象和范围只保留区分相邻技能所需的信息，避免重复表达。
- 保留 `ai`、`git`、`mcp`、`ux`、`readme` 等通用缩写；使用 `message`、`development` 代替 `msg`、`dev`。
- 不使用 `auto`、`smart`、`advanced` 等弱语义修饰或 `v2` 等版本标记。工具名只在确实限定能力时使用，例如 `config-codex-sync`。
- 按主要工作命名，不按执行者角色或最终文件形式命名。新增名称不使用 `generator`、`designer`、`analyzer`、`reviewer`、`maintainer`、`assistant`、`enforcer` 等角色结尾。

## 一级领域

先按主要职责选择下表领域，再确定细分对象和任务能力；同领域不得交替使用领域、工具名、范围或对象作为开头。不能仅因技能涉及某技术或生成某类文件就归入该领域。

| 一级领域 | 负责范围 | 示例 |
| --- | --- | --- |
| `ai` | AI 协作指令、提示词与约束内容 | `ai-instruction-refactoring` |
| `automation` | 自动化任务的配置、验证与排障 | `automation-management` |
| `backend` | 后端实现与运行风险 | `backend-memory-risk-analysis` |
| `business` | 业务链路事实与功能闭环核查 | `business-feature-audit` |
| `code` | 跨技术栈的代码质量审查 | `code-review` |
| `config` | 工具或服务配置的集成与同步 | `config-codex-sync`、`config-project-mcp-sync` |
| `design` | 设计规范与设计契约合规 | `design-spec-authoring`、`design-compliance-audit` |
| `development` | 开发计划、实施与交付流程 | `development-workflow` |
| `frontend` | 界面呈现、页面原型、体验与前端实现复用 | `frontend-design`、`frontend-prototype-design`、`frontend-ux-audit` |
| `git` | Git 提交消息与提交推送流程 | `git-commit-message-authoring`、`git-push` |
| `investment` | 投资研究知识与跟踪维护 | `investment-ai-trend-knowledge-maintenance` |
| `operation` | 服务器运维、连接与变更授权、单位手册和操作留痕 | `operation-workflow` |
| `project` | 项目总体认知、README 与模块架构事实文档 | `project-handover-analysis`、`project-readme-authoring`、`project-module-architecture-doc-authoring` |
| `requirement` | 需求闭环与正式需求契约 | `requirement-closure-design`、`requirement-doc-authoring` |
| `skill` | 技能本身的编写与维护规范 | `skill-authoring-standard` |
| `system` | 本机系统资源诊断 | `system-disk-usage-analysis`、`system-process-usage-analysis` |

- `design` 与 `frontend` 按工作对象区分：编写规范、审查设计契约归 `design`；设计或审核可观察界面、制作原型及治理实现复用归 `frontend`。能力结尾也叫 `design`，不代表一级领域必须为 `design`。
- `project` 仅承接项目总体与架构事实类工作，不能因为工作发生在项目中就使用该前缀；设计规范归 `design`，项目 MCP 同步归 `config`。`page`、`module`、`disk`、`process`、`codex` 等作为细分对象或范围，不与对应领域并列为一级前缀。
- 按主要使用目标分类：AI 趋势投资知识库归 `investment`，不因研究主题含 AI 就与 AI 协作指令同归 `ai`。多个领域参与时，按主职责确定一个前缀，协作关系放入说明。
- 新技能先复用现有领域；确有独立职责无法归入时，在授权范围内维护本表及检查器的领域词表，再创建新前缀，不为每个对象另建领域。

## 任务能力词

| 能力词 | 适用工作 | 示例 |
| --- | --- | --- |
| `authoring` | 编写、生成并更新文档或文本成果 | `project-readme-authoring` |
| `design` | 设计方案、交互、原型或规则 | `frontend-prototype-design` |
| `analysis` | 还原事实、分析原因和风险 | `backend-memory-risk-analysis` |
| `review` | 综合审查质量与正确性 | `code-review` |
| `audit` | 按明确标准或专项维度核查 | `design-compliance-audit` |
| `refactoring` | 精简、重组并保留有效语义 | `ai-instruction-refactoring` |
| `governance` | 持续约束和治理实现方式 | `frontend-reuse-governance` |
| `maintenance` | 持续维护已有内容和状态 | `investment-ai-trend-knowledge-maintenance` |
| `management` | 配置、修改、验证及排障等综合管理 | `automation-management` |
| `sync` | 在明确来源和目标之间同步 | `config-project-mcp-sync` |
| `workflow` | 覆盖多个紧密关联阶段的执行流程 | `development-workflow` |
| `standard` | 提供编写或执行规范 | `skill-authoring-standard` |

分析技能即使交付报告，也使用 `analysis`；主要工作是编写报告时使用 `authoring`，不以 `report` 作为分析能力的默认结尾。中文名称同样不加“生成器”“分析器”“设计器”“助手”等角色词。

能力词以本表为统一词汇；确有无法准确表达的新能力时，在获准范围内维护本表及对应检查器，不自行换用近义角色词。清晰且稳定的既有命令式入口 `git-push` 为保留例外，不将该例外扩展为新增技能的默认命名方式。

## 创建与重命名

1. 先检索已有同职责技能，决定新增还是扩展；名称不同不能作为新增同职责入口的理由。
2. 先确定统一一级领域，再根据细分对象与主要任务选名，核对目录、`name`、中文标题及 UI 元数据；职责与相邻技能的边界由名称和 `description` 共同表达。
3. 已有标识保持稳定；只有用户授权重命名时才迁移。先检查目标冲突、引用关系和对应安装副本，以各自实际内容为基线，保留差异，不覆盖为统一版本。
4. 同步更新调用提示、技能间引用、README、适用全局规范及自动化中的当前引用；自动化通过其配置工具更新，仅改变名称或路径，保留其他配置。历史日志、会话和运行记录不改写。
5. 不保留两个可发现的同职责入口；检查名称、引用、资源路径及元数据一致性。已有脚本和产物文件名不因技能标识变化而机械改名。

命名检查器验证一级领域词表、格式和元数据一致性，不能证明领域归属及名称准确表达职责。目录与标识匹配、中文名称与 UI 名称一致，也不能代替主要任务、相邻边界及重命名后消费方兼容性的复核。
