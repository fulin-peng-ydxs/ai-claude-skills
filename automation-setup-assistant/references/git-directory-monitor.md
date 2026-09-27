# Git 目录监测示例

当用户希望 Codex 按计划监测本地 Git 目录，并提交所有 Git 可见变化时，使用这个模式。

## 用户输入

- 要监测的目录：
  - `/Users/pengshuaifeng/.codex/skills`
  - `/Users/pengshuaifeng/.claude/skills`
- 运行时间：每天 `23:00`。
- 变化规则：提交任何 Git 可见的新增、修改或删除文件；忽略 `.gitignore` 排除的文件。
- 暂存规则：`git add -A`。
- 提交消息规则：参考 `/Users/pengshuaifeng/.claude/skills/git-commit-msg/SKILL.md`。
- 推送规则：提交成功后自动 push。
- 输出语言：中文。

## 预检查

创建或更新自动化前，运行这些检查：

```bash
git -C /Users/pengshuaifeng/.codex/skills rev-parse --show-toplevel
git -C /Users/pengshuaifeng/.claude/skills rev-parse --show-toplevel
ls -la /Users/pengshuaifeng/.claude/skills/git-commit-msg
git -C /Users/pengshuaifeng/.codex/skills status --porcelain --untracked-files=all
git -C /Users/pengshuaifeng/.claude/skills status --porcelain --untracked-files=all
```

## 自动化配置

- 对 Git 多仓库监测，创建多个 `cron` 自动化，每个仓库一个自动化。
- 不要用一个自动化配置多个 cwd 再在提示词里遍历多个仓库；这可能导致手动执行时多次运行，并引发 `.git/index.lock` 竞争。

第一个自动化：

- 类型：`cron`
- 名称：`每晚提交 Codex 技能目录变更`
- RRULE: `FREQ=DAILY;BYHOUR=23;BYMINUTE=0;BYSECOND=0`
- 执行环境：`local`
- 工作区：`/Users/pengshuaifeng/.codex/skills`

提示词应要求：

```text
监测 Git 仓库 /Users/pengshuaifeng/.codex/skills 中未被 .gitignore 忽略的文件变化。
执行 git -C /Users/pengshuaifeng/.codex/skills status --porcelain --untracked-files=all。
如果没有 Git 可见变化，报告该仓库没有变化。
如果存在任何新增、修改或删除，执行 git -C /Users/pengshuaifeng/.codex/skills add -A。
然后参考 /Users/pengshuaifeng/.claude/skills/git-commit-msg/SKILL.md 中的提交消息模板和规则生成提交信息：默认项目标识使用 Agent；单一功能/小改动使用单行模板；多文件、多模块、多个相关改动或需要说明影响范围时使用完整模板；只有明确来源时才写需求来源；多个互不依赖需求时优先在结果中说明建议拆分，若仍需本次自动提交则使用完整模板分组概括。
使用 git -C /Users/pengshuaifeng/.codex/skills commit -m "<提交信息标题>" 创建提交；如果生成了完整模板，使用多个 -m 参数创建提交，第一个 -m 写标题，后续 -m 写正文段落。
随后必须使用显式命令 git -C /Users/pengshuaifeng/.codex/skills push 推送仓库。
最终用中文报告处理结果、创建的提交 hash，以及 push 是否成功或失败。
不要处理其他仓库。
```

第二个自动化：

- 类型：`cron`
- 名称：`每晚提交 Claude 技能目录变更`
- RRULE: `FREQ=DAILY;BYHOUR=23;BYMINUTE=0;BYSECOND=0`
- 执行环境：`local`
- 工作区：`/Users/pengshuaifeng/.claude/skills`

提示词应要求：

```text
监测 Git 仓库 /Users/pengshuaifeng/.claude/skills 中未被 .gitignore 忽略的文件变化。
执行 git -C /Users/pengshuaifeng/.claude/skills status --porcelain --untracked-files=all。
如果没有 Git 可见变化，报告该仓库没有变化。
如果存在任何新增、修改或删除，执行 git -C /Users/pengshuaifeng/.claude/skills add -A。
然后参考 /Users/pengshuaifeng/.claude/skills/git-commit-msg/SKILL.md 中的提交消息模板和规则生成提交信息：默认项目标识使用 Agent；单一功能/小改动使用单行模板；多文件、多模块、多个相关改动或需要说明影响范围时使用完整模板；只有明确来源时才写需求来源；多个互不依赖需求时优先在结果中说明建议拆分，若仍需本次自动提交则使用完整模板分组概括。
使用 git -C /Users/pengshuaifeng/.claude/skills commit -m "<提交信息标题>" 创建提交；如果生成了完整模板，使用多个 -m 参数创建提交，第一个 -m 写标题，后续 -m 写正文段落。
随后必须使用显式命令 git -C /Users/pengshuaifeng/.claude/skills push 推送仓库。
最终用中文报告处理结果、创建的提交 hash，以及 push 是否成功或失败。
不要处理其他仓库。
```

## 授权验证

创建自动化后，对精确的 push 命令触发一次授权：

```bash
git -C /Users/pengshuaifeng/.codex/skills push
git -C /Users/pengshuaifeng/.claude/skills push
```

使用 `sandbox_permissions: require_escalated`，并为每条命令设置匹配的持久 `prefix_rule`。

如果自动化线程里出现 `Could not resolve hostname github.com`，但当前聊天线程中 push 正常，说明问题不是 Git 凭据，而是 Codex 自动化线程网络沙箱。处理方式不是换成系统级定时任务，而是：

1. 向用户说明需要持久放开精确 push 命令的风险。
2. 等用户明确同意。
3. 在 `~/.codex/rules/default.rules` 写入精确规则：

```text
prefix_rule(pattern=["git", "-C", "/Users/pengshuaifeng/.codex/skills", "push"], decision="allow")
prefix_rule(pattern=["git", "-C", "/Users/pengshuaifeng/.claude/skills", "push"], decision="allow")
```

4. 更新自动化提示词：普通 push 失败时必须用 `require_escalated` 重试同一条命令。
5. 手动运行自动化本身验证，而不是只在当前聊天线程执行 push。

仅在当前线程执行 push 成功不等于自动化验证通过。还需要手动执行一次自动化，并读取对应 `memory.md`，确认没有重复运行、没有 `.git/index.lock`，并确认 push 在自动化线程中是否仍受网络限制。

## 失败诊断

如果运行结果显示已经创建提交，但 push 因 DNS 或网络错误失败，说明本地提交已经成功，缺少的只是网络授权。

如果运行结果显示没有 Git 可见变化，用下面命令验证：

```bash
git -C <repo> status --porcelain --untracked-files=all
```

如果运行结果未能创建提交，检查仓库状态、Git 身份配置、hooks，以及 `git add -A` 是否被允许写入仓库。
