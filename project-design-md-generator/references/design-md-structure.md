# DESIGN.md 结构参考

本文件定义 `DESIGN.md` 的固定结构。

## 基本要求

- 顶部 YAML front matter 放 token
- 正文使用 `##` 分节
- token 提供精确值，正文解释如何使用

## 内容结构

最终输出以 `references/design-md-template.md` 为骨架。下面只说明必须覆盖的区块：

```md
---
version: alpha
name: 项目名称
description: 项目设计系统描述
colors:
  primary: "#..."
  secondary: "#..."
typography:
  body-md:
    fontFamily: ...
    fontSize: ...
rounded:
  sm: 4px
  md: 8px
spacing:
  sm: 8px
  md: 16px
components:
  button-primary:
    backgroundColor: "{colors.primary}"
    textColor: "{colors.on-primary}"
    rounded: "{rounded.md}"
---

# 项目名称 Design System

## 1. Visual Theme & Atmosphere

## 2. Color Palette & Roles

## 3. Typography Rules

## 4. Component Stylings

## 5. Layout Principles

## 6. Depth & Elevation

## 7. Do's and Don'ts

## 8. Responsive Behavior

## 9. Agent Prompt Guide

## 10. Known Gaps
```

## Front Matter

- `version`：建议使用 `alpha`
- `name`：项目名或产品名
- `description`：一句话说明视觉方向和使用场景
- `colors`：至少覆盖与项目直接相关的主色、辅助色、文本色、背景色、边框色、状态色
- `typography`：至少覆盖标题、正文、按钮或标签中的主要文本样式
- `rounded`：给出可复用的圆角层级
- `spacing`：给出最小可复用间距刻度
- `components`：只写项目中真实存在且高频的关键组件

## 写作要求

- 优先使用 token 引用，不要在组件定义里反复内联 hex 值
- 优先写“稳定规律”，不要把偶然样式当成系统规则
- 组件状态可独立命名，如 `button-primary-active`
- 正文描述解释风格和使用边界，避免空话
- 如果某些值是经确认后补全的，应保证与项目整体风格一致

## 固定项与可变项

固定项：

- 顶部 YAML front matter + 正文 Markdown 分层结构
- 章节顺序固定为 `Visual Theme & Atmosphere` 到 `Agent Prompt Guide`，`Known Gaps` 作为第 10 章
- `colors`、`typography`、`rounded`、`spacing`、`components` 等常见 token 区块
- token 颗粒度
- 对组件和布局的描述方法
- 对已知缺口和注意事项的记录方式
- 使用 `{colors.primary}` 这类 token 引用，而不是重复硬编码

可变项：

- 具体 token 命名，只要清晰稳定即可
- 组件覆盖范围，可按项目实际复杂度裁剪
- 已知缺口说明，统一写入 `## 10. Known Gaps`

禁止项：

- 品牌名称
- 品牌叙事
- 专属字体、专属视觉隐喻
- 与当前项目无关的组件体系

## 高密度业务界面补充要求

项目包含后台管理台、业务工作台、运营台或其他高密度信息界面时，`DESIGN.md` 还应覆盖：

- `Component Stylings` 中明确表格、筛选区、弹窗、抽屉、分页、详情区等高频容器或组件的稳定规则
- `Layout Principles` 中明确主内容区如何分配空间，列表/表格是否默认占据剩余区域，何时允许局部滚动
- `Do's and Don'ts` 中明确禁止项，例如双重滚动、固定小高度表格容器、复杂表格塞进普通小弹窗、所有列平均等宽、长文本默认自动换行
- `Responsive Behavior` 中明确常见桌面宽度下的列展示优先级、折叠策略和降级方式

这些规则不能只记录现状。项目当前实现缺失或明显粗糙时，应在用户确认后按最低质量标准补齐。

最低质量标准至少包括：

- 主数据区优先占据可用空间，避免固定小高度表格容器
- 优先单主滚动，避免页面、弹窗、表格多层滚动叠加
- 列宽按信息类型分配，不默认平均等宽
- 长文本默认省略、提示或展开，不默认自动换行
- 复杂表格和批量操作优先使用抽屉、全屏弹窗或独立页面，而不是普通小弹窗
- 明确 1366、1440、1920 等常见桌面宽度下的展示优先级和降级规则

表格与弹窗规则至少要写清以下内容：

- 列类型策略：编号、状态、时间、操作列保持稳定；企业名、标题、描述、备注等长字段使用更宽列
- 长字段策略：默认省略 + tooltip；必要时允许两行截断，并说明详情弹窗、展开行或独立详情的承接方式
- 操作列策略：优先单行可见；超过可读范围时改分组、下拉或详情入口，不靠多行堆叠
- 滚动策略：宽表通过横向滚动承载；局部滚动仅允许出现在明确分区的列表、浮层或弹窗正文
- 承载策略：纯确认、少字段编辑、宽表、批量操作、长流程录入分别对应普通 modal、更宽 modal、drawer、全屏弹窗或独立页面
- 降级策略：在 `1366px` 下优先保证主操作、操作列、状态列、时间列和核心业务列可见，次要说明列通过截断、详情或展开承接

项目确实没有此类界面时，可不补充，但应在 `Known Gaps` 或说明章节写明未覆盖。
