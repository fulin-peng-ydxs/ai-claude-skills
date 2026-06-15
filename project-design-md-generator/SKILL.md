---
name: project-design-md-generator
description: 为当前项目生成或更新 `DESIGN.md`：扫描前端代码，沉淀可复用的 UI 规范；前端不统一或关键规范缺失时，先给建议并等待确认。
---

# Project DESIGN.md Generator

为当前项目生成项目专属 `DESIGN.md`，让后续 AI 按统一规范产出前端界面。

## 适用范围

在以下场景使用本技能：

- 用户要求根据当前项目前端生成、补齐或更新 `DESIGN.md`
- 用户要求把现有页面、组件、样式、主题、设计 token 沉淀成 AI 可读取的 UI 约束文档
- 用户要求先检查前端是否规范，再决定如何生成 `DESIGN.md`

本技能默认只生成或更新文档，不修改业务前端代码。

## 核心原则

- `DESIGN.md` 必须基于当前项目真实前端实现、可验证样式和已存在的设计模式生成。
- 对后台、运营台、工作台等高密度业务界面，`DESIGN.md` 必须覆盖表格、列表、筛选区、弹窗、抽屉等高频容器规则。
- 对高密度业务界面，要同时抽取项目已有稳定事实，并在必要时补齐缺失规范；不能把低质量现状直接固化进 `DESIGN.md`。
- 如果项目现有前端明显不统一、缺少必要规范或多个风格冲突，不要强行把混乱现状写成规范；先提出收敛建议并等待用户确认。
- 生成 `DESIGN.md` 时优先抽取稳定事实，其次才是合理补全；补全内容必须明确是建议性决策，而不是伪装成既有事实。

生成时按以下顺序：

1. 读取 `references/design-md-structure.md`
2. 读取 `references/frontend-audit-checklist.md`
3. 需要写入时读取 `references/design-md-template.md`
4. 扫描项目并生成或更新 `DESIGN.md`

## 信息来源

按以下顺序收集证据：

1. 用户给出的项目路径、页面范围、产品定位和额外约束
2. 当前项目中的前端入口、页面、组件、样式、主题文件、设计 token 文件
3. 样式约定：颜色变量、字体栈、间距、圆角、阴影、边框、断点、组件状态
4. 项目已有设计文档、组件库文档、品牌规范、设计系统文件
5. 项目已有 `DESIGN.md`，如果存在
6. `references/design-md-structure.md`

## 扫描范围

优先检查这些文件类型：

- 页面和组件：`*.html`、`*.jsx`、`*.tsx`、`*.vue`
- 样式和主题：`*.css`、`*.scss`、`*.less`、`tailwind.config.*`、`theme.*`、`tokens.*`
- 设计系统线索：组件库目录、布局组件、基础表单组件、按钮、表格、弹窗、导航

默认不深挖后端、数据库、接口或无关脚本，除非它们直接决定前端文案、状态或主题。

先全局定位候选文件，再重点阅读代表性文件。优先查找以下线索：

- 颜色：hex、rgb、hsl、CSS 变量、主题色变量
- 字体：`font-family`、字号、字重、行高
- 间距和尺寸：`margin`、`padding`、`gap`、容器宽度、断点
- 形状和层级：`border-radius`、`box-shadow`、`border`
- 组件状态：hover、active、focus、disabled、loading、error、success

## 输出位置

默认输出到项目根目录：

```text
./DESIGN.md
```

用户指定其他路径时按用户要求处理。

## 执行流程

1. 定位项目根目录，确认当前项目是否存在可分析的前端代码。
2. 读取 `references/design-md-structure.md` 与 `references/frontend-audit-checklist.md`。
3. 检查项目根目录是否已有 `DESIGN.md`；如果存在，必须读取并判断是更新、合并还是重写。
4. 识别前端技术栈、样式组织方式、样式入口和设计 token 来源。
5. 全局定位候选页面、组件、样式和主题文件，再重点阅读代表性页面、基础组件和样式入口。
6. 对照 `references/frontend-audit-checklist.md` 判断项目是否具备直接生成或更新 `DESIGN.md` 的条件。
7. 条件充分且不存在必须确认的情况时，读取 `references/design-md-template.md` 并生成或更新 `DESIGN.md`。
8. 存在明显缺口、冲突、已有文档覆盖风险或需要补规范时，先输出“拟定规范建议”和“拟生成范围”，等待用户确认。
9. 用户确认后，按 `references/design-md-template.md` 的骨架生成项目专属 `DESIGN.md`。
10. 完成后汇报依据文件、更新策略、哪些内容来自事实抽取、哪些内容是经确认后的补全建议。

需要确认时，确认内容应给出：

- 已识别到的前端现状摘要
- 发现的不一致或缺失项
- 如果本次属于“规范补齐”，明确指出哪些现状不应直接写入规范，以及准备补齐哪些规范项
- 建议采用的收敛方案
- 生成 `DESIGN.md` 后会写入的关键决策
- 如果已有 `DESIGN.md`，说明更新策略：保留、合并、修正或重写

## DESIGN.md 写作要求

生成的 `DESIGN.md` 必须满足以下要求：

- 使用项目自己的名称和定位
- 使用固定模板结构
- token 和 prose 同时存在
- 章节顺序和字段命名保持稳定
- 对缺失但必要的规范，只在用户确认后补入
- 避免空泛形容词，优先写可执行、可落地、可复用的规则

对高密度界面，如果项目已有实现无法支撑专业交互规范，应在用户确认后补齐规范，而不是只记录现状。

最低内容要求、固定章节和高密度界面规则以 `references/design-md-structure.md` 为准。

## 建议输出格式

当需要先确认时，先输出：

```markdown
## 前端现状摘要

## 发现的问题

## 建议补齐的规范

## 拟写入 DESIGN.md 的关键决策

请确认是否按以上方案生成 `DESIGN.md`
```

## 输出约束

- 输出内容使用中文，`DESIGN.md` 中的 token 名和标准字段名可保留英文
- 不把“推测”“审美偏好”“参考品牌描述”写成项目事实
- 不直接复制第三方 `DESIGN.md` 的品牌文案
- 不为了凑完整度发明大量项目中根本不存在的组件
- 如项目前端过少、几乎无样式依据，明确说明无法可靠生成完整 `DESIGN.md`，并给出最小补充建议

## 参考文件

- 结构规则：`references/design-md-structure.md`
- 审核清单：`references/frontend-audit-checklist.md`
- 输出模板：`references/design-md-template.md`
