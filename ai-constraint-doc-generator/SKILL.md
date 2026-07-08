---
name: ai-constraint-doc-generator
description: 生成或重构项目级 AI 通用约束文档，包括 AGENTS.md 与 CLAUDE.md。用于用户要求创建、更新、模板化、精简或校准仓库 AI 协作说明、Claude Code 入口、Codex 约束文档，并要求基于真实项目事实验证环境、测试、构建、本地启动命令后再落地的场景。
---

# AI 通用约束文档生成器

## 核心规则

从当前仓库事实生成面向 AI 的项目级说明，不凭记忆、不照搬样例。只写当前有效、稳定可执行、会影响后续 AI 协作质量的规则。

使用 `AGENTS.md` 作为项目级权威入口。`CLAUDE.md` 只作为 Claude Code 薄入口，指向权威文档和事实源，避免复制完整规则。

除命令、代码、文件名、机器字段和目标仓库已有英文约定外，生成文档默认使用简体中文；用户明确要求英文时再改用英文。

## 执行流程

1. 发现项目事实。
   - 读取目标仓库中实际存在的 `AGENTS.md`、`CLAUDE.md`、`README.md`、设计文档、架构文档、包管理文件、构建文件、启动脚本和测试配置。
   - 文档与代码冲突时，优先相信代码、脚本和机器可读配置。
   - 不把本技能或其他项目中的业务事实带入目标项目。

2. 建立命令验证计划。
   - 运行 `scripts/detect_project_commands.py <repo-root>` 收集技术栈、清单文件、脚本和候选命令。
   - 写文档结构前读取 `references/document-model.md`。
   - 判断验证门禁前读取 `references/verification-gate.md`。
   - 只读取检测到的相关语言参考：`references/languages/` 下的 Python、Vue/Node、Java 等文件。

3. 执行验证门禁。
   - 对将写入文档的环境版本、依赖或工具可用性、测试、构建、本地启动、状态检查和停止命令做实际执行验证。
   - 优先使用仓库提供的启动、停止、状态脚本，不随意裸跑长期进程。
   - 必验命令失败时，不写入或覆盖 `AGENTS.md`、`CLAUDE.md`。
   - 一次失败后，只在有明确、非破坏性修复依据时重试一次；仍失败或原因不确定时停止并询问用户，不连续试错。

4. 通过后再起草。
   - 只写入已成功执行的命令，或明确标注为“已发现但不作为已验证流程”的命令。
   - 项目特有契约只保留当前有效、会影响正确性、安全性、数据一致性、权限、构建产物或用户流程的内容。
   - 删除迁移说明、历史过程、临时案例、猜测命令和重复规则。

5. 落地并自检。
   - 验证门禁通过后再写 `AGENTS.md` 和 `CLAUDE.md`。
   - 写完后重读文件，检查职责分离、链接有效性、命令准确性，以及是否误带样例项目内容。
   - 向用户汇报已写文件、已验证命令、未写入命令及原因。

## 文档边界

- `AGENTS.md`：所有 AI Agent 的项目级权威说明。
- `CLAUDE.md`：Claude Code 专用薄入口，只保留入口指引、工作方式和必要记忆规则。
- `README.md`：产品或开发概览，可作为事实源引用，不承载 AI 协作规则。
- 设计、架构、需求和功能目录：已有职责时只引用入口，不复制完整细则。

## 资源入口

- `references/document-model.md`：目标文档结构、内容边界和薄入口模式。
- `references/verification-gate.md`：命令验证门禁、失败处理和交互规则。
- `references/languages/python.md`：Python、FastAPI、Django、pytest 等项目。
- `references/languages/vue.md`：Vue、Vite、Node 包管理项目。
- `references/languages/java.md`：Java、Maven、Gradle、Spring 项目。
- `scripts/detect_project_commands.py`：候选命令扫描脚本。它只能辅助发现，不能替代实际执行验证。
