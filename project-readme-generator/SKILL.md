---
name: project-readme-generator
description: 生成、重构或优化项目 README.md。用于用户要求创建 README、优化 README、补全项目介绍、梳理安装启动测试构建命令、整理架构模块入口、生成开发者/用户使用说明，并要求基于当前仓库事实和实际命令验证后再落地 README 的场景。
---

# 项目 README 生成器

## 核心规则

从当前仓库事实生成 README，不凭记忆、不照搬样例。README 面向项目读者，优先回答“这是什么、解决什么问题、怎么运行、怎么使用、从哪里继续读、哪些边界不能破坏”。

除命令、代码、文件名、机器字段和目标仓库已有英文约定外，默认使用简体中文；用户明确要求英文时再改用英文。

## 执行流程

1. 发现事实。
   - 读取现有 `README.md`、`AGENTS.md`、`CLAUDE.md`、设计/架构/需求文档、包管理文件、构建文件、启动脚本、测试配置和主要源码入口。
   - 运行 `scripts/detect_readme_facts.py <repo-root>` 收集候选事实、目录、清单、脚本、文档入口和命令线索。
   - 文档与代码冲突时，优先相信代码、脚本和机器可读配置。

2. 选择 README 模型。
   - 读取 `references/readme-model.md`。
   - 根据项目类型、读者和复杂度选择章节模块，不固定套用某个项目的章节标题。
   - 当前项目 README 的可复用点是“问题导向、闭环流程、模块入口、架构关系、命令分层、故障排查、文档索引”，不是具体业务内容。

3. 建立并执行命令验证。
   - 读取 `references/command-verification.md`。
   - README 会写成常规流程的安装、测试、构建、启动、健康检查、停止、CLI 命令，必须实际执行成功后再落地。
   - 失败后只做一次有明确依据的非破坏性重试；仍失败或不确定时停止并询问用户。

4. 起草与落地。
   - 读取 `references/content-quality.md` 做质量检查。
   - README 只写当前有效事实；删除历史流水、迁移叙事、过期计划、猜测命令和重复文档。
   - 对详细设计、架构、API、需求、AI 协作规则，只放入口和摘要，不把下游文档整段复制进 README。
   - 验证门禁通过后再写入 `README.md`。

5. 自检并汇报。
   - 重读 `README.md` 检查链接、命令、目录、图表、表格和读者路径。
   - 汇报写入文件、已验证命令、未写入命令及原因、残余风险。

## 文档边界

- `README.md`：项目对外或对开发者的主入口，承载概览、运行、使用、架构入口和文档索引。
- `AGENTS.md`：AI 协作约束，不复制到 README，只在需要时链接。
- `CLAUDE.md`：Claude Code 薄入口，不复制到 README。
- 设计、架构、API、需求文档：作为事实源和深入阅读入口，不在 README 展开全部细节。

## 资源入口

- `references/readme-model.md`：README 模块选择、结构策略和当前项目可借鉴的通用写法。
- `references/command-verification.md`：README 命令验证门禁和失败处理。
- `references/content-quality.md`：内容质量、去冗余、链接和图表检查规则。
- `scripts/detect_readme_facts.py`：候选事实扫描脚本。它只辅助发现，不替代人工判断和命令验证。
