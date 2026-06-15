# DESIGN.md 固定输出模板

生成或更新项目 `DESIGN.md` 时使用本模板。占位内容必须替换为项目真实信息；无法确认的内容写入 `Known Gaps` 或先向用户确认。

```md
---
version: alpha
name: 项目名称
description: 一句话说明项目的界面定位、主要用户和整体视觉方向
colors:
  primary: "#000000"
  secondary: "#000000"
  background: "#ffffff"
  surface: "#ffffff"
  text-primary: "#111111"
  text-secondary: "#666666"
  border: "#e5e7eb"
  success: "#16a34a"
  warning: "#f59e0b"
  danger: "#dc2626"
typography:
  heading-lg:
    fontFamily: 项目字体或字体栈
    fontSize: 24px
    fontWeight: 600
    lineHeight: 32px
  body-md:
    fontFamily: 项目字体或字体栈
    fontSize: 14px
    fontWeight: 400
    lineHeight: 22px
  label-sm:
    fontFamily: 项目字体或字体栈
    fontSize: 12px
    fontWeight: 400
    lineHeight: 18px
rounded:
  sm: 4px
  md: 8px
  lg: 12px
spacing:
  xs: 4px
  sm: 8px
  md: 16px
  lg: 24px
  xl: 32px
components:
  button-primary:
    backgroundColor: "{colors.primary}"
    textColor: "#ffffff"
    rounded: "{rounded.md}"
  input-default:
    backgroundColor: "{colors.surface}"
    borderColor: "{colors.border}"
    rounded: "{rounded.sm}"
  card-default:
    backgroundColor: "{colors.surface}"
    borderColor: "{colors.border}"
    rounded: "{rounded.md}"
---

# 项目名称 Design System

## 1. Visual Theme & Atmosphere

说明项目界面的整体视觉主题、使用场景、信息密度和界面风格。必须基于项目现有前端归纳。

应包含 `Key Characteristics`，用短句列出后续 AI 必须保持的关键特征。

## 2. Color Palette & Roles

说明主色、辅助色、背景色、表面色、文本色、边框色和状态色的语义角色。若项目已有 CSS 变量或主题 token，应说明来源。

应说明哪些颜色可用于交互，哪些颜色只用于背景、文本、边框或状态，不要只列色值。

## 3. Typography Rules

说明标题、正文、标签、按钮、表单等主要文字层级。必须写清字体栈、字号、字重和行高的使用方式。

应包含字体家族、层级表和排版原则。

## 4. Component Stylings

说明项目中真实存在且高频的组件规范，优先覆盖按钮、输入框、卡片/面板、表格、弹窗、导航、页面容器。

应覆盖默认态、悬停态、激活态、聚焦态、禁用态、加载态、错误态等可确认状态。缺失状态应写入 Known Gaps。

若项目包含后台台账、业务列表、筛选页、弹窗或抽屉，这一章还应明确：

- 按结构规则补齐高密度界面所需的组件与承载策略

## 5. Layout Principles

说明页面容器、栅格、内容密度、间距节奏、断点和响应式策略。若项目没有明确断点，应写入 Known Gaps。

应包含 spacing scale、grid/container、whitespace philosophy。

若项目包含高密度后台界面，这一章还应明确：

- 按结构规则补齐主数据区空间利用与滚动层级规则

## 6. Depth & Elevation

说明圆角、边框、阴影、分割线、透明度、遮罩、浮层和层级的使用规则。不要把偶然样式写成系统规则。

应说明项目如何表达层级：阴影、边框、背景差异、透明度、z-index、图片深度或无层级策略。

## 7. Do's and Don'ts

写可执行的使用规则，帮助后续 AI 在新增页面或组件时保持一致。Do 写应遵循的做法，Don't 写明确禁止的反模式。

## 8. Responsive Behavior

说明断点、移动端布局、触摸目标、组件折叠策略、图片/表格/导航在不同屏幕下的行为。

如果项目没有明确响应式策略，应写入 Known Gaps。

若项目当前主要面向桌面端，至少应说明 `1366px`、`1440px`、`1920px` 下：

- 按结构规则补齐桌面降级策略

## 9. Agent Prompt Guide

给后续 AI 使用的快速提示指南，包含：

- Quick Color Reference
- Example Component Prompts
- Iteration Guide

提示内容必须基于本项目真实规范。

## 10. Known Gaps

记录当前项目缺少或无法可靠确认的设计规范。若无明显缺口，写“暂无已确认缺口”。
```

## 使用要求

- front matter 中的示例值必须替换为项目真实值；无法确认时不要保留示例值。
- 项目缺少某类 token 时，先判断是否需要用户确认；不影响主体系的缺口可写入 `## 10. Known Gaps`。
- 组件只写项目真实存在或用户确认要补齐的组件。
- 不同项目之间必须保持 1-9 章节稳定，`## 10. Known Gaps` 可保留为空或写“暂无已确认缺口”。
- 不要把 `Responsive Behavior` 合并进 `Layout Principles`，也不要把 `Agent Prompt Guide` 省略。
