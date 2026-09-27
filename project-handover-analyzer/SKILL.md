---
name: project-handover-analyzer
description: 基于项目源码、配置、构建与部署材料生成可复核的全局接手分析报告。用于用户要求快速了解、接管、盘点或评估一个完整项目，重点说明总体功能、技术与部署架构、模块职责、跨模块依赖、交付完整性、运行风险和接手路线；不用于只分析单个业务闭环、单个模块架构或仅做代码变更审查。
---

# 项目接手分析器

## 目标

从当前可访问的项目事实中还原“这是什么、如何组成、如何运行、缺什么、先接手什么”，生成一份技术负责人可直接用于项目接管的 Markdown 报告。报告是当前状态快照，不是产品宣传、需求规划或源码目录复述。

默认使用简体中文；命令、代码、标识符和项目既有术语保持原样。

## 与相邻技能的边界

- 整个项目的全景、部署、跨模块依赖和交付完整性：使用本技能。
- 单个模块的详细架构文档：使用 `module-architecture-doc-generator`。
- 单项业务功能的端到端闭环：使用 `business-closed-loop-flow-analyzer`。
- 当前 Git 改动的正确性或业务风险：使用代码审查或业务核查技能。

只有用户同时要求这些交付物时才组合使用；不要因本技能自动扩展到代码修复、部署、提交或外部系统操作。

## 工作方式

1. 确定分析边界。
   - 识别项目根、嵌套 Git 仓库、子项目、版本线和生成物边界。
   - 根目录包含多个独立仓库时，将其视为一个交付包，分别记录仓库归属和组合关系。
   - 用户未限制范围时分析完整可访问项目；明确列出排除项、不可读取项和未验证项。

2. 建立机器清单。
   - 阅读 [references/project-discovery.md](references/project-discovery.md)。
   - 运行 `scripts/scan_project_handover.py <project-root> --format markdown`，辅助发现仓库、构建清单、部署材料、配置、数据库、测试和文档入口。
   - 扫描结果只是候选事实，必须回读关键文件确认，不能直接把目录名当作模块职责。

3. 还原系统关系。
   - 先解释用户和业务能力，再解释前端、网关/API、服务、数据、中间件、外部集成和运维设施。
   - 依赖至少区分构建依赖、运行调用、数据依赖、配置依赖、部署依赖和可选集成。
   - 对多版本、多实现、多入口和插件拼装形态做冲突分析，指出推荐主线及证据，不凭命名猜测。

4. 评估交付完整性。
   - 阅读 [references/evidence-completeness-security.md](references/evidence-completeness-security.md)。
   - 分别评估源码完整性、可构建性、可运行性、可部署性、数据准备、可观测性、测试保障和文档可接手性。
   - “缺失”必须有预期来源，例如父构建声明、路由、导入、配置、部署脚本或文档承诺；没有预期证据时写“待确认”，不要套用通用项目模板判缺。
   - 每个关键判断标注状态、证据、影响、置信度和验证方法。

5. 生成接手报告。
   - 阅读 [references/handover-report-model.md](references/handover-report-model.md)。
   - 以 [assets/project-handover-report-template.md](assets/project-handover-report-template.md) 为报告起始骨架，按项目事实填充内容；交付前删除全部花括号占位符、示例节点和 HTML 注释。
   - 默认生成一份完整的项目级单文档，使用参考文档规定的 14 章骨架；不得把它压缩成只有技术栈、模块表和风险矩阵的简版报告。
   - 输出位置按顺序选择：用户指定路径、项目已有同类报告、`agent-works/architecture/project-handover-report.md`。
   - 更新已有同类报告时保留仍成立的事实，删除与当前代码冲突的旧结论；不要创建重复报告。
   - 默认保留“一页结论、代码包全景、总体功能、技术架构、部署架构、模块职责、依赖关系、客户端结构、完整性、典型调用链、接手路线、交付方问题、证据入口、最后建议”等独立信息区。
   - 复杂关系使用 Mermaid，精确清单和评估结果使用表格；简单关系用文字。多服务项目至少包含总体运行图、构建或运行依赖图和核心调用时序图。
   - 项目确实不具备某类内容时，在对应章节写明“不适用”和依据；不要静默删除核心章节。用户明确要求精简版时才调整为摘要结构。

6. 验证和交付。
   - 回查报告中的关键路径、命令、模块名、端口、版本、API、表、配置键和依赖方向。
   - 验证 Mermaid 节点与关系可读，表格不过度横向扩张，链接和相对路径有效。
   - 做敏感信息扫描，确保报告没有密码、令牌、密钥、证书私钥、Cookie、完整连接串或不必要的内网端点。
   - 仅在安全且成本合理时执行构建或启动验证；未执行或失败必须明确记录，不能把静态推断写成运行验证。
   - 最终汇报报告绝对路径、分析范围、主要结论、验证方式和仍需交付方确认的问题。

## 分析底线

- 代码与机器可读配置优先于 README；README 可说明意图，但冲突时必须指出。
- 不读取或复述依赖缓存、构建产物、压缩包和大体积二进制内容，除非它们是唯一交付物且用户要求检查。
- 不输出任何真实凭据。敏感文件只记录相对路径、敏感类型、影响和治理建议。
- 不因缺少 Docker、Kubernetes、CI 或自动化测试就直接判定项目“不完整”；结合项目声明和交付目标判断。
- 不把静态扫描发现的端口、路由或服务名称直接判定为实际生产拓扑。
- 不修改业务代码、配置值、数据库或部署环境，除非用户另行明确授权。

## 资源

- [references/project-discovery.md](references/project-discovery.md)：项目边界、事实源和跨技术栈发现方法。
- [references/handover-report-model.md](references/handover-report-model.md)：接手报告应回答的问题和表达模型。
- [references/evidence-completeness-security.md](references/evidence-completeness-security.md)：证据等级、完整性判定、安全与质量门禁。
- [assets/project-handover-report-template.md](assets/project-handover-report-template.md)：与完整分析模式一致的 14 章 Markdown 输出骨架。
- `scripts/scan_project_handover.py`：只读项目清单扫描器，支持 Markdown 和 JSON 输出。
