# 命令模式与判定

本文定义规则格式和匹配算法，执行顺序见 [主流程](../SKILL.md)。项目只维护一份有效策略，新项目用 `OPS_ROOT/command-policy.json`，从 [默认模板](../assets/command-policy.json) 生成，不另写分类说明文章。

## 格式与匹配

- `version`：正整数；`targets`：共享本组规则的精确 `{server_id, user}` 对；`approval_ref`：批准该版本的可信用户消息/记录引用，草案为 null。字段本身不证明授权，执行者须核实来源。
- `deny / ask / allow`：命令模式字符串数组；`default` 固定为 `ask`。先 deny，再 ask，再 allow；未匹配、目标不符、配置错误均 ask。禁止项不能被普通任务批准覆盖。
- 命令和模式按 shell 引号解析为参数序列，逐参数匹配。`*`、`?`、`[abc]` 是单参数内通配符；独立 `**` 匹配零个或多个参数。`systemctl restart *.service` 不匹配额外参数；`docker service update **` 匹配其余参数。
- 控制符/重定向、换行、变量/命令替换不自动 allow；SSH、sudo、解释器/脚本等包装未命中 deny/ask 时返回 ask。执行者展开内层动作再判定，任一 deny 即停止；脚本批准绑定内容/哈希。未加引号的路径/花括号/波浪号展开或注释转 ask；实际命令传具体对象，通配写在规则里，格式字符串可用引号保护。

## 生成与更新

1. 初始化复制模板为草案，填本次服务器/账号；删不适用平台命令，按已发现服务名、Docker socket、程序路径和输出需求补实际模式。只读候选不自动授权；日志/配置读取须限定路径、字段、条数和时间窗。
2. 展示具体模式及范围，一次请求批准该版本；获批写 `approval_ref`，记录批准原文/版本。用户不设长期白名单时清空 allow，明确采用单次方案授权。
3. 服务器、账号或管理方式变化时提交 diff，获批后递增 version 并切换；未获批保留原有效版，草案不能覆盖它。批准一次执行方案不自动修改策略。
4. 已有 Markdown 策略先按原规则判定；迁移时转换完整语义、展示差异并取得批准，再更新 AGENTS 引用、停用旧版。不能丢弃原 deny 或把文本策略当空策略放行；历史记录不改写。

## 使用工具

```bash
python3 <技能目录>/scripts/check_command.py --policy <项目策略.json> --server-id <服务器ID> --user <账号> --command 'systemctl restart nginx.service'
```

输出 `decision / reason / pattern / policy_version`；退出码 allow=0、ask=2、deny=3，读取/格式错误按 ask 并给出原因。策略损坏须先恢复有效规则，不能据此认定无 deny。工具不连接、不执行输入、不处理审批。ask 已被有效方案精确覆盖时直接执行，不重复询问；allow 仍须连接授权，变更仍先批准整体方案。API/SQL/文件工具按对象和副作用等效判断，不因没有 shell 文本绕过规则。

工具级拦截只能从有效策略生成适配配置并验证允许/确认/拒绝及包装案例；本脚本不提供硬隔离。模板及匹配测试只用本地无害样例，不在生产执行破坏命令。
