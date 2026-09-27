# Claude 全局 Skills 说明

这个目录存放当前用户自定义的 Claude 全局技能。每个技能使用独立目录管理，核心入口文件为 `SKILL.md`。

## 目录用途

- 作用范围：放在 `~/.claude/skills/` 下的技能，可在 Claude 会话中作为全局技能被发现和使用。
- 适用场景：沉淀常用 Git 流程、项目文档生成、业务核查、设计规范、页面审查、前端复用治理和项目 MCP 接入能力。
- 组织方式：一个技能一个目录；如有 `agents`、脚本、模板、参考文档或说明文件，统一跟随技能目录一起维护。

## 当前技能

| 技能目录 | 主要用途 |
| --- | --- |
| `agent-auto-commit-audit` | 审查并修复指定 Git 项目中 Agent-Auto 提交范围内的代码、业务闭环、页面体验和相关文档。用于用户要求审查最近 Agent-Auto 提交、检查 AI 自动开发提交记录、按提交范围做代码 review、业务 review、页面审查、文档同步、自修复无业务歧义的问题、运行测试和浏览器自动化验证，并输出每个审查方向引用的约束规则文档或技能的场景。 |
| `ai-constraint-doc-generator` | 生成或重构项目级 AI 通用约束文档，包括 AGENTS.md 与 CLAUDE.md。用于用户要求创建、更新、模板化、精简或校准仓库 AI 协作说明、Claude Code 入口、Codex 约束文档，并要求基于真实项目事实验证环境、测试、构建、本地启动命令后再落地的场景。 |
| `ai-instruction-simplifier` | 精简、重构和规范 AI 约束文档、项目指令文档、AGENTS.md、CLAUDE.md、DESIGN.md、AI 工具全局/项目级记忆文档、Codex/Claude skills、自动化规则和提示词规范。用于用户要求简化、去冗余、去历史流水账、合并职责边界、整理文档关系、压缩技能说明，且必须保留最新事实、稳定执行约束和核心业务规则的场景。 |
| `ai-trend-knowledge-maintainer` | 维护 AI 趋势投资知识源仓库。用于用户要求更新、审查、规范化、复盘或自动化维护 /Users/pengshuaifeng/ai-trend-analysis 中的 Markdown 知识库；也用于判断外部新闻、财报、研报、技术路线、资本开支、订单、产能和政策信息是否应进入 data-source，并同步 metadata、更新记录、候选池和校验闭环。 |
| `auto-plan-dev` | 仅当用户明确提出使用 auto-plan-dev、$auto-plan-dev 或“使用开发计划生成器技能”时，才根据需求文档、PRD、requirement.md 或已确认的功能需求生成可执行开发计划。即使用户要求“根据需求文档生成开发计划”“制定实施计划”“拆分开发任务”“输出 plan.md”“生成任务编排和进度追踪清单”，只要没有明确点名使用本技能，AI 也不得自动使用本技能。 |
| `automation-setup-assistant` | 用于创建、更新、精简和验证 Codex 自动化任务；也用于排查自动化执行失败、权限失败、网络失败、Git push 失败、定时任务未运行、提示词冗余或提示词职责边界不清等问题。 |
| `backend-memory-risk-report` | 分析一个项目的后端，尤其是 Java/Spring 服务中可能存在的内存溢出、内存泄漏和异常内存增长风险，并输出完整结构化报告到项目路径下的 `docs/check/memory/日期.md`。适用于需要检查后端代码中的静态持有、无限增长缓存、ThreadLocal 滞留、监听器或调度任务堆积、大对象缓冲、资源泄漏、队列堆积等内存风险场景；报告需包含风险证据、影响、触发条件、修复建议和处理进度状态。 |
| `business-closed-loop-flow-analyzer` | 基于项目当前代码、数据结构和配置，还原单个业务功能从用户入口到终态的闭环运行流程，并生成章节稳定的事实文档，重点覆盖参与角色、操作方式、状态流转、数据权限、表关系、字段赋值和核心代码。用于分析已实现业务功能的端到端闭环；不用于设计尚未落地的需求、审查本次改动或生成整个模块的综合架构文档。 |
| `business-feature-audit` | 对当前会话或当前 Git 工作区中本次开发涉及的代码做业务闭环核查，判断改动放回业务链路后是否成立，是否存在流程闭环、状态流转、上下游协同、权限、兼容性、数据一致性、异常处理、运营落地和前端业务承接遗漏；支持先基于 Git diff 和会话上下文输出快速业务风险结论，也支持在用户确认模块、范围和目录名后写入 `business-audit.md`。 |
| `code-reviewer` | Use this skill to review code. It supports both local changes (staged or working tree) and remote Pull Requests (by ID or URL). It focuses on correctness, maintainability, and adherence to project standards. |
| `design-compliance-audit` | 审查项目 DESIGN 文档本身是否完整、一致、可执行、可验证且符合项目事实，并依据该文档检查前端页面、组件、布局、样式、交互、响应式、配置字段、页面登记、维护清单和验证命令是否合规。用于用户要求审查 DESIGN.md、设计系统文档质量、前端改动是否遵循 DESIGN、页面模板、组件规范、布局规范、风格 token、Design System、设计契约、页面设计闭环或“理论上不应该不遵循 DESIGN”的场景。默认同时审查 DESIGN 事实源和当前项目所有可访问页面及前端实现；也可按用户指定文档、模块、路由、页面文件、PR 或 diff 审查。不替代页面 UX 审美审查，不评估业务算法正确性。 |
| `development-trace` | 为当前会话或当前 Git 工作区中的业务代码改动生成开发留痕文档。仅当用户显式调用 `$development-trace` 时使用，不得根据代码改动、开发完成、文档需求或相似语义自动调用；按功能需求生成或更新 development-trace.md，输出目录遵循全局协作规则。 |
| `disk-usage-report` | 分析本机或指定目录的磁盘使用情况，定位高占用目录和可清理目标，并输出带风险分级的结构化报告。用于磁盘空间不足、查找大文件或评估清理方案；不用于未经确认的删除操作。 |
| `english-daily-tutor` | 面向小学英语水平、以日常口语听说为目标的中文讲解技能。当用户给出一句完整英文句子并要求"讲一下/拆解/学习/理解/分析"这句、给出中文想学对应的英文说法、或要求复习已学英语知识时使用。输出逐词释义（含常用变形）、语法讲解与中英对比差异、举一反三例句，并把新知识沉淀进本技能目录下的 knowledge/english-knowledge.md。 |
| `five-dim-stock-analysis` | 基于公开数据完成上市公司五维股票质量分析与季报增量跟踪。用户提供股票代码或公司名，要求判断公司质量、估值、风险、打分、建仓区间，或要求更新季报、复核原判断时使用；以 A 股为主要覆盖范围，不用于只查询股价或泛泛讨论行业。 |
| `frontend-design` | Guidance for distinctive, intentional visual design when building new UI, web pages, landing pages, dashboards, components, or reshaping an existing frontend. Use when Codex needs aesthetic direction, typography, visual hierarchy, layout, copy, or design quality that avoids generic AI templates and default-looking interfaces. |
| `frontend-reuse-enforcer` | 前端开发与代码审查中的复用优先约束。用于 AI 新增或修改前端页面、组件、表格、表单、弹窗、抽屉、筛选、状态逻辑、样式、hook/composable、util、API 封装、测试 helper 时，强制先查找同类实现；只要同类 UI、交互逻辑、状态处理、数据展示模式或参数处理逻辑在代码中第二次出现，就必须优先抽取或消费复用单元。不抽取必须说明清楚理由。也用于用户要求治理重复代码、避免页面私有实现、复用已有组件、减少 AI 堆代码或检查是否应抽组件/抽 hook/抽 util 的场景。 |
| `git-commit-msg` | 根据已确定的 Git 改动范围生成规范化提交消息：先确定文件范围，再读取改动摘要，生成提交文案后直接输出；仅在用户显式调用本技能时交互确认范围，否则自行确定范围且不提问；不执行 git add、git commit 或 git push。 |
| `git-push` | 推送 Git 提交：先确定提交文件范围，再生成提交信息，随后按范围执行 git add、git commit，并在用户要求推送时执行 git push；仅在用户显式调用本技能时进行交互确认，否则自行完成各流程步骤。 |
| `module-architecture-doc-generator` | 分析项目代码与现有文档后，按业务模块、平台模块或技术子系统生成和更新架构设计文档。用于用户要求梳理项目架构、为每个模块生成 architecture 文档、补全核心技术/业务架构/使用说明/流程/风险事项、建立模块文档索引、同步 README 与 AGENTS 文档入口的场景。 |
| `page-ux-audit` | 审查前端页面的视觉一致性、排版、颜色、交互直观性、动画、状态反馈、说明指引、控件必要性和页面细节质量。用于用户要求检查页面设计、交互合理性、UI 细节、风格统一、原型实现偏差、页面验收、冗余按钮/冗余控件、功能堆砌或“不要只为了做功能而做功能”的场景。默认审查当前项目所有可访问页面；也可按用户指定模块、路由、页面文件、PR 或变更范围审查。不评估业务算法、接口口径或业务规则正确性。 |
| `process-usage-report` | 分析本机当前进程的 CPU、内存、IO、线程和子进程分布，识别最可能导致卡顿或资源异常的进程并输出结构化报告。用于电脑卡顿、风扇高速、资源占用异常等排查；不用于未经确认地结束进程。 |
| `project-design-md-generator` | 为当前项目生成或更新 `DESIGN.md`：扫描前端代码，沉淀可复用的 UI 规范；前端不统一或关键规范缺失时，先给建议并等待确认。 |
| `project-handover-analyzer` | 基于项目源码、配置、构建与部署材料生成可复核的全局接手分析报告。用于用户要求快速了解、接管、盘点或评估一个完整项目，重点说明总体功能、技术与部署架构、模块职责、跨模块依赖、交付完整性、运行风险和接手路线；不用于只分析单个业务闭环、单个模块架构或仅做代码变更审查。 |
| `project-readme-generator` | 生成、重构或优化项目 README.md。用于用户要求创建 README、优化 README、补全项目介绍、梳理安装启动测试构建命令、整理架构模块入口、生成开发者/用户使用说明，并要求基于当前仓库事实和实际命令验证后再落地 README 的场景。 |
| `requirement-closure-designer` | 基于粗需求、核心要点或未闭环想法，补全功能闭环和落地链路，默认先在对话中分析；用户确认或要求保存时，沿用已有成果的结构和完整内容落盘，保留待确认状态。适用于澄清页面、入口、角色、操作、状态、权限、配置、异常与范围，或先完成闭环设计再决定是否生成正式需求文档的场景。 |
| `requirement-doc-generator` | 生成完整的项目化需求文档，用于在制定开发计划前澄清功能需求。适用于用户要求创建、补充、确认或保存需求文档、PRD、需求分析、requirement.md，或希望 AI 结合业务需求、当前项目代码、数据库实际情况、交互体验、边界条件、风险和验收标准来充分理解需求，并沉淀为可指导后续 AI 生成高质量开发计划的文档。 |
| `setup-dm-mcp` | 为当前项目注册达梦（DM）数据库 MCP 服务器。如项目已有 .codex-mcp/dm-db-mcp/run.sh 则直接复用；否则从技能模板自动创建完整实现（Java 源码 + run.sh）。连接参数直接写入 .mcp.json 的 env（不使用 ~/.codex/secrets），并更新 .claude/settings.json 免确认授权、执行 health_check 连接验证。适用于用户要求"注册 DM MCP"、"setup dm mcp"、"创建达梦数据库 mcp"等场景。 |
| `setup-redis-mcp` | 为当前项目注册 Redis MCP 服务器。如项目已有 .codex-mcp/redis-mcp/run.sh 则直接复用；否则从技能模板自动创建完整实现（纯 Java 实现，零依赖，内置 RESP 协议）。连接参数直接写入 .mcp.json 的 env（不使用 ~/.codex/secrets），并更新 .claude/settings.json 免确认授权、执行 health_check 连接验证。适用于用户要求"注册 Redis MCP"、"setup redis mcp"、"创建 redis mcp"、"生成 redis mcp"等场景。 |
| `setup-taos-mcp` | 为当前项目注册 TDengine（TaoS）时序数据库 MCP 服务器。如项目已有 .codex-mcp/taos-db-mcp/run.sh 则直接复用；否则从技能模板自动创建完整实现（Java 源码 + run.sh）。连接参数直接写入 .mcp.json 的 env（不使用 ~/.codex/secrets），并更新 .claude/settings.json 免确认授权、执行 health_check 连接验证。适用于用户要求"注册 TDengine MCP"、"setup taos mcp"、"创建 taos 数据库 mcp"等场景。 |
| `sync-codex-config` | 将 Codex 全局技能集合和协作说明同步到 Claude Code 与 Kimi Code 的用户级安装目录；同名技能或文档已存在时以 Codex 内容更新。用于用户要求同步、刷新、复制或对齐 Codex、Claude、Kimi 的全局技能和协作指令时。 |

## 使用方式

1. 在会话中直接描述需求，命中技能适用场景时，Claude 会按技能说明执行。
2. 如果要明确触发某个技能，可以直接提到技能目录名或对应任务名称；带显式调用约束的技能，只有在用户明确点名后才可使用。需求分析场景可先用 `requirement-closure-designer` 在对话中补齐闭环、确认后再保存闭环文档，之后再用 `requirement-doc-generator` 落正式文档；页面问题可按业务核查、DESIGN 文档与实现合规、体验审查和复用治理选择对应技能。
3. 使用前优先查看目标目录的 `SKILL.md`，确认输入要求、执行流程、输出格式和安全边界；如目录中还有 `references/`、`agents/`、脚本或模板，也要一并核对这些关键资源是否仍与技能说明一致。
4. 新增技能时，至少创建 `技能目录/SKILL.md`，写清技能名称、适用场景、步骤、限制和交付物。

## 编写建议

- 技能说明优先写清“触发条件、确认节点、执行顺序、禁止行为”。
- 需求文档和开发计划类技能要维护稳定的机器可追踪契约，例如需求编号、建议项处理状态、需求到任务映射、页面功能点覆盖和状态字段，不要只写泛化说明。
- 需求文档只识别页面是否依赖已有通用前端能力、是否可能新增通用能力、是否涉及配置化承载；具体组件实现、注册、消费和验证任务由开发计划承担。
- 开发计划类技能除了任务状态，还要维护建议项/可选增强的开发状态、任务实际落地情况和测试验证的具体完成情况，确保计划更新能反映真实实现、验证结果和遗留缺口。
- 开发计划涉及运行时复用组件、布局/配置组件种类、组件配置字段或页面注册能力时，必须写清复用或新增判断、真实消费页面、维护清单、配置入口和验证方式。
- 开发计划类技能如果涉及页面、布局、组件、交互或配置入口，README 和 `SKILL.md` 都要体现必须读取并承接项目 `DESIGN.md` 及其他适用设计规范的约束。
- 涉及固定文档、模板、Agent 配置或参考资料时，统一放到技能目录并在 `SKILL.md` 中引用。
- 需求文档和开发计划类技能如果依赖页面原型、图示或其他补充资源，要把资源目录约定写清楚，并确保 README 中的用途说明仍与 `SKILL.md` 一致。
- 需求闭环、正式需求文档和开发计划中出现“建议实现”或“可选增强”时，必须显式记录处理状态，避免后续无法判断是否纳入、已实现或跳过。
- 需求文档类技能如果输出 HTML 原型，原型中的正式业务控件必须与需求定义一致；暂不实现交互要禁用或显著标注，说明性内容和原型演示控件要与正式业务界面明确区分，避免被误实现为线上功能。
- Git、数据库、自动化这类高风险操作，要把用户确认点和安全红线写明确。
- 涉及闭环分析的技能如果要求“先对话确认、再落盘”，README 和 `SKILL.md` 都要明确保存时机、输出目录约束和不直接升级为正式需求文档的边界。
- README、架构文档与 AI 协作约束文档类技能如果要求命令验证后再落地，README 中的用途说明和维护约束也要与该门禁保持一致。
- 页面审查类技能要在 README 和 `SKILL.md` 中保持清晰边界：业务闭环、DESIGN 文档质量与实现合规、体验细节和前端复用分别归属对应技能，避免职责重叠。
- 涉及生成正式需求文档或原型落地的技能，要在 `SKILL.md` 中明确“先展示摘要并获得确认，再写入文件”的约束；README 不需要复述全部细节，但不能遗漏这类关键维护原则。
- 技能应沉淀可复用流程，不要夹带只适用于单次任务的临时上下文。

## 备注

- README 用于快速浏览目录用途与技能清单，具体执行规则仍以各技能目录下的 `SKILL.md` 为准。
- 新增、删除或重命名技能目录，或技能的用途、触发约束、关键资源目录发生变化后，应同步更新本文件，避免目录说明过期。
